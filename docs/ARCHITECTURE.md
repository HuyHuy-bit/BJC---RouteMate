# Architecture

## 1. System overview

```
┌─────────────┐      HTTPS/JSON      ┌──────────────┐        SQL        ┌─────────────────┐
│  Frontend   │ ───────────────────▶ │   Backend    │ ─────────────────▶│  PostgreSQL      │
│  (React)    │ ◀─────────────────── │  (FastAPI)   │ ◀──────────────── │  + PostGIS       │
└─────────────┘                      └──────┬───────┘                  └─────────────────┘
                                             │
                                             │ HTTPS
                                             ▼
                                     ┌──────────────┐
                                     │  Goong Maps   │
                                     │  Geocoding /  │
                                     │  Distance API │
                                     └──────────────┘
```

## 2. Why PostGIS instead of app-level distance math

The prototype computed distance with raw Euclidean math on fake pixel
coordinates. In production, "close together" needs to mean real-world
proximity on the actual road network. PostGIS gives us:

- `geography(Point, 4326)` columns to store real lat/lng
- `ST_DWithin(a, b, radius_meters)` — index-accelerated "is this within X
  meters" queries, used directly in the matching query
- `ST_Distance` — real great-circle distance for sorting/scoring candidates
- A GiST spatial index so these queries stay fast as the bookings table grows

Straight-line distance is only an approximation of drive time (a river or
highway can make two "close" points a long drive apart), so it is now used
strictly as a cheap coarse pre-filter. Everything that actually decides a
match — insertion cost, stop order, ETAs, the detour guarantee — runs on
real road durations from Goong's **Distance Matrix API**, fetched through
`app/services/routing.py` (cached, batched, circuit-broken, and flagged
`is_estimate` when it falls back to haversine).

## 3. Backend module layout

```
backend/app/
├── main.py                 FastAPI app entrypoint, middleware, router mounting
├── core/
│   ├── config.py            Settings loaded from environment (.env)
│   ├── security.py          JWT creation/verification, password hashing
│   └── encryption.py        Field-level encryption for PII (phone, address)
├── db/
│   ├── session.py           SQLAlchemy engine + session factory
│   └── base.py               Declarative base, shared mixins (timestamps, etc.)
├── models/                  SQLAlchemy ORM models (Customer, Booking, Trip,
│                               User, Vehicle, Corridor, Payment, ...)
├── schemas/                 Pydantic request/response schemas
├── services/
│   ├── geocoding.py          Goong Maps client (address → lat/lng)
│   ├── routing.py            The one gateway to Goong routing — caching,
│   │                           batching, circuit breaking, honest fallback
│   ├── geo.py                Pure corridor projection math (no DB session)
│   ├── corridors.py          Matches a booking's points to its corridor
│   ├── dispatch_service.py   Orchestration: pool selection, geometry
│   │                           refresh, assignment, ETAs
│   ├── pool_insertion.py     Should this rider join this pool, and in what
│   │                           stop order (feasibility + scoring)
│   ├── route_solver.py       Exact pickup-and-delivery ordering (§5)
│   ├── reclustering.py       Re-groups still-forming pools
│   ├── dispatch_engine.py    Per-tick decision: depart, wait, or escalate
│   ├── scheduler.py          Runs the dispatch cycle on a timer
│   ├── traffic.py            Rush-hour travel-time multiplier
│   ├── trip_state.py         The trip state machine + who may move it
│   ├── vehicle_return.py     Getting cars back to their home hub
│   └── ...                   booking/customer/notification/payment/audit
└── api/v1/routes/           One file per resource: auth, customers, bookings,
                               dispatch, vehicles, payments, notifications,
                               geocode, admin
```

## 4. Core domain model (initial pass)

- **User** — staff/admin/driver accounts, role-based permissions
- **Customer** — name, phone (encrypted), source (repeat customers get
  reused rather than re-entered)
- **Booking** — one customer's requested trip: pickup point, dropoff point,
  requested time window, `is_private` flag, status
  (`queued` / `matched` / `waiting` / `cancelled`)
- **Trip** — a car assignment: 1–4 bookings, driver/vehicle, computed stop
  order, and a status that moves through a role-enforced workflow —
  the driver accepts, starts and reports completion; a dispatcher signs
  it off. The full state machine, including who may make each move and
  which vehicle states follow from it, is **docs/STATE_MACHINE.md**;
  it is enforced in one place, `app/services/trip_state.py`.

## 5. Matching algorithm (as built)

Two decisions, deliberately kept separate because they have different
shapes: **who shares a car** (greedy, incremental) and **what order the
car visits stops in** (exact, re-solved for the whole group).

Tunable constants live in `app/core/dispatch_config.py`, except a few
local to the module that uses them.

### 5.1 Membership — greedy

`app/services/pool_insertion.py::evaluate_insertion` scores one candidate
booking against one existing forming pool and returns feasibility plus a
0..1 score where **lower is better** (weighted: added distance 0.28,
worst detour 0.24, pickup wait 0.20, occupancy 0.18, deadline pressure
0.10; rejected above `MAX_ACCEPTABLE_SCORE`). The booking joins the
best-scoring feasible pool.

- The acceptance criterion is **marginal route insertion cost**, not raw
  proximity: the pool's actual optimal route is solved with and without
  the candidate. Two riders can have close pickups and close dropoffs and
  still be a bad match if combining them forces the car to backtrack.
- Haversine (`COARSE_PREFILTER_METERS`, in `pool_insertion.py`) is a
  cheap pre-filter only — it
  discards obvious non-candidates before any API call. Every number that
  decides the match is a real road duration.
- Scoring deliberately makes no Directions call, saving one API request
  per candidate evaluated.
- Greedy means earlier grouping choices are never revisited.
  `app/services/reclustering.py` is the counterweight: it re-groups pools
  that are still `forming`, time-first and distance-second.

### 5.2 Stop order — exact, and re-solved

`app/services/route_solver.py::solve_pdp` is the shared core. This is a
**pickup-and-delivery problem, not a TSP**: each rider has a pickup and a
dropoff, the only hard precedence is that a rider is picked up before
their own dropoff, and stops from different riders interleave freely.

- For n riders there are 2n stops and `(2n)!/2^n` valid orderings —
  at most **2520** at the 4 seats this app allows. Cheap to solve
  exactly by constrained backtracking with branch-and-bound, and far
  cheaper in practice. Invalid orderings are never generated, so unlike
  a capped raw-permutation search this cannot be silently truncated.
- Two schedule constraints are pruned **inside** the search rather than
  validated afterwards, so an infeasible branch is abandoned instead of
  producing a "best" route that then gets thrown away:
  - pickup lands within `EARLY_PICKUP_TOLERANCE_MINUTES` /
    `LATE_PICKUP_TOLERANCE_MINUTES` of the requested time (arriving early
    costs a real wait that carries forward into every later stop);
  - no rider's in-car time exceeds their solo baseline by more than
    `MAX_PASSENGER_DETOUR_MINUTES`.
- Rush hour (`app/services/traffic.py`) scales route legs **and** the
  solo baseline they are compared against. Scaling one side only would
  make "detour = in-car minus solo" meaningless.
- The solver's per-stop arrival offsets are the single source of truth
  for the ETAs written to bookings — pickup and dropoff both.

**Vehicle anchoring.** Once a specific car is committed,
`best_ordering_from_position` prices the deadhead leg (car → first stop)
into the objective via `start_cost`, so the approach direction shapes the
chosen order instead of being invisible to it. The live GPS fix is used
only if newer than `VEHICLE_LOCATION_STALE_MINUTES`; otherwise the search
anchors at the vehicle's corridor home base. Anchoring at a stale-but-real
base beats letting the search start at whichever stop is cheapest, which
silently models a car that teleported to its first pickup.

**When it re-solves.** `_refresh_pool_geometry` throws the previous order
away and re-solves the entire group from scratch — never an incremental
patch — whenever pool membership or the assigned vehicle changes (booking
joins, leaves, is cancelled or removed; seal; vehicle assigned or
reassigned; trips merged; reclustering). A `solved_booking_ids` /
`solved_vehicle_id` snapshot on `Trip` short-circuits the work when
nothing has actually changed.

A car simply *moving* changes neither, so the order is **not**
continuously re-optimized in flight: it is solved at seal/assign time and
then held. That is a deliberate trade — live re-solving would mean a
Distance Matrix call per position update and a stop list that reshuffles
under the driver mid-route — but it does mean a significant post-assignment
deviation currently goes unnoticed.

### 5.3 Triggering

The cycle runs on a timer (`app/services/scheduler.py`, every
`DISPATCH_TICK_SECONDS` during operating hours), and per tick
`app/services/dispatch_engine.py` answers one question for each forming
pool: depart now, keep waiting, or escalate. Seal triggers in priority
order are full car → deadline with enough passengers → deadline on a
return leg (the car drives home regardless, so a single passenger still
departs) → deadline, outbound, one passenger, which is escalated
explicitly rather than silently stranded.

`POST /dispatch/run` remains for manual and test runs.

## 6. Auth & roles

- JWT access token (short-lived) + refresh token (longer-lived, stored
  hashed)
- Roles:
  - `admin` — everything a dispatcher can do, plus the financial and
    administrative surface: revenue reporting (`/api/v1/admin/*`),
    waiving fares, staff management.
  - `dispatcher` — the operation: bookings, merging, assigning vehicles
    and drivers, sealing, and finalizing completed trips. **No revenue
    rollups, and cannot start or complete a trip.**
  - `driver` — their own assigned trips: accept, reject, start, report
    completion, collect payment. Cannot finalize.
- Enforcement is server-side and structural. Trip-workflow permissions
  come from the transition table in `app/services/trip_state.py`, which
  every status write goes through, rather than from per-endpoint
  checks — the frontend renders its buttons from the same table via
  `TripOut.available_actions`, so the two cannot drift apart.

## 7. Deployment (not yet decided)

Options to evaluate later: a VN-based VPS (data residency is simpler to
reason about) vs. a managed platform (Render/Fly.io/DigitalOcean). This is a
business decision (cost, who maintains it) — flagged here rather than
assumed.

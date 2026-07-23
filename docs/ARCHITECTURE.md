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

Straight-line distance is still an approximation of drive time (a river or
highway can make two "close" points a long drive apart) — a later iteration
can call Goong's **Distance Matrix API** to score candidate groups by actual
drive time instead of straight-line distance, once volume justifies the
extra API calls.

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
├── models/                  SQLAlchemy ORM models (Customer, Booking, Trip, User)
├── schemas/                 Pydantic request/response schemas
├── services/
│   ├── geocoding.py          Goong Maps API client (address → lat/lng)
│   └── matching.py           The clustering algorithm, now running as a real
│                               PostGIS query instead of in-memory pixel math
└── api/v1/routes/           One file per resource: auth, customers, bookings,
                               dispatch, vehicles
```

## 4. Core domain model (initial pass)

- **User** — staff/admin/driver accounts, role-based permissions
- **Customer** — name, phone (encrypted), source (repeat customers get
  reused rather than re-entered)
- **Booking** — one customer's requested trip: pickup point, dropoff point,
  requested time window, `is_private` flag, status
  (`queued` / `matched` / `waiting` / `cancelled`)
- **Trip** — a car assignment: 1–4 bookings, driver/vehicle, computed stop
  order, status (`forming` / `confirmed` / `in_progress` / `completed`)

## 5. Matching algorithm (as built)

Greedy clustering over `queued` bookings, grouped by requested pickup date
first (a booking for tomorrow is never compared against one for today).
Implementation: `app/services/matching.py` + `app/services/route_solver.py`.

- Runs on a manual trigger (`POST /dispatch/run`) for now — a scheduled
  job (e.g. every 15 min) is the natural next step once this is running
  for real, matching the actual "batch until enough riders" business rule
- Clustering happens in Python over bookings pulled from Postgres, not as
  a single SQL query — at the volume this business runs (tens of bookings
  per batch), this is simpler to read and modify than an equivalent
  recursive SQL query. Worth revisiting with SQL-side `ST_DWithin`
  pre-filtering only if batch sizes grow into the hundreds.
- The acceptance criterion for adding a rider to a forming group is
  **marginal route insertion cost**: the group's actual optimal route
  (see below) is solved with and without the candidate, and they're only
  added if the increase stays under the configured max-detour threshold.
  This is a meaningfully better signal than raw pickup/dropoff proximity
  — two riders can have close pickups and close dropoffs while still
  being a bad match if combining them forces the car to backtrack.
- Route ordering is solved exactly, not approximated: for each finalized
  group (≤4 riders, ≤8 stops), every valid stop sequence respecting
  "pickup before that rider's own dropoff" is enumerated via backtracking
  (at most (2n)!/2^n orderings, ≤2520 at n=4) and the shortest one wins.
  This is real optimization, not a heuristic — cheap enough to brute-force
  exactly at this scale.
- No external API calls in the matching path — everything is haversine
  geometry on coordinates already in Postgres. Real road distance/drive
  time (via Goong's Distance Matrix API) would be more accurate but costs
  API calls and adds latency; noted as a possible future upgrade, not
  currently worth the cost at this business's scale.

## 6. Auth & roles

- JWT access token (short-lived) + refresh token (longer-lived, stored
  hashed)
- Roles: `admin` (full access), `dispatcher` (create/edit bookings, run
  matching), `driver` (read-only view of their own assigned trip)

## 7. Deployment (not yet decided)

Options to evaluate later: a VN-based VPS (data residency is simpler to
reason about) vs. a managed platform (Render/Fly.io/DigitalOcean). This is a
business decision (cost, who maintains it) — flagged here rather than
assumed.

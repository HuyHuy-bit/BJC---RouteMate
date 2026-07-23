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

## 5. Matching algorithm (production version)

Same greedy-clustering shape as the prototype, but:

- Runs as a scheduled job (e.g. every 15 min) over `queued` bookings, not a
  manual button — matches the real "batch until enough riders" business rule
- Candidate filtering happens in SQL via `ST_DWithin` on both pickup and
  dropoff, so the database does the heavy lifting instead of JS
- Route ordering within a confirmed trip upgrades from "sort by x" to a
  brute-force 4-point route solver (trivial at n≤4) respecting
  pickup-before-that-rider's-dropoff constraints

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

# Xe Ghép — Bắc Giang ⇄ Hà Nội Dispatch System

Hello — I created this software with the hope of helping reduce costs for
ride-sharing businesses, an industry that's very popular in the Vietnamese
market. This software is still in beta but will be released to the market
soon. It helps businesses find customers and supports matching them based
on logic that optimizes for distance and cost.

Internal dispatch platform for grouping door-to-door ride bookings into shared
4-seater trips, based on real proximity of pickup/dropoff points.

This is an Internal dispatch platform for grouping door-to-door ride bookings into shared 4-seater trips, based on real proximity of pickup/dropoff points.

## Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2.0 + PostGIS
- **Frontend:** React + TypeScript + Vite
- **Geocoding/Maps:** Goong Maps API
- **Auth:** JWT (access + refresh), argon2 password hashing
- **Infra (dev):** Docker Compose (Postgres+PostGIS, backend, frontend)

See `docs/ARCHITECTURE.md` for the full design and `docs/DATA_PROTECTION.md`
for how customer data is handled.

## First-time setup

1. Install Docker Desktop, enable WSL2 integration for your Ubuntu distro.
2. Get a Goong Maps API key: https://goong.io (free tier is enough for dev).
   You'll get two keys — a **Maps key** (for map tiles) and an **API key**
   (for Geocoding / Distance Matrix).
3. Copy the env template and fill in your keys:
   ```bash
   cp .env.example .env
   ```
4. Start everything:
   ```bash
   docker compose up --build
   ```
5. Backend docs (auto-generated): http://localhost:8000/docs
6. Frontend: http://localhost:5173

## Repo layout

```
xeghep/
├── backend/         FastAPI service — API, DB models, business logic
├── frontend/         React dispatch UI
├── docs/             Architecture + data protection documentation
├── docker-compose.yml
└── .env.example
```

## Status

Project skeleton — architecture and scaffolding only. Business logic
(auth, bookings, matching algorithm, geocoding integration) is built next,
module by module, on top of this structure.

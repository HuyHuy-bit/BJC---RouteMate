import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import (
    auth,
    bookings,
    customers,
    dispatch,
    geocode,
    health,
    users,
    vehicles,
)
from app.core.config import settings
from app.services.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uvicorn --reload spawns a reloader parent plus a worker; starting
    # the scheduler in both would double-dispatch every pool.
    if os.getenv("DISABLE_SCHEDULER", "").lower() not in ("1", "true", "yes"):
        start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Xe Ghép Dispatch API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(users.router, prefix="/api/v1/users")
app.include_router(vehicles.router, prefix="/api/v1/vehicles")
app.include_router(customers.router, prefix="/api/v1/customers")
app.include_router(bookings.router, prefix="/api/v1/bookings")
app.include_router(dispatch.router, prefix="/api/v1/dispatch")
app.include_router(geocode.router, prefix="/api/v1/geocode")

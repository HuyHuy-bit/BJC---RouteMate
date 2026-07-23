from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import auth, bookings, customers, dispatch, geocode, health
from app.core.config import settings

app = FastAPI(title="Xe Ghép Dispatch API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(customers.router, prefix="/api/v1/customers")
app.include_router(bookings.router, prefix="/api/v1/bookings")
app.include_router(dispatch.router, prefix="/api/v1/dispatch")
app.include_router(geocode.router, prefix="/api/v1/geocode")

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TripStatus
from app.schemas.booking import BookingOut


class TripOut(BaseModel):
    id: uuid.UUID
    status: TripStatus
    driver_id: uuid.UUID | None
    vehicle_label: str | None
    is_private: bool
    bookings: list[BookingOut]
    created_at: datetime


class MatchingRunResult(BaseModel):
    trips_created: int
    trips: list[TripOut]


class TripAssignDriver(BaseModel):
    driver_id: uuid.UUID


class TripStatusUpdate(BaseModel):
    status: TripStatus

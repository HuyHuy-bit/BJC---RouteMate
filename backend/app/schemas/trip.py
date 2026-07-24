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
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class MatchingRunResult(BaseModel):
    trips_created: int
    trips: list[TripOut]


class TripAssignDriver(BaseModel):
    driver_id: uuid.UUID


class TripStatusUpdate(BaseModel):
    status: TripStatus


class AttentionItem(BaseModel):
    """
    A forming pool that needs a human decision right now — either it
    couldn't fill by deadline (escalated) or the fleet is fully
    committed (no_vehicle). Previously these were only ever written to
    the dispatch_events audit log; nothing ever surfaced them to a
    dispatcher.
    """

    kind: str  # "escalated" | "no_vehicle"
    trip_id: uuid.UUID
    direction: str
    passenger_count: int
    minutes_overdue: float
    reason: str
    options: list[str] | None
    bookings: list[BookingOut]


class MergeTripsResult(BaseModel):
    target: TripOut

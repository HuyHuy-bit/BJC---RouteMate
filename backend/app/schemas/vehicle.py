import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.dispatch_config import MAX_PASSENGERS
from app.models.enums import VehicleStatus


class VehicleCreate(BaseModel):
    plate_number: str = Field(min_length=4, max_length=20)
    label: str | None = Field(default=None, max_length=50)
    seat_capacity: int = Field(default=MAX_PASSENGERS, ge=1, le=16)
    default_driver_id: uuid.UUID | None = None
    # If omitted and exactly one corridor is active, the route defaults
    # it automatically — same "server infers when unambiguous" rule
    # already used for a booking's direction. Only needs to be picked
    # explicitly once a second corridor exists.
    home_corridor_id: uuid.UUID | None = None


class VehicleUpdate(BaseModel):
    label: str | None = None
    status: VehicleStatus | None = None
    default_driver_id: uuid.UUID | None = None
    home_corridor_id: uuid.UUID | None = None
    # Manual correction for Vehicle.last_location — a dispatcher-facing
    # override for when the auto-captured point (set on trip completion,
    # see dispatch.py:update_trip_status) is stale or missing. Handled
    # specially in the route, not via the generic setattr loop, since
    # last_location is a PostGIS Geography column, not a plain scalar.
    last_location_lat: float | None = Field(default=None, ge=-90, le=90)
    last_location_lng: float | None = Field(default=None, ge=-180, le=180)


class VehicleOut(BaseModel):
    id: uuid.UUID
    plate_number: str
    label: str | None
    seat_capacity: int
    status: VehicleStatus
    default_driver_id: uuid.UUID | None
    home_corridor_id: uuid.UUID | None
    last_location_at: datetime | None

    # Where the car actually is. Previously only the TIMESTAMP of the
    # last fix was exposed, never the position — so the fleet view had
    # no way to say "this car is in Hà Nội now" and instead inferred
    # location from live trips, which is why a car vanished from the
    # board the moment its trip finished. Requirements §1.
    last_location_lat: float | None = None
    last_location_lng: float | None = None

    # Non-null exactly when a return to base is outstanding — the same
    # single source of truth the model uses, so a client never has to
    # infer "is this car being called home?" from the status alone.
    return_requested_at: datetime | None = None

    model_config = {"from_attributes": True}


class VehicleLocationPing(BaseModel):
    """Body for POST /vehicles/{id}/location — a driver reporting where
    their currently-assigned vehicle is right now."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

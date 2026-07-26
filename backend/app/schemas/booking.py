import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.dispatch_config import MAX_PASSENGERS
from app.models.enums import BookingDirection, BookingStatus
from app.schemas.customer import CustomerCreate, CustomerOut
from app.schemas.payment import PaymentOut


class BookingCreate(BaseModel):
    customer: CustomerCreate

    pickup_address: str = Field(min_length=1, max_length=255)
    pickup_lat: float = Field(ge=-90, le=90)
    pickup_lng: float = Field(ge=-180, le=180)

    dropoff_address: str = Field(min_length=1, max_length=255)
    dropoff_lat: float = Field(ge=-90, le=90)
    dropoff_lng: float = Field(ge=-180, le=180)

    requested_pickup_at: datetime
    is_private: bool = False
    # Seats this one booking occupies (a family travelling together is
    # ONE booking with several seats). Capped at MAX_PASSENGERS: a party
    # bigger than the smallest car in the fleet can't be served as a
    # single shared-ride booking at all.
    seats: int = Field(default=1, ge=1, le=MAX_PASSENGERS)
    # direction is inferred server-side from pickup location, not
    # accepted from the client — see app/services/geo.py:classify_direction


class BookingOut(BaseModel):
    id: uuid.UUID
    customer: CustomerOut

    pickup_address: str
    pickup_lat: float
    pickup_lng: float

    dropoff_address: str
    dropoff_lat: float
    dropoff_lng: float

    requested_pickup_at: datetime
    # Real per-stop estimates from the committed route (see
    # pool_insertion._best_ordering) — null until the pool seals and a
    # route is actually solved.
    estimated_pickup_at: datetime | None
    estimated_dropoff_at: datetime | None
    direction: BookingDirection
    is_private: bool
    seats: int
    status: BookingStatus
    trip_id: uuid.UUID | None
    created_at: datetime

    # --- Money: null for dispatchers, always ---
    # Dispatchers run the operation and have no business role in the
    # money, so these are stripped SERVER-SIDE rather than hidden in the
    # UI (see booking_service.to_booking_out). Admins see everything;
    # drivers see it on their own trips because they collect the cash
    # at the door and need to know what to ask for.
    #
    # Optional rather than a separate schema so one response model
    # serves every caller — the field is simply absent of content for
    # anyone not entitled to it, and no route can accidentally return
    # the wrong shape.
    price_vnd: int | None = None
    payment: PaymentOut | None = None

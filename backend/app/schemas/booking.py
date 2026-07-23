import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import BookingStatus
from app.schemas.customer import CustomerCreate, CustomerOut


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
    is_private: bool
    price_vnd: int
    status: BookingStatus
    trip_id: uuid.UUID | None
    created_at: datetime

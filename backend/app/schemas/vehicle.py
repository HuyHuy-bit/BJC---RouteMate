import uuid

from pydantic import BaseModel, Field

from app.core.dispatch_config import MAX_PASSENGERS
from app.models.enums import VehicleStatus


class VehicleCreate(BaseModel):
    plate_number: str = Field(min_length=4, max_length=20)
    label: str | None = Field(default=None, max_length=50)
    seat_capacity: int = Field(default=MAX_PASSENGERS, ge=1, le=16)
    default_driver_id: uuid.UUID | None = None


class VehicleUpdate(BaseModel):
    label: str | None = None
    status: VehicleStatus | None = None
    default_driver_id: uuid.UUID | None = None


class VehicleOut(BaseModel):
    id: uuid.UUID
    plate_number: str
    label: str | None
    seat_capacity: int
    status: VehicleStatus
    default_driver_id: uuid.UUID | None

    model_config = {"from_attributes": True}

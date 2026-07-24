import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import PaymentMethod, PaymentStatus


class PaymentOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    method: PaymentMethod
    expected_amount_vnd: int
    collected_amount_vnd: int | None
    status: PaymentStatus
    collected_by_user_id: uuid.UUID | None
    collected_at: datetime | None
    notes: str | None

    model_config = {"from_attributes": True}


class PaymentCollect(BaseModel):
    method: PaymentMethod = PaymentMethod.cash
    collected_amount_vnd: int = Field(ge=0)
    notes: str | None = Field(default=None, max_length=500)


class PaymentAdjust(BaseModel):
    status: PaymentStatus
    notes: str | None = Field(default=None, max_length=500)

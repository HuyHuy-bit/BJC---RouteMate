import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=20)


class CustomerOut(BaseModel):
    id: uuid.UUID
    # Optional, not required: null when the caller isn't entitled to
    # this booking's customer contact info — see
    # booking_service.may_see_customer_contact. Callers reaching a
    # customer directly via /customers (staff-only, see
    # routes/customers.py) always get real values.
    full_name: str | None
    phone: str | None
    created_at: datetime

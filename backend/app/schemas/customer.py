import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=20)


class CustomerOut(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    created_at: datetime

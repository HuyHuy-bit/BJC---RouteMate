import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    customer_name: str
    customer_phone: str
    event: str
    message: str
    status: str
    created_at: datetime

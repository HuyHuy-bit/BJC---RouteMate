import uuid

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DispatchEventType


class DispatchEvent(Base):
    """
    Append-only audit log for every dispatch decision.

    Needed the first time a customer disputes what happened, and needed
    continuously to tell whether the automation is making good calls —
    without this, an automated dispatcher is a black box nobody can
    check.
    """

    __tablename__ = "dispatch_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[DispatchEventType] = mapped_column(
        Enum(DispatchEventType, name="dispatch_event_type"), index=True
    )

    trip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Null actor == the automated engine decided this.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Scores, detour minutes, rejected alternatives — whatever explains
    # the decision later.
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

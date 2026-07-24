import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Notification(Base):
    """
    A message composed for a customer about their booking.

    There's no live SMS/Zalo integration wired up yet — no telecom
    credentials exist for this project. Rather than fake a "sent"
    confirmation that isn't true, every notification is logged here and
    exposed to staff so they can read and manually relay it (call or
    text) until a real channel is connected. `channel` and `status`
    exist so a real provider is a drop-in later: swap the log-only send
    in NotificationService for a real API call, and this table becomes a
    genuine delivery log instead of a manual-relay queue.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id"), index=True
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    event: Mapped[str] = mapped_column(String(50))  # sealed | driver_assigned | cancelled
    channel: Mapped[str] = mapped_column(String(20), default="manual")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending_manual_relay")

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    booking: Mapped["Booking"] = relationship()

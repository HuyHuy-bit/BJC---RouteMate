import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import PaymentMethod, PaymentStatus


class Payment(Base, TimestampMixin):
    """
    One booking's cash/payment record. Did not exist before — there was
    no way to know how much cash a driver should be holding at the end of
    a shift versus what trips they actually ran. One row per booking
    (not per trip), because in practice each passenger sharing a car pays
    their own fare individually, not the driver collecting one lump sum
    for the whole car.

    Created automatically alongside every booking (see
    booking_service.py:create_booking), starting `pending` at whatever
    `Booking.price_vnd` was at that moment — `expected_amount_vnd` is a
    snapshot, not a live reference, so it stays correct even if pricing
    logic changes later.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id"), unique=True, index=True
    )

    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method"), default=PaymentMethod.cash
    )
    expected_amount_vnd: Mapped[int] = mapped_column(Integer)
    collected_amount_vnd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.pending,
        index=True,
    )

    collected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="payment")

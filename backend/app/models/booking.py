import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import EncryptedString
from app.models.enums import BookingDirection, BookingStatus


class Booking(Base, TimestampMixin):
    """
    One customer's requested trip.

    Design note on encryption vs. PostGIS: the coordinate columns
    (pickup_point / dropoff_point) are stored in plaintext geography type,
    NOT encrypted — the matching algorithm needs PostGIS to run real
    ST_DWithin / ST_Distance queries directly against these columns, which
    is only possible on plaintext geometry. The free-text address strings
    (what the customer actually typed) ARE encrypted — DB columns are
    named *_address_encrypted, but the Python attributes are just
    pickup_address / dropoff_address (EncryptedString decrypts on read
    automatically), since they're only needed for human display, not
    spatial math. Protection for the coordinate data itself comes from
    access control + audit logging + encryption at rest on the database
    volume, not field-level app encryption. Documented in
    docs/DATA_PROTECTION.md.
    """

    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trips.id"), nullable=True
    )

    pickup_address: Mapped[str] = mapped_column(
        "pickup_address_encrypted", EncryptedString(255)
    )
    pickup_point = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )

    dropoff_address: Mapped[str] = mapped_column(
        "dropoff_address_encrypted", EncryptedString(255)
    )
    dropoff_point = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )

    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    price_vnd: Mapped[int] = mapped_column(Integer, default=0)
    requested_pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    direction: Mapped[BookingDirection] = mapped_column(
        Enum(BookingDirection, name="booking_direction")
    )

    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), default=BookingStatus.queued
    )
    stop_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="bookings")
    trip: Mapped["Trip | None"] = relationship(back_populates="bookings")

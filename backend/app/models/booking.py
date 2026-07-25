import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer
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
    corridor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridors.id"), index=True
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

    # How many physical seats this ONE booking occupies — a parent
    # booking for themselves plus two children is one booking worth
    # three seats, not three bookings. Capacity everywhere sums this
    # rather than counting booking rows (which silently treated that
    # family as a single passenger and would overfill the car).
    seats: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    requested_pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    direction: Mapped[BookingDirection] = mapped_column(
        Enum(
            BookingDirection,
            name="booking_direction",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        )
    )

    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"),
        default=BookingStatus.queued,
        index=True,
    )
    stop_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Direct point-to-point ride time for this booking alone, computed
    # once at creation and never recomputed (the address pair does not
    # change). Detour is measured as (in-car time) minus this baseline,
    # so the per-passenger service guarantee is only enforceable because
    # this is stored. Must come from
    # app/services/pool_insertion.py:compute_solo_baseline — a baseline
    # produced by any other method makes every detour figure meaningless.
    solo_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    solo_distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Filled when the pool seals, so the customer gets a firm ETA rather
    # than silence.
    estimated_pickup_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_dropoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer: Mapped["Customer"] = relationship(back_populates="bookings")
    trip: Mapped["Trip | None"] = relationship(back_populates="bookings")
    payment: Mapped["Payment | None"] = relationship(
        back_populates="booking", uselist=False
    )

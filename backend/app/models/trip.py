import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BookingDirection, TripStatus


class Trip(Base, TimestampMixin):
    """
    A vehicle's journey. While `forming`, this IS the ride pool — it
    accretes bookings until a seal trigger fires.

    Previously a Trip was created already-complete by a batch clustering
    run and then frozen, so a booking arriving one minute later could
    never join it even when it fit perfectly. Making the trip a
    long-lived, mutable pool is what allows continuous matching.
    """

    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    direction: Mapped[BookingDirection] = mapped_column(
        Enum(
            BookingDirection,
            name="booking_direction",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ), index=True
    )
    status: Mapped[TripStatus] = mapped_column(
        Enum(TripStatus, name="trip_status"),
        default=TripStatus.forming,
        index=True,
    )

    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id"), nullable=True
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    vehicle_label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Pool formation ---
    # The moment this pool must decide: depart, or escalate. Anchored to
    # the earliest requested pickup, so the promise belongs to whoever
    # has been waiting longest.
    departure_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    sealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cheap PostGIS pre-filter target: matching narrows candidate pools by
    # centroid proximity before spending any routing API call.
    centroid = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    # --- Computed route (refreshed on every insertion/removal) ---
    route_distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_geometry: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when the route was computed from fallback estimates because the
    # routing API was unavailable — surfaced so dispatchers know the ETAs
    # are softer than usual.
    route_is_estimate: Mapped[bool | None] = mapped_column(nullable=True)

    # When this trip actually finished (or was cancelled) — not inferred
    # from updated_at, which drifts if anything else touches the row
    # afterward. This is what the ride-history view is built on.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    bookings: Mapped[list["Booking"]] = relationship(back_populates="trip")

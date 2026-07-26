import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.dispatch_config import MAX_PASSENGERS
from app.db.base import Base, TimestampMixin
from app.models.enums import VehicleStatus


class Vehicle(Base, TimestampMixin):
    """
    A physical car in the fleet.

    This entity did not exist before, which meant the system could
    happily create twelve trips for a company that owns seven cars. It
    had no way to know that was impossible, and would have promised
    customers rides that could never run.
    """

    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plate_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seat_capacity: Mapped[int] = mapped_column(Integer, default=MAX_PASSENGERS)

    status: Mapped[VehicleStatus] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status"),
        default=VehicleStatus.available,
        index=True,
    )

    # Default driver; a trip may still override per-assignment.
    default_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # Which corridor this vehicle is based on, if known. Nullable on
    # purpose — an untagged vehicle stays assignable anywhere rather than
    # being excluded from dispatch over a tagging gap; see
    # dispatch_service.py:_assign_vehicle for how this is used to prefer
    # (not require) an in-corridor vehicle.
    home_corridor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridors.id"), nullable=True, index=True
    )

    # Last known position, for choosing the nearest available car.
    last_location = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    # When last_location was actually recorded — every write path (home-
    # base seed, trip-completion capture, dispatcher manual override,
    # driver location ping) sets this alongside last_location. Without
    # it there's no way to tell a fresh position from one a driver's
    # phone stopped sending an hour ago; see
    # dispatch_config.VEHICLE_LOCATION_STALE_MINUTES.
    last_location_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Return to base ---
    # Every car is stationed at its corridor's home hub overnight, so a
    # car that ends the day in Hà Nội has to get back to Bắc Giang. A
    # dispatcher can also call one home early when Hà Nội has no demand
    # left. Both write these; the driver confirming arrival clears them.
    #
    # Nullable and paired: a non-null return_requested_at is the entire
    # definition of "a return is outstanding", so there is no way for
    # the flag and the status to disagree about whether one exists.
    return_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Null when the end-of-day sweep raised it rather than a person —
    # the same "is_automatic" distinction dispatch_events already makes.
    return_requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

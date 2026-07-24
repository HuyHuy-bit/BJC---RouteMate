import uuid

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Corridor(Base, TimestampMixin):
    """
    One named route this business actually runs, e.g. "Bắc Giang ⇄ Hà Nội".

    Direction classification, pool matching, return-vehicle reuse, and
    pricing all used to assume there was exactly one of these, hard-coded
    as two module-level constants in app/services/geo.py. That made every
    booking on a different real corridor (Hà Nội ↔ Hải Phòng, etc.)
    silently misclassify rather than error. This table is what makes
    "which corridor" a real, queryable fact instead of a geometric
    coincidence — see app/services/corridors.py for how a booking is
    matched to one.
    """

    __tablename__ = "corridors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), unique=True)

    # The depot/base end. "return" means heading back toward this hub —
    # see classify_direction in app/services/geo.py for the exact
    # semantics this feeds.
    home_hub_name: Mapped[str] = mapped_column(String(80))
    home_hub_lat: Mapped[float] = mapped_column(Float)
    home_hub_lng: Mapped[float] = mapped_column(Float)

    away_hub_name: Mapped[str] = mapped_column(String(80))
    away_hub_lat: Mapped[float] = mapped_column(Float)
    away_hub_lng: Mapped[float] = mapped_column(Float)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Flat fare for this corridor, regardless of exactly where within it
    # a passenger boards/alights — deliberately NOT distance-scaled. An
    # earlier version of this made price grow with distance, which is
    # more "correct" on paper but broke the thing that actually made
    # this business work: a customer can quote the price from memory
    # before they even open the app, with zero ambiguity, every time.
    # See app/core/pricing.py:price_for.
    base_fare_vnd: Mapped[int] = mapped_column(Integer)

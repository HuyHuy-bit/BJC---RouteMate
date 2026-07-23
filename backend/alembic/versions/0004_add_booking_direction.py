"""add direction to bookings (outbound vs return leg)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23

Bắc Giang <-> Hà Nội is a fixed two-hub corridor, so direction is
inferred from whichever hub the pickup point is closer to, using
PostGIS ST_Distance directly in SQL for the backfill (matches the same
haversine-equivalent geography distance the app uses in Python via
app/services/geo.py:classify_direction).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BAC_GIANG_LAT, BAC_GIANG_LNG = 21.2731, 106.1946
HA_NOI_LAT, HA_NOI_LNG = 21.0285, 105.8542


def upgrade() -> None:
    booking_direction = postgresql.ENUM(
        "outbound", "return", name="booking_direction"
    )
    booking_direction.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "bookings",
        sa.Column(
            "direction",
            booking_direction,
            nullable=True,  # filled in below, then locked to NOT NULL
        ),
    )

    op.execute(
        f"""
        UPDATE bookings SET direction = CASE
          WHEN ST_Distance(
                 pickup_point,
                 ST_SetSRID(ST_MakePoint({BAC_GIANG_LNG}, {BAC_GIANG_LAT}), 4326)::geography
               )
               <=
               ST_Distance(
                 pickup_point,
                 ST_SetSRID(ST_MakePoint({HA_NOI_LNG}, {HA_NOI_LAT}), 4326)::geography
               )
          THEN 'outbound'::booking_direction
          ELSE 'return'::booking_direction
        END
        """
    )

    op.alter_column("bookings", "direction", nullable=False)
    op.create_index("ix_bookings_direction", "bookings", ["direction"])


def downgrade() -> None:
    op.drop_index("ix_bookings_direction", table_name="bookings")
    op.drop_column("bookings", "direction")
    postgresql.ENUM(name="booking_direction").drop(op.get_bind(), checkfirst=True)

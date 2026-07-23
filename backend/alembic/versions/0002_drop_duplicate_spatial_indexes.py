"""drop duplicate geoalchemy2 auto-created spatial indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10

GeoAlchemy2 auto-creates a spatial index on Geography columns by default
(named idx_<table>_<column>), which duplicated the ix_bookings_* indexes
already created explicitly in 0001. The model now sets
spatial_index=False to prevent this going forward; this migration cleans
up the duplicates that already exist.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bookings_pickup_point")
    op.execute("DROP INDEX IF EXISTS idx_bookings_dropoff_point")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX idx_bookings_pickup_point ON bookings USING gist (pickup_point)"
    )
    op.execute(
        "CREATE INDEX idx_bookings_dropoff_point ON bookings USING gist (dropoff_point)"
    )

"""add vehicles.last_location_at

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-24

Vehicle.last_location has existed for a while, but with no timestamp
there was no way to distinguish a fresh position from a stale one — see
dispatch_config.VEHICLE_LOCATION_STALE_MINUTES and
dispatch_service._assign_vehicle, which now treats an old
last_location_at the same as no location at all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("vehicles", "last_location_at"):
        op.add_column(
            "vehicles",
            sa.Column("last_location_at", sa.DateTime(timezone=True), nullable=True),
        )
    # Any vehicle that already has a last_location (from the home-base
    # seed or an earlier trip-completion capture, before this column
    # existed) gets backfilled to "now" rather than left NULL — NULL
    # would make an already-known position look identical to "never
    # recorded", which is the exact ambiguity this column exists to
    # remove. "Now" is a conservative choice: it's honest about not
    # knowing exactly when it was set, and treats it as fresh rather
    # than immediately stale.
    op.execute(
        "UPDATE vehicles SET last_location_at = now() "
        "WHERE last_location IS NOT NULL AND last_location_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("vehicles", "last_location_at")

"""add trips.solved_booking_ids and solved_vehicle_id

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-24

Lets _refresh_pool_geometry skip re-solving (no routing calls, no
re-derivation) when membership and the anchoring vehicle are both
unchanged since the last solve, instead of recomputing on every call
regardless of whether anything actually changed. Nullable on purpose —
NULL just means "never solved yet", correctly forcing a solve the first
time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("trips", "solved_booking_ids"):
        op.add_column(
            "trips", sa.Column("solved_booking_ids", postgresql.JSONB, nullable=True)
        )
    if not _column_exists("trips", "solved_vehicle_id"):
        op.add_column(
            "trips",
            sa.Column(
                "solved_vehicle_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
    # Left NULL for existing trips on purpose — the next
    # _refresh_pool_geometry call for each will correctly treat that as
    # "never solved, must solve", which is harmless (worst case: one
    # extra solve per trip that was already going to happen anyway).


def downgrade() -> None:
    op.drop_column("trips", "solved_vehicle_id")
    op.drop_column("trips", "solved_booking_ids")

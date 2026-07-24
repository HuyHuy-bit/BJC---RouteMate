"""add trip completed_at and cancelled_at

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("trips", "completed_at"):
        op.add_column(
            "trips", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.create_index("ix_trips_completed_at", "trips", ["completed_at"])
    if not _column_exists("trips", "cancelled_at"):
        op.add_column(
            "trips", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
        )

    # Backfill: any trip already sitting completed/cancelled from before
    # this column existed gets a reasonable timestamp (its last update)
    # rather than a permanent NULL that would hide it from date-based
    # history views.
    op.execute(
        "UPDATE trips SET completed_at = updated_at "
        "WHERE status = 'completed' AND completed_at IS NULL"
    )
    op.execute(
        "UPDATE trips SET cancelled_at = updated_at "
        "WHERE status = 'cancelled' AND cancelled_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_trips_completed_at", table_name="trips")
    op.drop_column("trips", "cancelled_at")
    op.drop_column("trips", "completed_at")

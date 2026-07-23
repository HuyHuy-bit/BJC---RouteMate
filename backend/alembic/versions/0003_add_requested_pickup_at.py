"""add requested_pickup_at to bookings

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column(
            "requested_pickup_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_bookings_requested_pickup_at", "bookings", ["requested_pickup_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_requested_pickup_at", table_name="bookings")
    op.drop_column("bookings", "requested_pickup_at")

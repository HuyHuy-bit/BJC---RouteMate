"""add notifications table

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _table_exists("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "booking_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("bookings.id"),
                nullable=False,
            ),
            sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("event", sa.String(50), nullable=False),
            sa.Column("channel", sa.String(20), nullable=False, server_default="manual"),
            sa.Column("message", sa.Text, nullable=False),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="pending_manual_relay",
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
        )
        op.create_index("ix_notifications_booking_id", "notifications", ["booking_id"])
        op.create_index("ix_notifications_trip_id", "notifications", ["trip_id"])
        op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")

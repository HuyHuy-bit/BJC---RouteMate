"""add payments

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-24

There was no payment/cash/invoice concept anywhere in the schema before
this — `Booking.price_vnd` said what was owed, but nothing recorded
whether or how it was actually collected. One row per booking (not per
trip): in practice each passenger sharing a car pays their own fare
individually, not the driver collecting one lump sum for the car.

Existing bookings are backfilled with a `pending` payment snapshotting
their current `price_vnd`, so no historical booking is left without a
payment record once this ships.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _index_exists(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def _safe_create_index(name: str, table: str, cols: list, **kw) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, cols, **kw)


def upgrade() -> None:
    bind = op.get_bind()

    # Create the types explicitly, then reference them with
    # create_type=False below — same reasoning as 0005's vehicle_status /
    # dispatch_event_type: passing a "live" ENUM to create_table makes
    # SQLAlchemy emit a second CREATE TYPE and fail with DuplicateObject.
    postgresql.ENUM(
        "cash", "bank_transfer", "other", name="payment_method"
    ).create(bind, checkfirst=True)
    payment_method = postgresql.ENUM(name="payment_method", create_type=False)

    postgresql.ENUM(
        "pending", "collected", "disputed", "waived", name="payment_status"
    ).create(bind, checkfirst=True)
    payment_status = postgresql.ENUM(name="payment_status", create_type=False)

    if not _table_exists("payments"):
        op.create_table(
            "payments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "booking_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("bookings.id"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "method", payment_method, nullable=False, server_default="cash"
            ),
            sa.Column("expected_amount_vnd", sa.Integer, nullable=False),
            sa.Column("collected_amount_vnd", sa.Integer, nullable=True),
            sa.Column(
                "status", payment_status, nullable=False, server_default="pending"
            ),
            sa.Column(
                "collected_by_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
        )
    _safe_create_index("ix_payments_booking_id", "payments", ["booking_id"])
    _safe_create_index("ix_payments_status", "payments", ["status"])

    # Backfill: every booking that predates this table gets a `pending`
    # payment snapshotting its current price, rather than being left with
    # no payment record at all. gen_random_uuid() is built into Postgres
    # core since v13 (this deployment runs 16), no extension needed.
    op.execute(
        """
        INSERT INTO payments
            (id, booking_id, method, expected_amount_vnd, status, created_at, updated_at)
        SELECT gen_random_uuid(), b.id, 'cash', b.price_vnd, 'pending', now(), now()
        FROM bookings b
        WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.booking_id = b.id)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_table("payments")

    bind = op.get_bind()
    postgresql.ENUM(name="payment_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="payment_method").drop(bind, checkfirst=True)

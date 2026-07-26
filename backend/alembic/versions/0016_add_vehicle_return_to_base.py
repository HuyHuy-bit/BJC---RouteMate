"""add return-to-base state for vehicles

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-26

Every vehicle is based at its corridor's home hub (Bắc Giang) and is
stationed there overnight. A car that finishes its last run in Hà Nội
therefore has to get home — either because a dispatcher calls it back
when Hà Nội has no demand left, or because the operating day ended.

  vehicle_status      += returning
  dispatch_event_type += return_requested, return_confirmed,
                         return_cancelled
  vehicles            += return_requested_at, return_requested_by_user_id

Home base itself needs no new column. Corridor already stores
home_hub_lat/lng and vehicles already carry home_corridor_id, so the
base is derivable — and deliberately stays derived. The Corridor table
exists precisely because the hubs used to be hardcoded constants in
geo.py, which silently misclassified every booking on a second route.
Hardcoding "Bắc Giang" again here would walk straight back into that.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_DISPATCH_EVENTS = (
    "return_requested",
    "return_confirmed",
    "return_cancelled",
)
NEW_VEHICLE_COLUMNS = ("return_requested_at", "return_requested_by_user_id")


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't be used later in the transaction
    # that adds it — same reasoning as 0005, 0011 and 0015.
    op.execute("COMMIT")

    op.execute("ALTER TYPE vehicle_status ADD VALUE IF NOT EXISTS 'returning'")
    for value in NEW_DISPATCH_EVENTS:
        op.execute(
            f"ALTER TYPE dispatch_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )

    if not _column_exists("vehicles", "return_requested_at"):
        op.add_column(
            "vehicles",
            sa.Column("return_requested_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _column_exists("vehicles", "return_requested_by_user_id"):
        op.add_column(
            "vehicles",
            sa.Column(
                "return_requested_by_user_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        # SET NULL rather than RESTRICT: who asked for a car to come
        # home must never be the reason a staff account can't be
        # deleted. Same call as trips.finalized_by_user_id in 0015.
        op.create_foreign_key(
            "fk_vehicles_return_requested_by_user_id",
            "vehicles",
            "users",
            ["return_requested_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _column_exists("vehicles", "return_requested_by_user_id"):
        op.drop_constraint(
            "fk_vehicles_return_requested_by_user_id", "vehicles", type_="foreignkey"
        )
    for column in NEW_VEHICLE_COLUMNS:
        if _column_exists("vehicles", column):
            op.drop_column("vehicles", column)

    # Any vehicle left mid-return has to land somewhere valid before the
    # enum value goes away, or the rows become unreadable. `available`
    # is the honest choice: without the columns above there is no longer
    # a record that a return was outstanding.
    op.execute("UPDATE vehicles SET status = 'available' WHERE status = 'returning'")

    # PostgreSQL cannot drop a value from an enum type in use, so
    # 'returning' and the three event types stay behind — same as every
    # other enum addition in this project's history. Harmless once no
    # row references them.

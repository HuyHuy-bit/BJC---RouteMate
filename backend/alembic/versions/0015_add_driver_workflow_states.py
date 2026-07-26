"""add driver-accept / completion-request workflow states

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-26

Splits trip completion into a driver's claim and a dispatcher's ruling,
which is what the business actually does: the person who drove the car
says they finished, and a dispatcher confirms it before the trip counts
as done and the vehicle's location is trusted. See
docs/STATE_MACHINE.md.

Three enum changes:

  trip_status        += driver_accepted, completion_requested
  vehicle_status     += assigned, and inactive RENAMED to offline
  dispatch_event_type += driver_accepted, completion_requested,
                         completion_rejected, trip_finalized

`vehicle_status.inactive -> offline` is a rename rather than an
add-plus-backfill: no row's meaning changes, only the word. ALTER TYPE
... RENAME VALUE rewrites it in place with no table scan, so existing
rows stay valid without being touched.

Deliberately NO backfill of in-flight trips. An earlier draft stamped
every currently-`assigned` trip as `driver_accepted` so drivers
wouldn't have to tap Accept on work already in their hands. That would
have written an acceptance that never happened into the audit trail —
and this whole migration exists to make that trail trustworthy. A
driver taps Accept once. The record stays true.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_TRIP_STATUSES = ("driver_accepted", "completion_requested")
NEW_DISPATCH_EVENTS = (
    "driver_accepted",
    "completion_requested",
    "completion_rejected",
    "trip_finalized",
)
NEW_TRIP_COLUMNS = (
    "driver_accepted_at",
    "completion_requested_at",
    "finalized_at",
    "finalized_by_user_id",
)


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _enum_has_value(type_name: str, value: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :t AND e.enumlabel = :v"
            ),
            {"t": type_name, "v": value},
        )
        .first()
    )


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot be used later in the same
    # transaction that adds it — same reasoning as 0005 and 0011.
    op.execute("COMMIT")

    for value in NEW_TRIP_STATUSES:
        op.execute(f"ALTER TYPE trip_status ADD VALUE IF NOT EXISTS '{value}'")
    for value in NEW_DISPATCH_EVENTS:
        op.execute(
            f"ALTER TYPE dispatch_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )
    op.execute("ALTER TYPE vehicle_status ADD VALUE IF NOT EXISTS 'assigned'")

    # RENAME VALUE has no IF NOT EXISTS form, so guard it explicitly —
    # otherwise re-running a partially-applied migration errors out.
    if _enum_has_value("vehicle_status", "inactive"):
        op.execute("ALTER TYPE vehicle_status RENAME VALUE 'inactive' TO 'offline'")

    for column in ("driver_accepted_at", "completion_requested_at", "finalized_at"):
        if not _column_exists("trips", column):
            op.add_column(
                "trips",
                sa.Column(column, sa.DateTime(timezone=True), nullable=True),
            )

    if not _column_exists("trips", "finalized_by_user_id"):
        op.add_column(
            "trips",
            sa.Column(
                "finalized_by_user_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        # SET NULL, not RESTRICT: users.py already clears trips.driver_id
        # when a staff account is deleted. A finalization record that
        # blocked account deletion forever would be a worse outcome than
        # one that loses the reviewer's name.
        op.create_foreign_key(
            "fk_trips_finalized_by_user_id",
            "trips",
            "users",
            ["finalized_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _column_exists("trips", "finalized_by_user_id"):
        op.drop_constraint("fk_trips_finalized_by_user_id", "trips", type_="foreignkey")
    for column in NEW_TRIP_COLUMNS:
        if _column_exists("trips", column):
            op.drop_column("trips", column)

    # The rename IS reversible, unlike the additions.
    op.execute("COMMIT")
    if _enum_has_value("vehicle_status", "offline"):
        op.execute("ALTER TYPE vehicle_status RENAME VALUE 'offline' TO 'inactive'")

    # PostgreSQL cannot drop a single value from an enum type in use, so
    # the added trip_status/dispatch_event_type/vehicle_status values
    # stay behind — same as every other enum addition in this project's
    # migration history. Harmless: nothing references them once the
    # rows above are gone.

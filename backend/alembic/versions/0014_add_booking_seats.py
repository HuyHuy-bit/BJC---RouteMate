"""add bookings.seats and make the capacity trigger seat-aware

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-25

A booking can now represent more than one physical seat (a parent
booking for themselves plus two children is ONE booking worth THREE
seats). That makes every "is this car full?" check that counted booking
ROWS wrong — including, most importantly, the enforce_trip_capacity
trigger from 0005, which is the only thing that actually prevents an
overbooking race at the database level. It counted rows; a 3-seat
family booking would have slipped straight past it. Rewritten here to
sum seats, and to account for the incoming booking's own seat count
rather than assuming it occupies exactly one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("bookings", "seats"):
        op.add_column(
            "bookings",
            sa.Column(
                "seats", sa.Integer, nullable=False, server_default="1"
            ),
        )

    # Seat-aware replacement for 0005's row-counting version. Note the
    # comparison also changed shape: the old check was
    # `existing_rows >= cap` (correct only because every booking was
    # implicitly 1 seat); this is `existing_seats + NEW.seats > cap`,
    # which reduces to exactly the same thing when all seats are 1.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_trip_capacity()
        RETURNS TRIGGER AS $$
        DECLARE
            current_seats INTEGER;
            cap INTEGER;
        BEGIN
            IF NEW.trip_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT COALESCE(v.seat_capacity, 4) INTO cap
            FROM trips t
            LEFT JOIN vehicles v ON v.id = t.vehicle_id
            WHERE t.id = NEW.trip_id;

            SELECT COALESCE(SUM(seats), 0) INTO current_seats
            FROM bookings
            WHERE trip_id = NEW.trip_id
              AND id <> NEW.id
              AND status NOT IN ('cancelled', 'no_show');

            IF current_seats + NEW.seats > cap THEN
                RAISE EXCEPTION
                    'trip % is full (% of % seats, booking needs %)',
                    NEW.trip_id, current_seats, cap, NEW.seats;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    # Restore 0005's row-counting version verbatim, so this migration is
    # genuinely reversible rather than leaving a seat-aware trigger
    # behind reading a column that no longer exists.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_trip_capacity()
        RETURNS TRIGGER AS $$
        DECLARE
            current_count INTEGER;
            cap INTEGER;
        BEGIN
            IF NEW.trip_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT COALESCE(v.seat_capacity, 4) INTO cap
            FROM trips t
            LEFT JOIN vehicles v ON v.id = t.vehicle_id
            WHERE t.id = NEW.trip_id;

            SELECT COUNT(*) INTO current_count
            FROM bookings
            WHERE trip_id = NEW.trip_id
              AND id <> NEW.id
              AND status NOT IN ('cancelled', 'no_show');

            IF current_count >= cap THEN
                RAISE EXCEPTION
                    'trip % is full (% of % seats)', NEW.trip_id, current_count, cap;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.drop_column("bookings", "seats")

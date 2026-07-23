"""add vehicles, dispatch events, pool fields, booking baselines

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23

Adds the fleet and dispatch-automation layer:
  - vehicles          (the system previously had no idea the company
                       owns 7 cars, and could invent a 12th)
  - dispatch_events   (audit trail for automated decisions)
  - trips.*           (pool formation: deadline, centroid, route cache)
  - bookings.*        (solo baselines, which make the per-passenger
                       detour guarantee enforceable at all)

Enum values are added with ALTER TYPE rather than by recreating the
types, because existing rows already reference them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_BOOKING_STATUSES = ["locked", "onboard", "completed", "no_show"]
NEW_TRIP_STATUSES = ["sealed", "assigned", "reassigning"]


def upgrade() -> None:
    bind = op.get_bind()

    # --- Extend existing enums in place -------------------------------
    # ALTER TYPE ... ADD VALUE historically could not run inside a
    # transaction block. PG 12+ allows it, but Alembic wraps migrations in
    # a transaction and the new value is not usable in the SAME
    # transaction that adds it — which this migration needs, because the
    # backfill below references trips.direction. Committing first makes
    # both concerns moot.
    op.execute("COMMIT")
    for value in NEW_BOOKING_STATUSES:
        op.execute(f"ALTER TYPE booking_status ADD VALUE IF NOT EXISTS '{value}'")
    for value in NEW_TRIP_STATUSES:
        op.execute(f"ALTER TYPE trip_status ADD VALUE IF NOT EXISTS '{value}'")

    vehicle_status = postgresql.ENUM(
        "available", "on_trip", "maintenance", "inactive", name="vehicle_status"
    )
    vehicle_status.create(bind, checkfirst=True)

    dispatch_event_type = postgresql.ENUM(
        "pool_created",
        "booking_pooled",
        "booking_removed",
        "pool_sealed",
        "pool_escalated",
        "pool_merged",
        "vehicle_assigned",
        "trip_started",
        "trip_completed",
        "trip_cancelled",
        "driver_rejected",
        "manual_override",
        name="dispatch_event_type",
    )
    dispatch_event_type.create(bind, checkfirst=True)

    # --- vehicles -----------------------------------------------------
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plate_number", sa.String(20), nullable=False, unique=True),
        sa.Column("label", sa.String(50), nullable=True),
        sa.Column("seat_capacity", sa.Integer, nullable=False, server_default="4"),
        sa.Column(
            "status", vehicle_status, nullable=False, server_default="available"
        ),
        sa.Column(
            "default_driver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "last_location",
            geoalchemy2.Geography(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_vehicles_plate_number", "vehicles", ["plate_number"])
    op.create_index("ix_vehicles_status", "vehicles", ["status"])

    # --- dispatch_events ----------------------------------------------
    op.create_table(
        "dispatch_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", dispatch_event_type, nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_automatic", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dispatch_events_event_type", "dispatch_events", ["event_type"])
    op.create_index("ix_dispatch_events_trip_id", "dispatch_events", ["trip_id"])
    op.create_index("ix_dispatch_events_booking_id", "dispatch_events", ["booking_id"])
    op.create_index("ix_dispatch_events_created_at", "dispatch_events", ["created_at"])

    # --- trips: pool formation ----------------------------------------
    op.add_column(
        "trips",
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "trips",
        sa.Column("direction", postgresql.ENUM(name="booking_direction", create_type=False), nullable=True),
    )
    op.add_column(
        "trips",
        sa.Column("departure_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("trips", sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "trips",
        sa.Column(
            "centroid",
            geoalchemy2.Geography(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
    )
    op.add_column("trips", sa.Column("route_distance_meters", sa.Float, nullable=True))
    op.add_column("trips", sa.Column("route_duration_seconds", sa.Float, nullable=True))
    op.add_column("trips", sa.Column("route_geometry", sa.Text, nullable=True))
    op.add_column("trips", sa.Column("route_is_estimate", sa.Boolean, nullable=True))

    op.create_index("ix_trips_status", "trips", ["status"])
    op.create_index("ix_trips_direction", "trips", ["direction"])
    op.create_index("ix_trips_departure_deadline", "trips", ["departure_deadline"])
    # GiST index on centroid is what makes the cheap candidate-pool
    # prefilter fast enough to run before any routing API call.
    op.create_index(
        "ix_trips_centroid", "trips", ["centroid"], postgresql_using="gist"
    )

    # Backfill direction on existing trips from their bookings, so old
    # rows are not left with a null that breaks direction filtering.
    op.execute(
        """
        UPDATE trips t
        SET direction = sub.direction
        FROM (
            SELECT DISTINCT ON (trip_id) trip_id, direction
            FROM bookings
            WHERE trip_id IS NOT NULL
        ) sub
        WHERE t.id = sub.trip_id AND t.direction IS NULL
        """
    )
    # Any trip with no bookings at all cannot be classified; default it
    # rather than leaving NULL.
    op.execute(
        "UPDATE trips SET direction = 'outbound' WHERE direction IS NULL"
    )
    op.alter_column("trips", "direction", nullable=False)

    # --- bookings: baselines + ETAs -----------------------------------
    op.add_column("bookings", sa.Column("solo_duration_seconds", sa.Float, nullable=True))
    op.add_column("bookings", sa.Column("solo_distance_meters", sa.Float, nullable=True))
    op.add_column(
        "bookings",
        sa.Column("estimated_pickup_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("estimated_dropoff_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bookings_trip_id", "bookings", ["trip_id"])

    # --- overbooking guard --------------------------------------------
    # Application-level capacity checks lose to a race between two
    # concurrent inserts taking the last seat. This makes it impossible
    # at the database, which is the only layer that can actually
    # guarantee it.
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
    op.execute(
        """
        CREATE TRIGGER trg_enforce_trip_capacity
        BEFORE INSERT OR UPDATE OF trip_id ON bookings
        FOR EACH ROW EXECUTE FUNCTION enforce_trip_capacity();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_trip_capacity ON bookings")
    op.execute("DROP FUNCTION IF EXISTS enforce_trip_capacity()")

    op.drop_index("ix_bookings_trip_id", table_name="bookings")
    for col in (
        "estimated_dropoff_at",
        "estimated_pickup_at",
        "solo_distance_meters",
        "solo_duration_seconds",
    ):
        op.drop_column("bookings", col)

    for idx in (
        "ix_trips_centroid",
        "ix_trips_departure_deadline",
        "ix_trips_direction",
        "ix_trips_status",
    ):
        op.drop_index(idx, table_name="trips")
    for col in (
        "route_is_estimate",
        "route_geometry",
        "route_duration_seconds",
        "route_distance_meters",
        "centroid",
        "sealed_at",
        "departure_deadline",
        "direction",
        "vehicle_id",
    ):
        op.drop_column("trips", col)

    op.drop_table("dispatch_events")
    op.drop_table("vehicles")

    bind = op.get_bind()
    postgresql.ENUM(name="dispatch_event_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="vehicle_status").drop(bind, checkfirst=True)
    # Enum VALUES added above are intentionally not removed: PostgreSQL
    # cannot drop a value from a type in use, and leaving them is
    # harmless.

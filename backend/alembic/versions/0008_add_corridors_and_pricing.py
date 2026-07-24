"""add corridors, seed the live route, tag bookings/trips/vehicles

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-24

Direction classification, pool matching, return-vehicle reuse, and
pricing all used to assume there was exactly one corridor, hard-coded as
two module-level coordinates in app/services/geo.py. This makes
"which corridor" a real, queryable table instead — see
app/models/corridor.py and app/services/corridors.py.

Only one corridor actually runs today (Hà Nội ⇄ Bắc Giang), so this
migration seeds exactly that one, using the same hub coordinates already
used for the one-time direction backfill in 0004, so behavior is
unchanged at launch. A second corridor is just a new row later — no
further migration needed for that.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same coordinates as 0004_add_booking_direction.py and the original
# app/services/geo.py module constants.
BAC_GIANG_LAT, BAC_GIANG_LNG = 21.2731, 106.1946
HA_NOI_LAT, HA_NOI_LNG = 21.0285, 105.8542

# Fixed so this migration is idempotent-safe and the seed row is
# identifiable/reproducible rather than a fresh random id every run.
SEED_CORRIDOR_ID = "8f3f9a2e-0000-4000-8000-000000000001"
SEED_CORRIDOR_NAME = "Bắc Giang ⇄ Hà Nội"

# base_fare_vnd + per_km_vnd chosen so a full ~50km corridor ride still
# lands at ~150,000₫ — the flat price this replaces — while shorter
# segments now correctly cost less. See app/core/pricing.py.
SEED_BASE_FARE_VND = 50_000
SEED_PER_KM_VND = 2_000


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def _safe_add_column(table: str, column: sa.Column) -> None:
    if not _column_exists(table, column.name):
        op.add_column(table, column)


def _safe_create_index(name: str, table: str, cols: list, **kw) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, cols, **kw)


def upgrade() -> None:
    # --- corridors ------------------------------------------------------
    if not _table_exists("corridors"):
        op.create_table(
            "corridors",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("home_hub_name", sa.String(80), nullable=False),
            sa.Column("home_hub_lat", sa.Float, nullable=False),
            sa.Column("home_hub_lng", sa.Float, nullable=False),
            sa.Column("away_hub_name", sa.String(80), nullable=False),
            sa.Column("away_hub_lat", sa.Float, nullable=False),
            sa.Column("away_hub_lng", sa.Float, nullable=False),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("base_fare_vnd", sa.Integer, nullable=False),
            sa.Column("per_km_vnd", sa.Integer, nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
        )

    existing = op.get_bind().execute(
        sa.text("SELECT 1 FROM corridors WHERE name = :name"),
        {"name": SEED_CORRIDOR_NAME},
    ).first()
    if existing is None:
        op.execute(
            sa.text(
                """
                INSERT INTO corridors
                    (id, name, home_hub_name, home_hub_lat, home_hub_lng,
                     away_hub_name, away_hub_lat, away_hub_lng,
                     is_active, base_fare_vnd, per_km_vnd)
                VALUES
                    (CAST(:id AS uuid), :name, :home_name, :home_lat, :home_lng,
                     :away_name, :away_lat, :away_lng,
                     true, :base_fare, :per_km)
                """
            ).bindparams(
                id=SEED_CORRIDOR_ID,
                name=SEED_CORRIDOR_NAME,
                home_name="Bắc Giang",
                home_lat=BAC_GIANG_LAT,
                home_lng=BAC_GIANG_LNG,
                away_name="Hà Nội",
                away_lat=HA_NOI_LAT,
                away_lng=HA_NOI_LNG,
                base_fare=SEED_BASE_FARE_VND,
                per_km=SEED_PER_KM_VND,
            )
        )

    # --- bookings.corridor_id / trips.corridor_id (required) -----------
    for table in ("bookings", "trips"):
        _safe_add_column(
            table,
            sa.Column(
                "corridor_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("corridors.id"),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                f"UPDATE {table} SET corridor_id = CAST(:id AS uuid) WHERE corridor_id IS NULL"
            ).bindparams(id=SEED_CORRIDOR_ID)
        )
        op.alter_column(table, "corridor_id", nullable=False)
        _safe_create_index(f"ix_{table}_corridor_id", table, ["corridor_id"])

    # --- vehicles.home_corridor_id (optional) ---------------------------
    _safe_add_column(
        "vehicles",
        sa.Column(
            "home_corridor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("corridors.id"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE vehicles SET home_corridor_id = CAST(:id AS uuid) "
            "WHERE home_corridor_id IS NULL"
        ).bindparams(id=SEED_CORRIDOR_ID)
    )
    _safe_create_index("ix_vehicles_home_corridor_id", "vehicles", ["home_corridor_id"])


def downgrade() -> None:
    op.drop_index("ix_vehicles_home_corridor_id", table_name="vehicles")
    op.drop_column("vehicles", "home_corridor_id")

    for table in ("trips", "bookings"):
        op.drop_index(f"ix_{table}_corridor_id", table_name=table)
        op.drop_column(table, "corridor_id")

    op.drop_table("corridors")

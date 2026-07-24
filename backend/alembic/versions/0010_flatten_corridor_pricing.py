"""flatten corridor pricing (drop per-km rate)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-24

Corridor pricing briefly grew with distance (base_fare_vnd + per_km_vnd
* km). Reverted on the operator's explicit call: flat, memorizable
pricing is part of what makes this business work, not a simplification
worth trading away for "more correct" per-km math. base_fare_vnd is now
the WHOLE flat fare, not just a floor — the seeded corridor's rate goes
from 50,000 (base only) back to 150,000 (the actual flat price), and
per_km_vnd is dropped since nothing reads it anymore.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FLAT_FARE_VND = 150_000

# Prior values, kept here only so downgrade() can restore them exactly.
PRIOR_BASE_FARE_VND = 50_000
PRIOR_PER_KM_VND = 2_000


def _column_exists(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    op.execute(f"UPDATE corridors SET base_fare_vnd = {FLAT_FARE_VND}")
    if _column_exists("corridors", "per_km_vnd"):
        op.drop_column("corridors", "per_km_vnd")


def downgrade() -> None:
    if not _column_exists("corridors", "per_km_vnd"):
        op.add_column(
            "corridors",
            sa.Column(
                "per_km_vnd",
                sa.Integer,
                nullable=False,
                server_default=str(PRIOR_PER_KM_VND),
            ),
        )
    op.execute(f"UPDATE corridors SET base_fare_vnd = {PRIOR_BASE_FARE_VND}")

"""add pool_reclustered dispatch event type

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-24

Supports the new periodic re-clustering pass (see
app/services/reclustering.py, app/services/dispatch_service.py:
recluster_forming_pools) which regroups still-forming pools by pickup
time first, then geographic proximity — this is the event type logged
whenever it actually moves a booking between pools.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't be used later in the same
    # transaction it runs in — same reasoning as 0005_add_fleet_and_dispatch.py.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE dispatch_event_type ADD VALUE IF NOT EXISTS 'pool_reclustered'"
    )


def downgrade() -> None:
    # PostgreSQL cannot drop a single value from an enum type in use —
    # same as every other enum-value addition in this project's
    # migration history. Harmless to leave in place.
    pass

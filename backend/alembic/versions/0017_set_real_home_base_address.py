"""Point the home hub at the company's actual base address.

The seeded home hub was a generic "Bắc Giang" city-centre coordinate,
good enough while nothing depended on precisely where the depot was.
Several things now do: is_at_base decides whether to send a car home,
the end-of-day sweep decides what counts as already parked, and stop
ordering falls back to anchoring the route at base when a car has no
fresh GPS fix. All three deserve the real address rather than a point
somewhere near it.

The move is small — about 90 m — so no dispatch decision changes today
(AT_BASE_RADIUS_METERS is 3 km, and corridor tolerances are in
kilometres). It is recorded because a base address that is merely
approximately right is the kind of thing nobody re-checks later.

Revision ID: 0017
Revises: 0016
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_CORRIDOR_ID = "8f3f9a2e-0000-4000-8000-000000000001"

# 167 Xương Giang, Bắc Giang — the operating base.
BASE_NAME = "167 Xương Giang, Bắc Giang"
BASE_LAT = 21.2739
BASE_LNG = 106.1948

PRIOR_NAME = "Bắc Giang"
PRIOR_LAT = 21.2731
PRIOR_LNG = 106.1946


def _set(name: str, lat: float, lng: float) -> None:
    # Scoped to the seeded corridor by id: a second corridor added later
    # has its own base and must not be dragged to this one.
    op.execute(
        sa.text(
            """
            UPDATE corridors
               SET home_hub_name = :name,
                   home_hub_lat  = :lat,
                   home_hub_lng  = :lng
             WHERE id = CAST(:id AS uuid)
            """
        ).bindparams(id=SEED_CORRIDOR_ID, name=name, lat=lat, lng=lng)
    )


def upgrade() -> None:
    _set(BASE_NAME, BASE_LAT, BASE_LNG)


def downgrade() -> None:
    _set(PRIOR_NAME, PRIOR_LAT, PRIOR_LNG)

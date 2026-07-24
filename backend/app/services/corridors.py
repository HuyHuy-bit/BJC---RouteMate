"""
Matches a booking's pickup/dropoff points to the corridor it belongs to.

This is the DB-touching counterpart to app/services/geo.py's pure
projection math — kept separate so geo.py stays a plain function library
with no session dependency. Works correctly with exactly one active
corridor today and requires no code change when a second one is added:
whichever active corridor's hub-to-hub line the booking sits closest to
(within tolerance) wins.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dispatch_config import MAX_CORRIDOR_DEVIATION_METERS
from app.models.corridor import Corridor
from app.services.geo import project_onto_corridor


def find_corridor_for_points(
    db: Session,
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
) -> Corridor | None:
    corridors = (
        db.execute(select(Corridor).where(Corridor.is_active.is_(True)))
        .scalars()
        .all()
    )

    best: Corridor | None = None
    best_deviation: float | None = None

    for corridor in corridors:
        origin = (corridor.away_hub_lat, corridor.away_hub_lng)
        dest = (corridor.home_hub_lat, corridor.home_hub_lng)
        _, pickup_dev = project_onto_corridor(pickup_lat, pickup_lng, origin, dest)
        _, dropoff_dev = project_onto_corridor(dropoff_lat, dropoff_lng, origin, dest)
        deviation = max(pickup_dev, dropoff_dev)

        if deviation > MAX_CORRIDOR_DEVIATION_METERS:
            continue
        if best_deviation is None or deviation < best_deviation:
            best, best_deviation = corridor, deviation

    return best

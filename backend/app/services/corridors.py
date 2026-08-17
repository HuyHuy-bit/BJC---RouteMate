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

from app.core.dispatch_config import (
    MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS,
    MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS,
)
from app.models.corridor import Corridor
from app.services.geo import corridor_deviation_limit_m, project_onto_corridor


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
        pickup_t, pickup_dev = project_onto_corridor(
            pickup_lat, pickup_lng, origin, dest
        )
        dropoff_t, dropoff_dev = project_onto_corridor(
            dropoff_lat, dropoff_lng, origin, dest
        )

        # Each end is judged against the tolerance for where it actually
        # sits, so a rural Bắc Giang pickup isn't held to a city radius.
        over_tolerance = any(
            dev
            > corridor_deviation_limit_m(
                t,
                MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS,
                MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS,
            )
            for t, dev in ((pickup_t, pickup_dev), (dropoff_t, dropoff_dev))
        )
        if over_tolerance:
            continue

        # Ranking between corridors still uses raw deviation: "which
        # corridor is this booking most on" is a different question from
        # "is it on this one at all", and folding per-end tolerances into
        # the comparison would make it incomparable across corridors.
        deviation = max(pickup_dev, dropoff_dev)
        if best_deviation is None or deviation < best_deviation:
            best, best_deviation = corridor, deviation

    return best


def corridor_miss_report(
    db: Session,
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
) -> str:
    """
    Why these points matched no corridor, as one greppable line.

    Nothing recorded how far outside the service area a rejected booking
    actually fell, which made every proposal to move a tolerance a guess
    — including the decision to leave the Hà Nội end at 20 km rather
    than tighten it. Two weeks of these lines is the evidence that
    decision is missing.

    Reports against whichever active corridor came closest, and names
    the end each point sits at (t≈1 is the home hub, t≈0 the away hub)
    so a miss can be attributed to the right tolerance. Deliberately
    logs no coordinates or customer data — only distances.

    Called only on the rejection path, so the extra projection pass
    costs nothing on the normal one.
    """
    corridors = (
        db.execute(select(Corridor).where(Corridor.is_active.is_(True)))
        .scalars()
        .all()
    )
    if not corridors:
        return "no active corridors configured"

    best_line, best_worst = "", None
    for corridor in corridors:
        origin = (corridor.away_hub_lat, corridor.away_hub_lng)
        dest = (corridor.home_hub_lat, corridor.home_hub_lng)
        pickup_t, pickup_dev = project_onto_corridor(
            pickup_lat, pickup_lng, origin, dest
        )
        dropoff_t, dropoff_dev = project_onto_corridor(
            dropoff_lat, dropoff_lng, origin, dest
        )
        worst = max(pickup_dev, dropoff_dev)
        if best_worst is not None and worst >= best_worst:
            continue
        best_worst = worst
        best_line = (
            f"corridor={corridor.name!r} "
            f"pickup_dev_m={pickup_dev:.0f} pickup_t={pickup_t:.2f} "
            f"pickup_limit_m={corridor_deviation_limit_m(pickup_t, MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS, MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS):.0f} "
            f"dropoff_dev_m={dropoff_dev:.0f} dropoff_t={dropoff_t:.2f} "
            f"dropoff_limit_m={corridor_deviation_limit_m(dropoff_t, MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS, MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS):.0f}"
        )
    return best_line

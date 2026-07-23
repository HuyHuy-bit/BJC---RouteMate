"""
The matching algorithm — greedy clustering, same overall shape as before,
but the acceptance criterion and stop ordering now come from a real route
solver (app/services/route_solver.py) instead of raw pickup/dropoff
proximity.

Why this is better than the old "sum of two straight-line distances"
approach: two riders can have a close pickup AND a close dropoff while
still being a bad match if combining them requires the car to backtrack.
Marginal *route insertion cost* — how much longer does the group's actual
optimal route get by adding this rider — is a direct measure of what
actually matters: does sharing raise the total distance/cost driven. No
external API calls; still pure geometry (haversine), just organized
around real route geometry instead of point-to-point distance.
"""

from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, TripStatus
from app.models.trip import Trip
from app.services.geo import Candidate, haversine_m  # noqa: F401 (haversine_m re-exported for callers/tests)
from app.services.route_solver import best_route, pickup_order_ranks

MAX_SEATS = 4


def cluster(candidates: list[Candidate], max_detour_meters: float) -> list[list[UUID]]:
    """
    Greedy clustering: seed a group with the first unclustered candidate,
    then repeatedly add whichever remaining candidate raises the group's
    optimal route distance the LEAST (marginal insertion cost), as long as
    that increase stays within max_detour_meters. Stops at 4 seats.
    Returns a list of groups (lists of booking ids); a group of size 1
    means "no match found this run."
    """
    pool = list(candidates)
    groups: list[list[UUID]] = []

    while pool:
        seed = pool.pop(0)
        group = [seed]
        group_cost, _ = best_route(group)

        while len(group) < MAX_SEATS:
            best_idx = None
            best_marginal = float("inf")
            best_new_cost = None

            for idx, cand in enumerate(pool):
                trial_cost, _ = best_route(group + [cand])
                marginal = trial_cost - group_cost
                if marginal <= max_detour_meters and marginal < best_marginal:
                    best_idx = idx
                    best_marginal = marginal
                    best_new_cost = trial_cost

            if best_idx is None:
                break

            group.append(pool.pop(best_idx))
            group_cost = best_new_cost

        groups.append([c.booking_id for c in group])

    return groups


def run_matching(db: Session, radius_meters: float = 3000) -> list[Trip]:
    """
    Executes one matching pass over all `queued` bookings and returns the
    Trip rows created this run. `radius_meters` is the max acceptable
    detour (in meters) that adding one more rider is allowed to add to a
    car's total route — same parameter name/units as before so the API
    and frontend didn't need to change, but its meaning is now "max added
    detour," not "clustering radius." Caller is responsible for commit —
    this only flushes so generated ids are available.
    """
    from geoalchemy2.shape import to_shape

    queued = db.query(Booking).filter(Booking.status == BookingStatus.queued).all()

    private = [b for b in queued if b.is_private]
    shared = [b for b in queued if not b.is_private]

    trips: list[Trip] = []

    for booking in private:
        trip = Trip(status=TripStatus.confirmed)
        db.add(trip)
        db.flush()
        booking.trip_id = trip.id
        booking.status = BookingStatus.matched
        booking.stop_order = 1
        trips.append(trip)

    by_id = {b.id: b for b in shared}

    # Group by requested pickup date first — a booking for tomorrow must
    # never be clustered with one for today, no matter how close the
    # pickup points are.
    by_date: dict = defaultdict(list)
    for b in shared:
        by_date[b.requested_pickup_at.date()].append(b)

    for _date, bookings_on_date in by_date.items():
        candidates = []
        for b in bookings_on_date:
            p = to_shape(b.pickup_point)
            d = to_shape(b.dropoff_point)
            candidates.append(Candidate(b.id, p.y, p.x, d.y, d.x))

        for group_ids in cluster(candidates, radius_meters):
            if len(group_ids) < 2:
                lone = by_id[group_ids[0]]
                lone.status = BookingStatus.waiting
                continue

            trip = Trip(status=TripStatus.confirmed)
            db.add(trip)
            db.flush()

            members = [by_id[bid] for bid in group_ids]
            member_candidates = [
                c for c in candidates if c.booking_id in set(group_ids)
            ]
            _, ordered_stops = best_route(member_candidates)
            ranks = pickup_order_ranks(ordered_stops)

            for booking in members:
                booking.trip_id = trip.id
                booking.status = BookingStatus.matched
                booking.stop_order = ranks[booking.id]
            trips.append(trip)

    db.flush()
    return trips

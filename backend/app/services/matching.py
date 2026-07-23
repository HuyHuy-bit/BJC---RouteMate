"""
The matching algorithm — greedy clustering using a real route solver for
grouping decisions and stop ordering (see route_solver.py), grouped by
requested pickup date AND direction.

Direction matters for a business reason, not just a geographic one: every
van that drives Bắc Giang -> Hà Nội returns the same day regardless of
whether it's carrying a paying customer (small fleet, fixed base). That
means:
  - Outbound bookings still need 2+ riders to justify running the trip
    (the original business rule — filling seats is what makes an
    outbound trip worth it).
  - Return-leg bookings should be scheduled even solo — the van is
    driving back either way, so there's no "is this worth running"
    threshold on the way home, only a seat-capacity ceiling (4).
This is NOT a pricing change (same price both directions, per the
business's own choice) — it only affects whether a single unmatched
rider counts as "waiting" or as a confirmed trip.
"""

from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingDirection, BookingStatus, TripStatus
from app.models.trip import Trip
from app.services.geo import Candidate, haversine_m  # noqa: F401
from app.services.route_solver import best_route, pickup_order_ranks

MAX_SEATS = 4

MIN_GROUP_SIZE = {
    BookingDirection.outbound: 2,
    BookingDirection.return_leg: 1,
}


def cluster(candidates: list[Candidate], max_detour_meters: float) -> list[list[UUID]]:
    """
    Greedy clustering: seed a group with the first unclustered candidate,
    then repeatedly add whichever remaining candidate raises the group's
    optimal route distance the LEAST (marginal insertion cost), as long as
    that increase stays within max_detour_meters. Stops at 4 seats.
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
    Executes one matching pass over all `queued` bookings. `radius_meters`
    is the max acceptable added detour (meters) for grouping — same
    parameter as before. Caller is responsible for commit — this only
    flushes so generated ids are available.
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

    # Group by (date, direction) — different dates never mix, and
    # outbound/return legs never mix either (they're geographically
    # opposite anyway, but grouping explicitly also lets the two
    # directions use different minimum-group rules below).
    by_bucket: dict = defaultdict(list)
    for b in shared:
        by_bucket[(b.requested_pickup_at.date(), b.direction)].append(b)

    for (_date, direction), bookings_in_bucket in by_bucket.items():
        candidates = []
        for b in bookings_in_bucket:
            p = to_shape(b.pickup_point)
            d = to_shape(b.dropoff_point)
            candidates.append(Candidate(b.id, p.y, p.x, d.y, d.x))

        min_size = MIN_GROUP_SIZE[direction]

        for group_ids in cluster(candidates, radius_meters):
            if len(group_ids) < min_size:
                for bid in group_ids:
                    by_id[bid].status = BookingStatus.waiting
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

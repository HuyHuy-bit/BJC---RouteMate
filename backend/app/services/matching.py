"""
The real matching algorithm — same greedy-clustering shape as the original
prototype's in-browser JS, but operating on real lat/lng coordinates with
real geodesic distance instead of fake pixel math.

Runs as: fetch all `queued` bookings -> greedily cluster into groups of up
to 4, where a candidate can only join a group if it's within
`radius_meters` of every current member's pickup AND dropoff -> groups of
2+ become a confirmed Trip; private bookings always get their own Trip;
leftover singles stay `waiting` for the next run.

This does the clustering in Python rather than as a single SQL query.
That's a deliberate tradeoff: at the volume this business actually runs
(tens of bookings per batch, not thousands), pulling all queued rows and
clustering in memory is simpler to read, debug, and modify than an
equivalent recursive SQL query — and it's easy to swap for a PostGIS-side
implementation later if volume ever justifies it.
"""

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, TripStatus
from app.models.trip import Trip

EARTH_RADIUS_M = 6_371_000
MAX_SEATS = 4


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in meters."""
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * atan2(sqrt(a), sqrt(1 - a))


@dataclass
class Candidate:
    booking_id: UUID
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float


def _score(a: Candidate, b: Candidate) -> float:
    return haversine_m(
        a.pickup_lat, a.pickup_lng, b.pickup_lat, b.pickup_lng
    ) + haversine_m(a.dropoff_lat, a.dropoff_lng, b.dropoff_lat, b.dropoff_lng)


def cluster(candidates: list[Candidate], radius_meters: float) -> list[list[UUID]]:
    """
    Greedy clustering: seed a group with the first unclustered candidate,
    then repeatedly add whichever remaining candidate is closest to the
    ENTIRE current group (max distance to any existing member <=
    2*radius_meters, since the score is a sum of two distances), stopping
    at 4 seats. Returns a list of groups (lists of booking ids); a group
    of size 1 means "no match found this run."
    """
    pool = list(candidates)
    groups: list[list[UUID]] = []
    score_limit = radius_meters * 2

    while pool:
        seed = pool.pop(0)
        group = [seed]
        while len(group) < MAX_SEATS:
            best_idx, best_score = None, float("inf")
            for idx, cand in enumerate(pool):
                max_score = max(_score(member, cand) for member in group)
                if max_score <= score_limit and max_score < best_score:
                    best_idx, best_score = idx, max_score
            if best_idx is None:
                break
            group.append(pool.pop(best_idx))
        groups.append([c.booking_id for c in group])

    return groups


def run_matching(db: Session, radius_meters: float = 3000) -> list[Trip]:
    """
    Executes one matching pass over all `queued` bookings and returns the
    Trip rows created (or reused) this run. Caller is responsible for
    commit — this only flushes so generated ids are available.
    """
    from geoalchemy2.shape import to_shape  # local import: keeps this
    # module's top-level import list free of geometry-shape deps for
    # anything that only needs the pure clustering function above.

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

    # Group by requested pickup date FIRST — a booking for tomorrow must
    # never be clustered with one for today, no matter how close the
    # pickup points are. (Uses each booking's date in UTC; if the business
    # ever needs this in Vietnam local time specifically, convert here.)
    from collections import defaultdict

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

            members = sorted(
                [by_id[bid] for bid in group_ids],
                key=lambda b: to_shape(b.pickup_point).x,
            )
            for i, booking in enumerate(members, start=1):
                booking.trip_id = trip.id
                booking.status = BookingStatus.matched
                booking.stop_order = i
            trips.append(trip)

    db.flush()
    return trips

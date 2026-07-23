from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from uuid import UUID

EARTH_RADIUS_M = 6_371_000


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

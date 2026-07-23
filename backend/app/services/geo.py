from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from uuid import UUID

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Great-circle distance in meters. Used ONLY for cheap pre-filtering and
    for the degraded fallback path when the routing API is unreachable —
    never for final matching decisions, because straight-line distance
    badly misrepresents this corridor (the Red River and Đuống crossings
    mean two points 2km apart can be a 14km drive).
    """
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


# Corridor endpoints. This business serves exactly one corridor, which is
# what makes projection-based direction classification reliable.
BAC_GIANG_HUB = (21.2731, 106.1946)  # (lat, lng)
HA_NOI_HUB = (21.0285, 105.8542)


def _corridor_position(lat: float, lng: float) -> float:
    """
    Projects a point onto the Hà Nội -> Bắc Giang corridor line and
    returns how far along it sits, as a scalar (0.0 ≈ Hà Nội end,
    1.0 ≈ Bắc Giang end; values outside that range mean the point is
    beyond an endpoint).

    Uses an equirectangular approximation, which is accurate at this
    latitude over ~50km and avoids the distortion of treating raw
    lat/lng as planar coordinates.
    """
    lat_ref = radians((BAC_GIANG_HUB[0] + HA_NOI_HUB[0]) / 2)

    def to_xy(la: float, ln: float) -> tuple[float, float]:
        return (radians(ln) * cos(lat_ref) * EARTH_RADIUS_M,
                radians(la) * EARTH_RADIUS_M)

    hx, hy = to_xy(*HA_NOI_HUB)
    bx, by = to_xy(*BAC_GIANG_HUB)
    px, py = to_xy(lat, lng)

    dx, dy = bx - hx, by - hy
    denom = dx * dx + dy * dy
    if denom == 0:
        return 0.0
    return ((px - hx) * dx + (py - hy) * dy) / denom


def classify_direction(
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
) -> str:
    """
    Direction is decided by which way the passenger MOVES along the
    corridor, not by which hub their pickup happens to sit nearer.

    The old nearest-hub check failed silently for midpoint towns like
    Bắc Ninh and Từ Sơn, where a few hundred meters flipped the
    classification and could group a passenger with a car driving the
    opposite way. Comparing pickup and dropoff projections is robust
    anywhere on the corridor, including outside the two endpoints.
    """
    start = _corridor_position(pickup_lat, pickup_lng)
    end = _corridor_position(dropoff_lat, dropoff_lng)
    # Moving toward Bắc Giang (increasing projection) == outbound.
    return "outbound" if end >= start else "return"

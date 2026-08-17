from math import atan2, cos, radians, sin, sqrt

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


LatLng = tuple[float, float]


def project_onto_corridor(
    lat: float, lng: float, origin: LatLng, dest: LatLng
) -> tuple[float, float]:
    """
    Projects a point onto the line from `origin` to `dest` and returns
    `(t, perpendicular_distance_m)`:
      - t: how far along the line the point sits, as a scalar
        (0.0 ≈ origin, 1.0 ≈ dest; values outside that range mean the
        point is beyond an endpoint).
      - perpendicular_distance_m: how far off that line the point sits,
        in meters — near 0 for a point right on the corridor, large for
        a point nowhere near it.

    Generalized from a version that only ever handled one hard-coded
    corridor (Hà Nội ↔ Bắc Giang) — this business now serves more than
    one, so "which two hubs" has to be a parameter, not a module
    constant. Behavior for that original corridor is unchanged when
    called with the same two points.

    Uses an equirectangular approximation, which is accurate over
    distances of a few tens of km (the scale of a single corridor) and
    avoids the distortion of treating raw lat/lng as planar coordinates.
    """
    lat_ref = radians((origin[0] + dest[0]) / 2)

    def to_xy(la: float, ln: float) -> tuple[float, float]:
        return (radians(ln) * cos(lat_ref) * EARTH_RADIUS_M,
                radians(la) * EARTH_RADIUS_M)

    ox, oy = to_xy(*origin)
    dx_, dy_ = to_xy(*dest)
    px, py = to_xy(lat, lng)

    dx, dy = dx_ - ox, dy_ - oy
    denom = dx * dx + dy * dy
    if denom == 0:
        return 0.0, haversine_m(lat, lng, origin[0], origin[1])

    t = ((px - ox) * dx + (py - oy) * dy) / denom
    # Perpendicular offset: distance from the point to its own projection
    # onto the (infinite) line, via the standard 2D cross-product formula.
    perp_m = abs((px - ox) * dy - (py - oy) * dx) / sqrt(denom)
    return t, perp_m


def corridor_deviation_limit_m(
    t: float, home_hub_limit_m: float, away_hub_limit_m: float
) -> float:
    """
    How far off the corridor line a point at position `t` may sit and
    still belong to it. `t` is project_onto_corridor's along-line scalar:
    0.0 at the away hub, 1.0 at the home hub, outside that range beyond
    an endpoint (clamped here).

    One tolerance could not serve both ends. The home hub (Bắc Giang)
    end has a sparse road grid and housing set well back from the
    highway, so coverage matters more than precision there. The away hub
    (Hà Nội) end is dense enough that a modest radius still finds
    matches, and a wide one only invites slow, unpredictable in-city
    detours.

    Interpolated rather than switched at the midpoint on purpose. A step
    would drop a cliff over Bắc Ninh and Từ Sơn, where a few hundred
    metres of GPS imprecision would swing the allowance by kilometres —
    the same shape of failure classify_direction below records having
    already happened once, in those same towns. Passing equal limits
    reproduces the old single-threshold behavior exactly.
    """
    ratio = min(1.0, max(0.0, t))
    return away_hub_limit_m + (home_hub_limit_m - away_hub_limit_m) * ratio


def classify_direction(
    corridor,
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

    `corridor` needs `home_hub_lat/lng` (the depot/base end) and
    `away_hub_lat/lng` (see app/models/corridor.py). Business meaning:
      outbound = leaving the home base (home -> away)
      return   = heading back to the home base (away -> home)
    Projecting from the away hub (t≈0) to the home hub (t≈1), moving
    TOWARD home (dropoff projection > pickup projection) is the RETURN
    leg, not outbound — this matches the original single-corridor
    semantics exactly (an earlier version had this inverted, which
    displayed every Bắc Giang -> Hà Nội booking backwards).
    """
    origin = (corridor.away_hub_lat, corridor.away_hub_lng)
    dest = (corridor.home_hub_lat, corridor.home_hub_lng)
    start, _ = project_onto_corridor(pickup_lat, pickup_lng, origin, dest)
    end, _ = project_onto_corridor(dropoff_lat, dropoff_lng, origin, dest)
    return "return" if end >= start else "outbound"

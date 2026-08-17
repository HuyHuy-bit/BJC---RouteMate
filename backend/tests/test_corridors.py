"""
Corridor membership: which bookings the service area accepts, and what
gets recorded about the ones it turns away.

Deliberately NOT an integration test. corridors.py only ever asks the
session for "the active corridors", so a five-line stub stands in for
Postgres and these run in the default offline suite — where a
database-gated test would silently skip and prove nothing. Corridor
objects construct fine with no session (same trick as test_geo.py).
"""

from math import cos, radians

from app.core.dispatch_config import (
    MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS,
    MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS,
)
from app.models.corridor import Corridor
from app.services.corridors import corridor_miss_report, find_corridor_for_points
from app.services.geo import EARTH_RADIUS_M

BAC_GIANG = (21.2731, 106.1946)  # home hub
HA_NOI = (21.0285, 105.8542)  # away hub

CORRIDOR = Corridor(
    name="Bắc Giang ⇄ Hà Nội",
    home_hub_name="Bắc Giang",
    home_hub_lat=BAC_GIANG[0],
    home_hub_lng=BAC_GIANG[1],
    away_hub_name="Hà Nội",
    away_hub_lat=HA_NOI[0],
    away_hub_lng=HA_NOI[1],
    is_active=True,
    base_fare_vnd=150_000,
)

# The single symmetric tolerance the two endpoint values replaced. Used
# to state the loosen-only property in terms of real coordinates.
LEGACY_SYMMETRIC_LIMIT_M = 20_000


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeSession:
    """Answers the one query corridors.py makes: the active corridors."""

    def __init__(self, *corridors):
        self._corridors = list(corridors)

    def execute(self, _stmt):
        return _FakeResult(self._corridors)


def _offset_perpendicular(point, metres):
    """
    Move `point` `metres` at right angles to the corridor.

    Offsetting along a single axis would not do: the corridor runs
    diagonally, so a pure-latitude shift slides the point ALONG the
    route as well as off it, and the resulting `t` no longer isolates
    the end under test.
    """
    lat_ref = radians((BAC_GIANG[0] + HA_NOI[0]) / 2)
    m_per_deg_lat = radians(1) * EARTH_RADIUS_M
    m_per_deg_lng = radians(1) * cos(lat_ref) * EARTH_RADIUS_M
    dx = (BAC_GIANG[1] - HA_NOI[1]) * m_per_deg_lng
    dy = (BAC_GIANG[0] - HA_NOI[0]) * m_per_deg_lat
    length = (dx * dx + dy * dy) ** 0.5
    return (
        point[0] + (dx / length * metres) / m_per_deg_lat,
        point[1] + (-dy / length * metres) / m_per_deg_lng,
    )


# -- membership -------------------------------------------------------


def test_points_on_the_corridor_are_matched():
    db = _FakeSession(CORRIDOR)
    assert find_corridor_for_points(db, *BAC_GIANG, *HA_NOI) is CORRIDOR


def test_a_rural_pickup_now_inside_the_widened_home_end_is_accepted():
    # 24 km off-corridor at the Bắc Giang end: beyond the old symmetric
    # 20 km, inside the new 28 km. This booking is the whole point of
    # the change — a real customer down a commune road who used to be
    # told they were outside the service area.
    db = _FakeSession(CORRIDOR)
    pickup = _offset_perpendicular(BAC_GIANG, 24_000)
    assert find_corridor_for_points(db, *pickup, *HA_NOI) is CORRIDOR


def test_the_city_end_tolerance_is_unchanged():
    # The same 24 km offset at the Hà Nội end stays rejected: this pass
    # widened one end only, and did not quietly loosen the other.
    db = _FakeSession(CORRIDOR)
    pickup = _offset_perpendicular(HA_NOI, 24_000)
    assert find_corridor_for_points(db, *pickup, *HA_NOI) is None


def test_beyond_the_widened_home_end_is_still_rejected():
    # 30 km off at Bắc Giang is past even the new tolerance. Widening is
    # not the same as removing the boundary.
    db = _FakeSession(CORRIDOR)
    pickup = _offset_perpendicular(BAC_GIANG, 30_000)
    assert find_corridor_for_points(db, *pickup, *HA_NOI) is None


def test_nothing_accepted_under_the_old_tolerance_is_rejected_now():
    # The loosen-only guarantee, in coordinates rather than in the
    # abstract: sweep both ends at offsets the old symmetric 20 km would
    # have accepted, and confirm every one still gets in.
    db = _FakeSession(CORRIDOR)
    for anchor in (BAC_GIANG, HA_NOI):
        for metres in (0, 5_000, 12_000, 19_000):
            pickup = _offset_perpendicular(anchor, metres)
            assert find_corridor_for_points(db, *pickup, *HA_NOI) is CORRIDOR, (
                f"{metres}m off at {anchor} was inside the old "
                f"{LEGACY_SYMMETRIC_LIMIT_M}m tolerance but is rejected now"
            )


def test_both_ends_must_qualify_not_just_one():
    # A pickup sitting perfectly on the corridor does not buy a dropoff
    # 40 km away from it a place on the route.
    db = _FakeSession(CORRIDOR)
    dropoff = _offset_perpendicular(HA_NOI, 40_000)
    assert find_corridor_for_points(db, *BAC_GIANG, *dropoff) is None


# -- what a rejection records -----------------------------------------


def test_miss_report_names_the_corridor_and_both_deviations():
    db = _FakeSession(CORRIDOR)
    pickup = _offset_perpendicular(BAC_GIANG, 30_000)
    report = corridor_miss_report(db, *pickup, *HA_NOI)

    assert "Bắc Giang ⇄ Hà Nội" in report
    for field in (
        "pickup_dev_m=",
        "pickup_t=",
        "pickup_limit_m=",
        "dropoff_dev_m=",
        "dropoff_t=",
        "dropoff_limit_m=",
    ):
        assert field in report, f"{field} missing from {report!r}"


def test_miss_report_attributes_the_miss_to_the_end_it_happened_at():
    # The report has to say WHICH tolerance was the binding one, or it
    # can't be used to decide which end to move. t≈1 is the home hub.
    db = _FakeSession(CORRIDOR)
    pickup = _offset_perpendicular(BAC_GIANG, 30_000)
    report = corridor_miss_report(db, *pickup, *HA_NOI)

    assert "pickup_t=1.0" in report
    assert f"pickup_limit_m={MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS}" in report
    assert f"dropoff_limit_m={MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS}" in report


def test_miss_report_survives_having_no_corridors_at_all():
    # An empty corridor table must produce a log line, not an exception
    # on the path that is already rejecting a customer's booking.
    assert corridor_miss_report(_FakeSession(), *BAC_GIANG, *HA_NOI) == (
        "no active corridors configured"
    )

"""
Pure-function coverage for the corridor projection/classification math —
no database needed, since geo.py is deliberately DB-free.

The Bắc Giang <-> Hà Nội numbers here are the same hub coordinates the
app has always used (see app/services/corridors.py's seed migration).
This is also a regression test for a real historical bug: an earlier
version of classify_direction had outbound/return inverted, silently
showing every Bắc Giang -> Hà Nội booking backwards.
"""

from app.models.corridor import Corridor
from app.services.geo import (
    classify_direction,
    corridor_deviation_limit_m,
    project_onto_corridor,
)

BAC_GIANG = (21.2731, 106.1946)
HA_NOI = (21.0285, 105.8542)

CORRIDOR = Corridor(
    name="Bắc Giang ⇄ Hà Nội",
    home_hub_name="Bắc Giang",
    home_hub_lat=BAC_GIANG[0],
    home_hub_lng=BAC_GIANG[1],
    away_hub_name="Hà Nội",
    away_hub_lat=HA_NOI[0],
    away_hub_lng=HA_NOI[1],
    base_fare_vnd=150_000,
)


def test_project_onto_corridor_endpoints():
    # Right at the away hub (Hà Nội): t ~= 0, no perpendicular offset.
    t, perp = project_onto_corridor(*HA_NOI, HA_NOI, BAC_GIANG)
    assert abs(t) < 1e-6
    assert perp < 1.0

    # Right at the home hub (Bắc Giang): t ~= 1.
    t, perp = project_onto_corridor(*BAC_GIANG, HA_NOI, BAC_GIANG)
    assert abs(t - 1.0) < 1e-6
    assert perp < 1.0


def test_project_onto_corridor_midpoint_is_on_line():
    mid_lat = (BAC_GIANG[0] + HA_NOI[0]) / 2
    mid_lng = (BAC_GIANG[1] + HA_NOI[1]) / 2
    t, perp = project_onto_corridor(mid_lat, mid_lng, HA_NOI, BAC_GIANG)
    assert abs(t - 0.5) < 1e-6
    assert perp < 1.0


def test_project_onto_corridor_off_line_has_large_perpendicular_offset():
    # A point far off the corridor (e.g. well south of the line) should
    # have a large perpendicular distance regardless of where it falls
    # along the line.
    _, perp = project_onto_corridor(20.5, 105.9, HA_NOI, BAC_GIANG)
    assert perp > 20_000  # tens of km off the corridor


def test_classify_direction_bac_giang_to_ha_noi_is_outbound():
    # Leaving the home base — this is the exact scenario a prior version
    # of this function got backwards.
    direction = classify_direction(CORRIDOR, *BAC_GIANG, *HA_NOI)
    assert direction == "outbound"


def test_classify_direction_ha_noi_to_bac_giang_is_return():
    direction = classify_direction(CORRIDOR, *HA_NOI, *BAC_GIANG)
    assert direction == "return"


def test_classify_direction_midpoint_town_moving_toward_home_is_return():
    # A rider picked up partway along the corridor (e.g. near Bắc Ninh)
    # heading further toward the home hub is still a return leg, even
    # though neither point is at an endpoint.
    bac_ninh_ish = (21.15, 106.05)
    direction = classify_direction(CORRIDOR, *bac_ninh_ish, *BAC_GIANG)
    assert direction == "return"


# -- endpoint-aware deviation tolerance -------------------------------

# The single symmetric tolerance these two values replace, kept as the
# floor every interpolated result must clear. See
# test_no_point_gets_a_tighter_tolerance_than_before.
LEGACY_SYMMETRIC_LIMIT_M = 20_000


def test_deviation_limit_is_the_away_hub_value_at_the_away_hub():
    t, _ = project_onto_corridor(*HA_NOI, HA_NOI, BAC_GIANG)
    limit = corridor_deviation_limit_m(
        t, home_hub_limit_m=28_000, away_hub_limit_m=20_000
    )
    assert abs(limit - 20_000) < 1.0


def test_deviation_limit_is_the_home_hub_value_at_the_home_hub():
    t, _ = project_onto_corridor(*BAC_GIANG, HA_NOI, BAC_GIANG)
    limit = corridor_deviation_limit_m(
        t, home_hub_limit_m=28_000, away_hub_limit_m=20_000
    )
    assert abs(limit - 28_000) < 1.0


def test_deviation_limit_has_no_cliff_at_the_corridor_midpoint():
    # The midpoint is Bắc Ninh / Từ Sơn country. A step function here
    # would swing the allowance by kilometres on a few hundred metres of
    # GPS noise — the same shape of bug classify_direction's docstring
    # records for exactly these towns. Two points a hair either side of
    # the middle must get near-identical tolerances.
    just_below = corridor_deviation_limit_m(0.499, 28_000, 20_000)
    just_above = corridor_deviation_limit_m(0.501, 28_000, 20_000)
    assert abs(just_above - just_below) < 50.0


def test_deviation_limit_is_clamped_beyond_both_endpoints():
    # project_onto_corridor returns t outside [0, 1] for points past an
    # endpoint. Those must pin to the nearer hub's limit rather than
    # extrapolate into a nonsense tolerance.
    assert corridor_deviation_limit_m(-3.0, 28_000, 20_000) == 20_000
    assert corridor_deviation_limit_m(4.0, 28_000, 20_000) == 28_000


def test_no_point_gets_a_tighter_tolerance_than_before():
    # The loosen-only invariant this change ships under: with the away
    # hub pinned at today's symmetric value, no position along the
    # corridor may come out stricter than today. A booking accepted
    # before this change must still be accepted after it.
    for i in range(-20, 121):
        t = i / 100.0
        limit = corridor_deviation_limit_m(
            t, home_hub_limit_m=28_000, away_hub_limit_m=LEGACY_SYMMETRIC_LIMIT_M
        )
        assert limit >= LEGACY_SYMMETRIC_LIMIT_M, (
            f"t={t} got {limit}m, tighter than the {LEGACY_SYMMETRIC_LIMIT_M}m "
            "tolerance it replaces"
        )


def test_equal_limits_reproduce_the_old_symmetric_behavior_exactly():
    for t in (-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
        assert corridor_deviation_limit_m(t, 20_000, 20_000) == 20_000

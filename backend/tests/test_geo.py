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
from app.services.geo import classify_direction, project_onto_corridor

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

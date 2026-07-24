"""
Coverage for time-first, distance-second pool grouping — no database
needed (PoolMember is a plain dataclass; evaluate_insertion only talks
to the routing service, forced below into its degraded/estimate mode so
these tests are deterministic and network-free regardless of whether a
real Goong API key happens to be configured in this environment).
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.dispatch_config import MAX_PASSENGERS, TIME_CLUSTER_MINUTES
from app.services.pool_insertion import PoolMember, compute_solo_baseline
from app.services.reclustering import cluster_by_proximity, regroup, time_cluster
from app.services.routing import routing_service

BASE_TIME = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)

# Two geographically distinct pickup areas, both on the corridor, far
# enough apart that grouping them together would be a bad route.
AREA_A = (21.20, 106.10)
AREA_B = (21.08, 105.90)
DROPOFF = (21.0285, 105.8542)  # everyone headed toward central Hà Nội


@pytest.fixture(autouse=True)
def force_degraded_routing():
    """Force routing_service's circuit "open" so every call in this file
    uses the haversine-based fallback, never a real network request."""
    original = routing_service._circuit_open_until
    routing_service._circuit_open_until = time.time() + 3600
    yield
    routing_service._circuit_open_until = original


def _member(pickup, dropoff, minutes_after_base: float, jitter=(0.0, 0.0)) -> PoolMember:
    p = (pickup[0] + jitter[0], pickup[1] + jitter[1])
    return PoolMember(
        booking_id=uuid4(),
        pickup=p,
        dropoff=dropoff,
        requested_pickup_at=BASE_TIME + timedelta(minutes=minutes_after_base),
        solo_duration_seconds=compute_solo_baseline(p, dropoff),
    )


# ---------------------------------------------------------------- time_cluster


def test_time_cluster_groups_close_pickups_together():
    members = [
        _member(AREA_A, DROPOFF, 0),
        _member(AREA_A, DROPOFF, 5),
        _member(AREA_A, DROPOFF, 15),
    ]
    clusters = time_cluster(members)
    assert len(clusters) == 1
    assert len(clusters[0]) == 3


def test_time_cluster_splits_on_a_large_gap():
    members = [
        _member(AREA_A, DROPOFF, 0),
        _member(AREA_A, DROPOFF, 5),
        _member(AREA_A, DROPOFF, 90),  # well past TIME_CLUSTER_MINUTES
    ]
    clusters = time_cluster(members)
    assert len(clusters) == 2
    assert len(clusters[0]) == 2
    assert len(clusters[1]) == 1


def test_time_cluster_chaining_within_threshold():
    # Each adjacent gap is under TIME_CLUSTER_MINUTES, even though the
    # first and last are further apart than the threshold — sequential
    # bucketing chains them into one cluster on purpose; final pairwise
    # feasibility is still enforced separately inside evaluate_insertion.
    assert TIME_CLUSTER_MINUTES == 20  # this test's gaps assume this value
    members = [
        _member(AREA_A, DROPOFF, 0),
        _member(AREA_A, DROPOFF, 19),
        _member(AREA_A, DROPOFF, 38),
    ]
    clusters = time_cluster(members)
    assert len(clusters) == 1
    assert len(clusters[0]) == 3


def test_time_cluster_empty_input():
    assert time_cluster([]) == []


# ------------------------------------------------------------ cluster_by_proximity


def test_cluster_by_proximity_respects_max_passengers():
    members = [_member(AREA_A, DROPOFF, i, jitter=(0.001 * i, 0)) for i in range(5)]
    groups = cluster_by_proximity(members)
    assert all(len(g) <= MAX_PASSENGERS for g in groups)
    # Everyone appears exactly once across all groups.
    all_ids = [m.booking_id for g in groups for m in g]
    assert sorted(all_ids) == sorted(m.booking_id for m in members)


def test_cluster_by_proximity_keeps_distinct_areas_apart():
    # 4 pickups tightly clustered near area A, 4 tightly clustered near
    # area B, all requesting pickup within a few minutes of each other.
    # Mixing an A-rider with a B-rider into the same car would be a
    # needless detour when there's no capacity pressure forcing it —
    # the nearest-neighbor greedy should keep the two areas separate.
    area_a_members = [
        _member(AREA_A, DROPOFF, i, jitter=(0.001 * i, 0.001 * i)) for i in range(4)
    ]
    area_b_members = [
        _member(AREA_B, DROPOFF, i, jitter=(0.001 * i, 0.001 * i)) for i in range(4)
    ]
    groups = cluster_by_proximity(area_a_members + area_b_members)

    assert len(groups) == 2
    a_ids = {m.booking_id for m in area_a_members}
    b_ids = {m.booking_id for m in area_b_members}
    group_id_sets = [{m.booking_id for m in g} for g in groups]
    assert a_ids in group_id_sets
    assert b_ids in group_id_sets


# -------------------------------------------------------------------- regroup


def test_regroup_keeps_two_close_time_waves_separate_even_when_geographically_identical():
    # Same pickup area for everyone (so distance alone would happily
    # merge them), but two waves 35 minutes apart — inside the hard
    # PICKUP_WINDOW_MINUTES=45 ceiling (so the old distance-first scoring
    # could well have merged them for occupancy), but outside
    # TIME_CLUSTER_MINUTES=20. Time-first grouping must still keep them
    # apart as two separate waves.
    wave_1 = [_member(AREA_A, DROPOFF, m, jitter=(0.0005 * m, 0)) for m in (0, 5, 10)]
    wave_2 = [_member(AREA_A, DROPOFF, m, jitter=(0.0005 * m, 0)) for m in (35, 40, 45)]

    groups = regroup(wave_1 + wave_2)

    wave_1_ids = {m.booking_id for m in wave_1}
    wave_2_ids = {m.booking_id for m in wave_2}
    group_id_sets = [{m.booking_id for m in g} for g in groups]
    assert wave_1_ids in group_id_sets
    assert wave_2_ids in group_id_sets


def test_regroup_single_member():
    members = [_member(AREA_A, DROPOFF, 0)]
    groups = regroup(members)
    assert len(groups) == 1
    assert len(groups[0]) == 1

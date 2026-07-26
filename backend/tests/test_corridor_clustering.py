"""
Phase 7 coverage: corridor-projection grouping, and the shared leg cache
that makes a whole clustering pass cost one routing call instead of one
per candidate.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.corridor import Corridor
from app.services import pool_insertion
from app.services.pool_insertion import (
    PoolMember,
    build_leg_cache,
    compute_solo_baseline,
    evaluate_insertion,
)
from app.services.reclustering import (
    cluster_by_proximity,
    corridor_position_meters,
    regroup,
)
from app.services.routing import routing_service

BASE_TIME = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)

# The live corridor's real hub coordinates.
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
    base_fare_vnd=150_000,
)


@pytest.fixture(autouse=True)
def force_degraded_routing():
    """Force the routing circuit open so calls use the haversine
    fallback — deterministic and network-free."""
    original = routing_service._circuit_open_until
    routing_service._circuit_open_until = time.time() + 3600
    yield
    routing_service._circuit_open_until = original


def _member(pickup, minutes=0.0, seats=1) -> PoolMember:
    return PoolMember(
        booking_id=uuid4(),
        pickup=pickup,
        dropoff=HA_NOI,
        requested_pickup_at=BASE_TIME + timedelta(minutes=minutes),
        solo_duration_seconds=compute_solo_baseline(pickup, HA_NOI),
        seats=seats,
    )


# -- corridor projection ----------------------------------------------


def test_corridor_position_increases_from_away_hub_toward_home_hub():
    at_away = corridor_position_meters(*HA_NOI, CORRIDOR)
    midpoint = (
        (BAC_GIANG[0] + HA_NOI[0]) / 2,
        (BAC_GIANG[1] + HA_NOI[1]) / 2,
    )
    at_mid = corridor_position_meters(*midpoint, CORRIDOR)
    at_home = corridor_position_meters(*BAC_GIANG, CORRIDOR)

    assert at_away < at_mid < at_home
    assert abs(at_away) < 1_000  # ~0 m from the away hub itself


def test_points_off_the_corridor_project_to_their_along_line_position():
    # Two points at the SAME position along the corridor but offset to
    # opposite sides of it project to (nearly) the same value — which is
    # the whole point: what matters for a shared route is how far along
    # the direction of travel you are, not lateral scatter.
    mid = ((BAC_GIANG[0] + HA_NOI[0]) / 2, (BAC_GIANG[1] + HA_NOI[1]) / 2)
    north = (mid[0] + 0.05, mid[1] - 0.04)
    south = (mid[0] - 0.05, mid[1] + 0.04)

    pos_north = corridor_position_meters(*north, CORRIDOR)
    pos_south = corridor_position_meters(*south, CORRIDOR)
    assert abs(pos_north - pos_south) < 5_000


def test_grouping_follows_the_corridor_not_raw_scatter():
    # Six riders in the same time wave: three clustered near the Bắc
    # Giang end, three near the Hà Nội end. Corridor-aware grouping
    # should keep each end together rather than mixing ends.
    near_home = [
        _member((BAC_GIANG[0] - 0.01 * i, BAC_GIANG[1] - 0.01 * i), minutes=i)
        for i in range(3)
    ]
    near_away = [
        _member((HA_NOI[0] + 0.01 * i, HA_NOI[1] + 0.01 * i), minutes=i)
        for i in range(3)
    ]

    groups = cluster_by_proximity(near_home + near_away, CORRIDOR)

    home_ids = {m.booking_id for m in near_home}
    away_ids = {m.booking_id for m in near_away}
    for g in groups:
        ids = {m.booking_id for m in g}
        # No group may straddle both ends of the corridor.
        assert not (ids & home_ids and ids & away_ids), (
            "a group mixed riders from opposite ends of the corridor"
        )


# -- shared leg cache -------------------------------------------------


class _CallCounter:
    """Wraps routing_service.matrix to count real fetches."""

    def __init__(self):
        self.calls = 0
        self._original = routing_service.matrix

    def __enter__(self):
        def counting(origins, destinations):
            self.calls += 1
            return self._original(origins, destinations)

        routing_service.matrix = counting
        return self

    def __exit__(self, *exc):
        routing_service.matrix = self._original


def test_supplying_a_leg_cache_removes_all_matrix_calls():
    members = [
        _member((BAC_GIANG[0] - 0.01 * i, BAC_GIANG[1] - 0.01 * i), minutes=i)
        for i in range(4)
    ]
    coords = [c for m in members for c in (m.pickup, m.dropoff)]

    with _CallCounter() as counter:
        leg_cache = build_leg_cache(coords)
        assert counter.calls == 1  # the one shared fetch

        cluster_by_proximity(members, CORRIDOR, leg_cache)
        # Every insertion evaluated during clustering served from cache.
        assert counter.calls == 1, (
            f"clustering made {counter.calls - 1} extra matrix call(s) "
            "despite a complete leg cache"
        )


def test_without_a_leg_cache_each_evaluation_fetches_its_own():
    # The contrast case — proves the assertion above is actually
    # measuring something rather than passing vacuously.
    members = [
        _member((BAC_GIANG[0] - 0.01 * i, BAC_GIANG[1] - 0.01 * i), minutes=i)
        for i in range(4)
    ]
    with _CallCounter() as counter:
        cluster_by_proximity(members, CORRIDOR)
        assert counter.calls > 1


def test_incomplete_cache_falls_back_instead_of_producing_wrong_numbers():
    # A cache missing a needed pair must trigger a real fetch, not a
    # KeyError and not a silently-wrong duration.
    members = [_member(BAC_GIANG, minutes=0), _member(HA_NOI, minutes=2)]
    partial: dict = {(members[0].pickup, members[0].pickup): 0.0}

    with _CallCounter() as counter:
        result = evaluate_insertion([members[0]], members[1], leg_cache=partial)
        assert counter.calls == 1  # fell back to a live fetch
    assert result is not None  # and produced a real verdict either way


def test_oversized_matrix_is_chunked_not_sent_as_one_failing_request():
    # Regression: batching a whole dispatch group into one matrix call
    # can exceed the provider's element limit (Goong rejects anything
    # over MATRIX_MAX_ELEMENTS with a bare 400). That failure was silent
    # and expensive — every pair in the group degraded to straight-line
    # estimates. RoutingService must split the request instead.
    from app.core.dispatch_config import MATRIX_MAX_ELEMENTS

    side = int(MATRIX_MAX_ELEMENTS**0.5)
    n = side + 2  # comfortably over the limit when squared
    pts = [(21.05 + 0.01 * i, 105.88 + 0.01 * i) for i in range(n)]

    sizes: list[int] = []
    original = routing_service._fetch_matrix_chunk

    def recording(origins, destinations):
        # Record the shape, then return a synthetic block of the right
        # size. It used to delegate to `original`, which fired a real
        # HTTPS request at the Goong API for every chunk — so without a
        # paid key the 403 propagated out of _fetch_matrix and NOT ONE
        # of the assertions below ever ran, and with a key the suite
        # burned live quota on every execution.
        #
        # Nothing here needs the network: the chunk-splitting arithmetic
        # under test happens before any request, and is fully observable
        # from `sizes` plus the shape of the reassembled result.
        sizes.append(len(origins) * len(destinations))
        return [[1.0] * len(destinations) for _ in origins]

    routing_service._fetch_matrix_chunk = recording
    routing_service._cache._data.clear()
    try:
        # Calls _fetch_matrix directly rather than going through the
        # degraded-mode fixture, because chunk splitting is what
        # _fetch_matrix itself owns.
        result = routing_service._fetch_matrix(pts, pts)
    finally:
        routing_service._fetch_matrix_chunk = original

    assert len(sizes) > 1, "oversized request was not split at all"
    assert all(s <= MATRIX_MAX_ELEMENTS for s in sizes), (
        f"a chunk exceeded the provider limit: {sizes}"
    )
    # ...and the reassembled matrix is still the full requested shape.
    assert len(result) == n and all(len(row) == n for row in result)


def test_regroup_threads_corridor_and_cache_through():
    members = [
        _member((BAC_GIANG[0] - 0.01 * i, BAC_GIANG[1] - 0.01 * i), minutes=i)
        for i in range(3)
    ]
    coords = [c for m in members for c in (m.pickup, m.dropoff)]
    with _CallCounter() as counter:
        leg_cache = build_leg_cache(coords)
        groups = regroup(members, CORRIDOR, leg_cache)
        assert counter.calls == 1

    all_ids = sorted(m.booking_id for g in groups for m in g)
    assert all_ids == sorted(m.booking_id for m in members)

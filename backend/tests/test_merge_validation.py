"""
The merge path is the one place the per-passenger detour guarantee used
to be waived: rank_merge_candidates applies only cheap filters
(direction, seats, timing), so without a real route check the caller
could combine two pools that cannot actually be driven inside the
promised cap — and, because the bookings had already moved by then,
_refresh_pool_geometry would silently fall back to a naive route and
run it anyway.

These cover both halves: that ranking still offers every cheap-viable
candidate (so a caller can fall through to a worse-but-workable one),
and that the real feasibility engine rejects a combination that breaks
the guarantee.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.dispatch_config import MAX_PASSENGERS
from app.services.dispatch_engine import PoolSnapshot, rank_merge_candidates
from app.services.pool_insertion import (
    PoolMember,
    compute_solo_baseline,
    solve_group_ordering,
)
from app.services.routing import routing_service

BASE = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
BAC_GIANG = (21.2731, 106.1946)
HA_NOI = (21.0285, 105.8542)


@pytest.fixture(autouse=True)
def force_degraded_routing():
    original = routing_service._circuit_open_until
    routing_service._circuit_open_until = time.time() + 3600
    yield
    routing_service._circuit_open_until = original


def _snap(minutes=0.0, seats=1, direction="outbound", private=False, capacity=MAX_PASSENGERS):
    return PoolSnapshot(
        pool_id=uuid4(),
        direction=direction,
        passenger_count=1,
        earliest_requested_pickup=BASE + timedelta(minutes=minutes),
        created_at=BASE,
        is_private=private,
        seat_count=seats,
        capacity=capacity,
    )


def _member(pickup, dropoff, minutes=0.0, seats=1):
    return PoolMember(
        booking_id=uuid4(),
        pickup=pickup,
        dropoff=dropoff,
        requested_pickup_at=BASE + timedelta(minutes=minutes),
        solo_duration_seconds=compute_solo_baseline(pickup, dropoff),
        seats=seats,
    )


# -- ranking ----------------------------------------------------------


def test_ranking_returns_all_viable_candidates_closest_time_first():
    # Returning a LIST, not a single pick, is the point: if the closest
    # candidate turns out to be un-routable, the caller needs the next
    # one rather than giving up on merging entirely.
    lonely = _snap(minutes=0)
    far = _snap(minutes=30)
    near = _snap(minutes=5)

    ranked = rank_merge_candidates(lonely, [far, near])

    assert [c.pool_id for c in ranked] == [near.pool_id, far.pool_id]


def test_ranking_excludes_opposite_direction_private_and_oversized():
    lonely = _snap(minutes=0, seats=2)
    ranked = rank_merge_candidates(
        lonely,
        [
            _snap(minutes=1, direction="return"),   # wrong way
            _snap(minutes=1, private=True),          # private hire
            _snap(minutes=1, seats=3),               # 2 + 3 > 4 seats
        ],
    )
    assert ranked == []


def test_ranking_never_offers_the_pool_itself():
    lonely = _snap(minutes=0)
    assert rank_merge_candidates(lonely, [lonely]) == []


# -- real feasibility -------------------------------------------------


def test_a_combination_that_breaks_the_detour_cap_has_no_feasible_ordering():
    # Two riders going opposite ways along the corridor: one Bắc Giang
    # -> Hà Nội, one Hà Nội -> Bắc Giang. Timing and seats both look
    # fine to the cheap filters, but no stop order can serve both
    # without dragging someone far past their solo baseline. This is
    # exactly the case that used to slip through and get merged.
    members = [
        _member(BAC_GIANG, HA_NOI, minutes=0),
        _member(HA_NOI, BAC_GIANG, minutes=5),
    ]
    _total, ordered_stops, _offsets = solve_group_ordering(members)
    assert ordered_stops == [], (
        "a combination breaking the detour guarantee was reported as routable"
    )


def test_solo_group_is_routable_so_emptiness_must_be_caught_separately():
    # A single rider always has a trivially valid ordering. That's why
    # can_merge_pools checks each side for real bookings explicitly
    # rather than relying on the route solve to reject an already-
    # emptied partner: the solve would happily succeed on the survivor's
    # own stops alone and report the merge as fine.
    members = [_member(BAC_GIANG, HA_NOI, minutes=0)]
    _total, ordered_stops, _offsets = solve_group_ordering(members)
    assert ordered_stops != []


def test_a_sensible_combination_is_still_routable():
    # Two riders heading the same way from nearby pickups — the merge
    # this feature exists to enable must still work.
    members = [
        _member(BAC_GIANG, HA_NOI, minutes=0),
        _member((BAC_GIANG[0] - 0.01, BAC_GIANG[1] - 0.01), HA_NOI, minutes=4),
    ]
    _total, ordered_stops, _offsets = solve_group_ordering(members)
    assert ordered_stops != []
    # Everyone's pickup and dropoff appear exactly once.
    assert len(ordered_stops) == 4

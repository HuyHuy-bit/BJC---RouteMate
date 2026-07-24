"""
Phase 2/3 coverage: real per-stop ETAs (not an even split), the
timezone regression in find_returning_vehicle's gap calculation, and
Phase 3's schedule-window enforcement (late rejection, early-arrival
forced wait that propagates to later stops).

These exercise the pure scheduling internals directly (no DB) plus the
_write_etas writer against lightweight stand-ins.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.core.dispatch_config import (
    EARLY_PICKUP_TOLERANCE_MINUTES,
    LATE_PICKUP_TOLERANCE_MINUTES,
)
from app.services.pool_insertion import PoolMember, _as_utc, _best_ordering

BASE = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def _member(bid, requested_offset_minutes=0.0, solo_seconds=600.0) -> PoolMember:
    return PoolMember(
        booking_id=bid,
        pickup=(0.0, 0.0),
        dropoff=(0.0, 0.0),
        requested_pickup_at=BASE + timedelta(minutes=requested_offset_minutes),
        solo_duration_seconds=solo_seconds,
    )


def _index_for(members):
    """Build the (booking_id, kind) -> coord-slot index the same way
    evaluate_insertion does: pickup then dropoff per member, in order."""
    index = {}
    slot = 0
    for m in members:
        index[(m.booking_id, "pickup")] = slot
        slot += 1
        index[(m.booking_id, "dropoff")] = slot
        slot += 1
    return index


def _biased_durations(index, cheap_sequence, cheap_costs, high=1_000_000.0):
    """A full cost matrix where every leg costs `high` except the given
    sequence of (booking_id, kind) stops, which cost `cheap_costs`
    between consecutive entries — forces the solver to pick exactly
    that ordering, so tests can assert on its resulting offsets."""
    n = len(index)
    durations = {(i, j): high for i in range(n) for j in range(n)}
    slots = [index[key] for key in cheap_sequence]
    for (a, b), cost in zip(zip(slots, slots[1:]), cheap_costs):
        durations[(a, b)] = cost
    return durations


def test_offsets_use_real_leg_times_not_even_split():
    a, b, c = uuid4(), uuid4(), uuid4()
    members = [_member(a), _member(b), _member(c)]
    index = _index_for(members)
    sequence = [(a, "pickup"), (b, "pickup"), (c, "pickup"),
                (a, "dropoff"), (b, "dropoff"), (c, "dropoff")]
    durations = _biased_durations(index, sequence, [120, 1500, 180, 60, 90])

    total, order, offsets = _best_ordering(members, durations, index)

    assert [(s.booking_id, s.kind) for s in order] == sequence
    assert offsets[a]["pickup"] == 0
    assert offsets[b]["pickup"] == 120
    assert offsets[c]["pickup"] == 1620
    # Not an even split of the 1950s total across 6 stops.
    assert offsets[b]["pickup"] != offsets[c]["pickup"]


def test_each_passenger_gets_a_distinct_dropoff_offset():
    a, b = uuid4(), uuid4()
    members = [_member(a), _member(b)]
    index = _index_for(members)
    sequence = [(a, "pickup"), (b, "pickup"), (a, "dropoff"), (b, "dropoff")]
    durations = _biased_durations(index, sequence, [300, 600, 400])

    _, _, offsets = _best_ordering(members, durations, index)

    assert offsets[a]["dropoff"] == 900
    assert offsets[b]["dropoff"] == 1300
    assert offsets[a]["dropoff"] != offsets[b]["dropoff"]


# -- Phase 3: schedule-window enforcement ------------------------------


def test_ordering_scheduling_a_pickup_too_late_is_rejected():
    # B's only reachable route puts their pickup well past their own
    # LATE tolerance — no ordering should be returned.
    a, b = uuid4(), uuid4()
    members = [
        _member(a, requested_offset_minutes=0),
        _member(b, requested_offset_minutes=0),
    ]
    index = _index_for(members)
    sequence = [(a, "pickup"), (a, "dropoff"), (b, "pickup"), (b, "dropoff")]
    late_seconds = (LATE_PICKUP_TOLERANCE_MINUTES + 20) * 60
    durations = _biased_durations(index, sequence, [10, late_seconds, 10])
    trip_start = min(_as_utc(m.requested_pickup_at) for m in members)

    total, order, offsets = _best_ordering(members, durations, index, trip_start)

    assert order == []


def test_early_arrival_forces_a_wait_that_delays_later_stops():
    # A is picked up first, then the route would reach B's pickup WAY
    # before B's requested time — this must become a forced wait, not a
    # free early pickup, and that wait must delay A's own dropoff (A is
    # already in the car while the vehicle waits for B).
    a, b = uuid4(), uuid4()
    members = [
        _member(a, requested_offset_minutes=0),
        _member(b, requested_offset_minutes=60),  # B wants pickup an hour later
    ]
    index = _index_for(members)
    sequence = [(a, "pickup"), (b, "pickup"), (a, "dropoff"), (b, "dropoff")]
    # a->b pickup leg is short (arrives way before B's window) on purpose.
    durations = _biased_durations(index, sequence, [60, 120, 60])
    trip_start = min(_as_utc(m.requested_pickup_at) for m in members)

    total, order, offsets = _best_ordering(members, durations, index, trip_start)

    assert order != []
    early_cutoff = 60 * 60 - EARLY_PICKUP_TOLERANCE_MINUTES * 60
    # B's pickup offset must be pushed out to (at least) the early
    # tolerance boundary, not the raw 60+... arrival time.
    assert offsets[b]["pickup"] >= early_cutoff
    # The forced wait before B's pickup happened while A was already
    # aboard, so A's dropoff (which comes after B's pickup in this
    # route) is correspondingly delayed past the no-wait raw time.
    raw_no_wait_dropoff = 60 + 120  # pickup A(0) -> pickup B(60) -> dropoff A(180)
    assert offsets[a]["dropoff"] > raw_no_wait_dropoff


# -- _write_etas ------------------------------------------------------


@dataclass
class FakeBooking:
    id: UUID
    requested_pickup_at: datetime
    estimated_pickup_at: datetime | None = None
    estimated_dropoff_at: datetime | None = None


def test_write_etas_anchors_to_earliest_requested_pickup():
    from app.services.dispatch_service import _write_etas

    base = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    a, b = uuid4(), uuid4()
    ba = FakeBooking(a, base)
    bb = FakeBooking(b, base + timedelta(minutes=10))
    offsets = {
        a: {"pickup": 0.0, "dropoff": 1800.0},
        b: {"pickup": 300.0, "dropoff": 2400.0},
    }
    _write_etas([ba, bb], offsets, total_duration_seconds=2400.0)

    assert ba.estimated_pickup_at == base
    assert ba.estimated_dropoff_at == base + timedelta(seconds=1800)
    assert bb.estimated_pickup_at == base + timedelta(seconds=300)
    assert bb.estimated_dropoff_at == base + timedelta(seconds=2400)


# -- tz regression ----------------------------------------------------


def test_as_utc_makes_naive_and_aware_subtractable():
    naive = datetime(2026, 7, 25, 8, 0)  # no tzinfo
    aware = datetime(2026, 7, 25, 7, 30, tzinfo=timezone.utc)
    # This is exactly the subtraction find_returning_vehicle does; before
    # the fix, one side naive + one aware raised TypeError.
    gap = (_as_utc(naive) - _as_utc(aware)).total_seconds() / 60
    assert gap == 30

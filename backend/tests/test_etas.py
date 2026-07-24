"""
Phase 2 coverage: real per-stop ETAs, and the timezone regression in
find_returning_vehicle's gap calculation.

These exercise the pure scheduling helpers directly (no DB) plus the
_write_etas writer against lightweight stand-ins, which is enough to pin
the two behaviors the plan calls out: (1) ETAs reflect real per-leg
times, not an even split, and per-passenger dropoffs differ; (2) mixing
a naive and an aware datetime no longer raises.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.services.pool_insertion import Stop, _as_utc, stop_schedule


def _index_for(members):
    """Build the (booking_id, kind) -> coord-slot index the same way
    evaluate_insertion does: pickup then dropoff per member."""
    index = {}
    slot = 0
    for bid in members:
        index[(bid, "pickup")] = slot
        slot += 1
        index[(bid, "dropoff")] = slot
        slot += 1
    return index


def test_stop_schedule_uses_real_leg_times_not_even_split():
    a, b, c = uuid4(), uuid4(), uuid4()
    index = _index_for([a, b, c])
    # Ordered route: pA, pB, pC, dA, dB, dC with deliberately uneven legs.
    order = [
        Stop(a, "pickup", (0, 0)),
        Stop(b, "pickup", (0, 0)),
        Stop(c, "pickup", (0, 0)),
        Stop(a, "dropoff", (0, 0)),
        Stop(b, "dropoff", (0, 0)),
        Stop(c, "dropoff", (0, 0)),
    ]
    # leg durations between consecutive stops: 120s, 1500s, 180s, 60s, 90s
    seq_slots = [index[(s.booking_id, s.kind)] for s in order]
    leg_secs = [120, 1500, 180, 60, 90]
    durations = {}
    for (i_slot, j_slot), secs in zip(zip(seq_slots, seq_slots[1:]), leg_secs):
        durations[(i_slot, j_slot)] = float(secs)

    offsets = stop_schedule(order, durations, index)

    # Pickups happen at cumulative sums: A=0, B=120, C=1620.
    assert offsets[a]["pickup"] == 0
    assert offsets[b]["pickup"] == 120
    assert offsets[c]["pickup"] == 1620
    # These are NOT an even split of the total route (1950s / 5 legs).
    assert offsets[b]["pickup"] != offsets[c]["pickup"]


def test_each_passenger_gets_a_distinct_dropoff_offset():
    a, b = uuid4(), uuid4()
    index = _index_for([a, b])
    order = [
        Stop(a, "pickup", (0, 0)),
        Stop(b, "pickup", (0, 0)),
        Stop(a, "dropoff", (0, 0)),
        Stop(b, "dropoff", (0, 0)),
    ]
    slots = [index[(s.booking_id, s.kind)] for s in order]
    durations = {
        (slots[0], slots[1]): 300.0,
        (slots[1], slots[2]): 600.0,
        (slots[2], slots[3]): 400.0,
    }
    offsets = stop_schedule(order, durations, index)
    # A dropped at 300+600=900, B dropped at 900+400=1300 — distinct, not
    # both equal to total route duration.
    assert offsets[a]["dropoff"] == 900
    assert offsets[b]["dropoff"] == 1300
    assert offsets[a]["dropoff"] != offsets[b]["dropoff"]


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

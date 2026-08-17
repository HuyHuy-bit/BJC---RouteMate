"""
Stop ordering responds to where the car actually is.

The dispatcher's question is not just "who shares this car" but "in what
order does the driver collect and deliver them", and the answer depends
on where the car starts. A route planned without an anchor is free to
begin at whichever stop is cheapest, which quietly models a car that
teleported to its first pickup.

These run offline: the routing circuit is forced open so distances come
from the haversine fallback, which is deterministic and needs no API key.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.pool_insertion import (
    PoolMember,
    best_ordering_from_position,
    compute_solo_baseline,
)
from app.services.routing import routing_service

BASE = (21.2739, 106.1948)  # 167 Xương Giang — the depot
HA_NOI = (21.0285, 105.8542)

# Two pickups on opposite sides of Bắc Giang: one a few hundred metres
# from the depot, one well out of town in the other direction.
NEAR_BASE = (21.2760, 106.1975)
FAR_FROM_BASE = (21.3400, 106.2600)

T0 = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def force_degraded_routing():
    original = routing_service._circuit_open_until
    routing_service._circuit_open_until = time.time() + 3600
    yield
    routing_service._circuit_open_until = original


def _member(pickup, minutes=0.0):
    return PoolMember(
        booking_id=uuid4(),
        pickup=pickup,
        dropoff=HA_NOI,
        requested_pickup_at=T0 + timedelta(minutes=minutes),
        solo_duration_seconds=compute_solo_baseline(pickup, HA_NOI),
        seats=1,
    )


def _first_pickup(ordered_stops):
    return next(s.coord for s in ordered_stops if s.kind == "pickup")


def test_car_starting_at_base_collects_the_nearer_passenger_first():
    near, far = _member(NEAR_BASE), _member(FAR_FROM_BASE)
    _total, stops, _offsets = best_ordering_from_position([near, far], BASE)

    assert stops, "no ordering produced"
    assert _first_pickup(stops) == NEAR_BASE, (
        "a car leaving the depot should collect the passenger next door "
        "before the one out of town"
    )


def test_the_order_follows_the_car_not_the_booking_times():
    """
    Same two passengers, same requested times — only the car's position
    differs. If the anchor is doing its job, the order flips.
    """
    near, far = _member(NEAR_BASE), _member(FAR_FROM_BASE)

    _t1, from_base, _o1 = best_ordering_from_position([near, far], BASE)
    _t2, from_out_of_town, _o2 = best_ordering_from_position(
        [near, far], (21.3500, 106.2700)
    )

    assert _first_pickup(from_base) == NEAR_BASE
    assert _first_pickup(from_out_of_town) == FAR_FROM_BASE, (
        "stop order ignored the vehicle's position — this is the whole "
        "point of anchoring the solve"
    )


def test_every_passenger_is_picked_up_before_they_are_dropped_off():
    # The precedence constraint the solver exists to honour. Cheap to
    # assert and catastrophic to get wrong.
    members = [_member(NEAR_BASE), _member(FAR_FROM_BASE, minutes=8)]
    _total, stops, _offsets = best_ordering_from_position(members, BASE)

    seen = set()
    for stop in stops:
        if stop.kind == "dropoff":
            assert stop.booking_id in seen, (
                "a passenger was dropped off before being picked up"
            )
        else:
            seen.add(stop.booking_id)
    assert len(stops) == 2 * len(members), "every stop should appear exactly once"


def test_a_single_passenger_still_gets_a_usable_order():
    _total, stops, offsets = best_ordering_from_position([_member(NEAR_BASE)], BASE)
    assert [s.kind for s in stops] == ["pickup", "dropoff"]
    assert offsets, "a solo run still needs stop offsets for its ETAs"


def test_no_members_is_handled_rather_than_crashing():
    total, stops, offsets = best_ordering_from_position([], BASE)
    assert (total, stops, offsets) == (0.0, [], {})

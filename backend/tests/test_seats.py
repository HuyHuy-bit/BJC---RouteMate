"""
Phase 6 coverage: a booking can occupy more than one seat.

Capacity everywhere has to SUM seats rather than count booking rows —
one booking can be a family of three. These pin the matching-side
checks; the database-level trigger (enforce_trip_capacity, rewritten in
migration 0014) is the other half and is verified live against Postgres,
since a plpgsql trigger can't be exercised from a pure unit test.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.dispatch_config import MAX_PASSENGERS
from app.services.dispatch_engine import PoolSnapshot, SealDecision, evaluate_pool
from app.services.pool_insertion import PoolMember, compute_solo_baseline, evaluate_insertion
from app.services.routing import routing_service

BASE_TIME = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
AREA = (21.20, 106.10)
DROPOFF = (21.0285, 105.8542)


@pytest.fixture(autouse=True)
def force_degraded_routing():
    """Force the routing circuit open so every call uses the haversine
    fallback — deterministic and network-free."""
    original = routing_service._circuit_open_until
    routing_service._circuit_open_until = time.time() + 3600
    yield
    routing_service._circuit_open_until = original


def _member(seats=1, minutes=0.0, jitter=0.0) -> PoolMember:
    pickup = (AREA[0] + jitter, AREA[1] + jitter)
    return PoolMember(
        booking_id=uuid4(),
        pickup=pickup,
        dropoff=DROPOFF,
        requested_pickup_at=BASE_TIME + timedelta(minutes=minutes),
        solo_duration_seconds=compute_solo_baseline(pickup, DROPOFF),
        seats=seats,
    )


# -- matching-side capacity -------------------------------------------


def test_two_two_seat_bookings_fill_a_four_seat_car():
    # 2 + 2 = 4 seats across only TWO bookings. Counting rows would say
    # "2 of 4 passengers, room for more"; counting seats says full.
    a = _member(seats=2, minutes=0)
    b = _member(seats=2, minutes=2, jitter=0.001)
    third = _member(seats=1, minutes=3, jitter=0.002)

    # The second 2-seat booking still fits (2 + 2 == 4).
    assert evaluate_insertion([a], b).feasible

    # A third 1-seat booking does not — the car is physically full.
    result = evaluate_insertion([a, b], third)
    assert not result.feasible
    assert "seat" in (result.reason or "").lower()


def test_a_three_seat_booking_cannot_join_a_two_seat_pool():
    a = _member(seats=2, minutes=0)
    family = _member(seats=3, minutes=2, jitter=0.001)
    result = evaluate_insertion([a], family)
    assert not result.feasible  # 2 + 3 = 5 > 4


def test_capacity_argument_allows_a_larger_vehicle_to_be_filled():
    # Same four riders that exactly fill a 4-seat car, plus a fifth —
    # rejected at the default capacity, accepted when the pool is
    # already committed to a 7-seat van. Vehicle.seat_capacity existed
    # all along but nothing read it, so a bigger van could never be
    # filled past MAX_PASSENGERS.
    members = [_member(seats=1, minutes=i, jitter=0.001 * i) for i in range(4)]
    fifth = _member(seats=1, minutes=5, jitter=0.005)

    assert not evaluate_insertion(members, fifth).feasible
    assert evaluate_insertion(members, fifth, capacity=7).feasible


def test_seat_count_does_not_change_behavior_for_ordinary_solo_bookings():
    # Regression guard: everything defaults to 1 seat, so the pre-Phase-6
    # behavior (four solo riders fill a car) must be untouched.
    members = [_member(seats=1, minutes=i, jitter=0.001 * i) for i in range(3)]
    fourth = _member(seats=1, minutes=4, jitter=0.004)
    assert evaluate_insertion(members, fourth).feasible


# -- seal decision ----------------------------------------------------


def _snapshot(seat_count, passenger_count, capacity=MAX_PASSENGERS):
    return PoolSnapshot(
        pool_id=uuid4(),
        direction="outbound",
        passenger_count=passenger_count,
        earliest_requested_pickup=BASE_TIME,
        created_at=BASE_TIME,
        seat_count=seat_count,
        capacity=capacity,
    )


def test_pool_seals_as_full_on_seats_not_booking_count():
    # Two bookings, four seats: full, and must seal immediately rather
    # than sit waiting for a third booking it has no room for.
    snap = _snapshot(seat_count=4, passenger_count=2)
    decision = evaluate_pool(snap, now=BASE_TIME)
    assert decision.decision is SealDecision.SEAL
    assert "full" in decision.reason


def test_pool_below_seat_capacity_still_waits():
    snap = _snapshot(seat_count=3, passenger_count=2)
    decision = evaluate_pool(snap, now=BASE_TIME)
    assert decision.decision is SealDecision.WAIT


def test_larger_vehicle_capacity_keeps_a_four_seat_pool_open():
    # Four seats in a 7-seat van is NOT full — it should keep filling.
    snap = _snapshot(seat_count=4, passenger_count=2, capacity=7)
    decision = evaluate_pool(snap, now=BASE_TIME)
    assert decision.decision is SealDecision.WAIT

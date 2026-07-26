"""
A cancelled rider must disappear from a LIVE trip but stay in the
historical record.

The API used to return every booking attached to a trip regardless of
status. On a live trip that meant a passenger who had cancelled was
still handed to the driver as a stop to drive to, and every UI that
sums over trip.bookings — seat occupancy, expected revenue — counted
them. Measured on real data: a 2-rider pool where one cancelled
reported 4 seats and 600,000₫ instead of 1 seat and 150,000₫.

Blanket-filtering them everywhere would have broken History, where a
cancelled trip's whole point is the record of who cancelled — hence the
split on trip status rather than a single rule.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.api.v1.routes.dispatch import FINISHED_TRIP_STATUSES, _to_trip_out
from app.models.enums import BookingStatus, TripStatus


@dataclass
class FakeCustomer:
    id: UUID = field(default_factory=uuid4)
    full_name: str = "Khách"
    phone: str = "0900000000"
    created_at: datetime = datetime(2026, 7, 25, tzinfo=timezone.utc)


@dataclass
class FakeBooking:
    """Only the attributes to_booking_out actually touches."""

    status: BookingStatus
    seats: int = 1
    price_vnd: int = 150_000
    is_private: bool = False
    id: UUID = field(default_factory=uuid4)
    customer: FakeCustomer = field(default_factory=FakeCustomer)
    customer_id: UUID = field(default_factory=uuid4)
    pickup_address: str = "P"
    dropoff_address: str = "D"
    requested_pickup_at: datetime = datetime(2026, 7, 25, 8, tzinfo=timezone.utc)
    estimated_pickup_at: datetime | None = None
    estimated_dropoff_at: datetime | None = None
    direction: str = "outbound"
    trip_id: UUID | None = None
    payment: object | None = None
    created_at: datetime = datetime(2026, 7, 25, tzinfo=timezone.utc)
    # to_booking_out reads coordinates through to_shape(); patched below.
    pickup_point: object = None
    dropoff_point: object = None


@dataclass
class FakeTrip:
    status: TripStatus
    bookings: list
    id: UUID = field(default_factory=uuid4)
    driver_id: UUID | None = None
    vehicle_id: UUID | None = None
    vehicle_label: str | None = "Xe 1"
    created_at: datetime = datetime(2026, 7, 25, tzinfo=timezone.utc)
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class _Point:
    x = 105.85
    y = 21.02


@pytest.fixture(autouse=True)
def stub_geometry(monkeypatch):
    """to_booking_out converts PostGIS points; these fakes have none."""
    monkeypatch.setattr(
        "app.services.booking_service.to_shape", lambda _p: _Point()
    )


def _trip(status, statuses_and_seats):
    return FakeTrip(
        status=status,
        bookings=[
            FakeBooking(status=s, seats=seats)
            for s, seats in statuses_and_seats
        ],
    )


def test_live_trip_drops_cancelled_and_no_show_riders():
    trip = _trip(
        TripStatus.assigned,
        [
            (BookingStatus.locked, 1),
            (BookingStatus.cancelled, 2),
            (BookingStatus.no_show, 1),
        ],
    )
    out = _to_trip_out(trip)

    assert len(out.bookings) == 1
    assert sum(b.seats for b in out.bookings) == 1  # not 4
    assert sum(b.price_vnd for b in out.bookings) == 150_000  # not 600,000


def test_finished_trip_keeps_the_full_record():
    for status in FINISHED_TRIP_STATUSES:
        trip = _trip(
            status,
            [(BookingStatus.completed, 1), (BookingStatus.no_show, 1)],
        )
        out = _to_trip_out(trip)
        assert len(out.bookings) == 2, (
            f"{status.value} trip must keep its full history — that record IS "
            "the point of the history view"
        )


def test_is_private_ignores_cancelled_riders():
    # One private rider left after the other cancelled: still a private
    # hire. Counting the cancelled booking made len() == 2 and reported
    # it as a shared trip.
    trip = _trip(TripStatus.assigned, [])
    trip.bookings = [
        FakeBooking(status=BookingStatus.locked, is_private=True),
        FakeBooking(status=BookingStatus.cancelled, is_private=False),
    ]
    assert _to_trip_out(trip).is_private is True


def test_a_trip_with_no_survivors_serializes_empty_rather_than_crashing():
    trip = _trip(TripStatus.assigned, [(BookingStatus.cancelled, 1)])
    out = _to_trip_out(trip)
    assert out.bookings == []
    assert out.is_private is False

"""
Getting cars home: the rules about when a return may be raised, what
confirming one actually changes, and what the end-of-day sweep is
allowed to assume.

Every vehicle is based at its corridor's home hub and sleeps there, so
a car that finishes its last run in Hà Nội has to get back before the
next morning — otherwise dispatch starts the day matching bookings
against yesterday's last dropoff.

No database: these exercise the guard logic with stubs. The full
round-trip through HTTP lives in test_workflow_integration.py.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.dispatch_config import AT_BASE_RADIUS_METERS
from app.models.enums import UserRole, VehicleStatus
from app.services.vehicle_return import (
    ReturnError,
    cancel_return,
    confirm_return,
    home_base_of,
    is_at_base,
    request_return,
)

BAC_GIANG = (21.2731, 106.1946)
HA_NOI = (21.0278, 105.8342)


class FakePoint:
    def __init__(self, lat, lng):
        self.y, self.x = lat, lng


@dataclass
class FakeCorridor:
    home_hub_lat: float = BAC_GIANG[0]
    home_hub_lng: float = BAC_GIANG[1]


@dataclass
class FakeVehicle:
    status: VehicleStatus = VehicleStatus.available
    id: UUID = field(default_factory=uuid4)
    home_corridor_id: UUID | None = field(default_factory=uuid4)
    last_location: object | None = None
    last_location_at: datetime | None = None
    return_requested_at: datetime | None = None
    return_requested_by_user_id: UUID | None = None


@dataclass
class FakeUser:
    role: UserRole = UserRole.dispatcher
    id: UUID = field(default_factory=uuid4)


class FakeDB:
    """
    Stands in for the Session. `committed` is what a
    `SELECT ... WHERE status IN (committed)` would return — None means
    the car isn't tied to a live trip.
    """

    def __init__(self, corridor=None, committed=None):
        self._corridor = corridor if corridor is not None else FakeCorridor()
        self._committed = committed
        self.added = []

    def get(self, _model, _pk):
        return self._corridor

    def execute(self, _stmt):
        committed = self._committed

        class Result:
            def scalars(self):
                return self

            def first(self):
                return committed

            def all(self):
                return []

        return Result()

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass


def at(lat_lng):
    return FakePoint(*lat_lng)


def monkeypatch_shape(monkeypatch):
    """to_shape unpacks a PostGIS geometry; these fakes are already
    point-shaped."""
    monkeypatch.setattr("app.services.vehicle_return.to_shape", lambda p: p)


@pytest.fixture(autouse=True)
def _shape(monkeypatch):
    monkeypatch_shape(monkeypatch)


# --------------------------------------------------------------------
# Home base is derived, not hardcoded
# --------------------------------------------------------------------


def test_home_base_comes_from_the_corridor():
    """The hubs used to be constants in geo.py, which misclassified
    every booking on a second route. Writing "Bắc Giang" into the
    return logic would repeat that."""
    db = FakeDB(FakeCorridor(home_hub_lat=10.0, home_hub_lng=20.0))
    assert home_base_of(db, FakeVehicle()) == (10.0, 20.0)


def test_untagged_vehicle_has_no_base():
    assert home_base_of(FakeDB(), FakeVehicle(home_corridor_id=None)) is None


def test_at_base_uses_real_distance():
    db = FakeDB()
    assert is_at_base(db, FakeVehicle(last_location=at(BAC_GIANG))) is True
    assert is_at_base(db, FakeVehicle(last_location=at(HA_NOI))) is False


def test_unknown_position_does_not_count_as_home():
    """A car nobody can locate is exactly the one worth asking about;
    assuming it's home would suppress the instruction to bring it back."""
    assert is_at_base(FakeDB(), FakeVehicle(last_location=None)) is False


def test_just_inside_the_base_radius_counts_as_home():
    # ~1km north of the hub, comfortably inside AT_BASE_RADIUS_METERS.
    nearby = (BAC_GIANG[0] + 0.009, BAC_GIANG[1])
    assert AT_BASE_RADIUS_METERS >= 1000
    assert is_at_base(FakeDB(), FakeVehicle(last_location=at(nearby))) is True


# --------------------------------------------------------------------
# Requesting a return
# --------------------------------------------------------------------


def test_dispatcher_can_call_a_stranded_car_home():
    v = FakeVehicle(last_location=at(HA_NOI))
    request_return(FakeDB(), v, FakeUser(), reason="no demand left")
    assert v.status is VehicleStatus.returning
    assert v.return_requested_at is not None


def test_the_request_records_who_asked():
    actor = FakeUser()
    v = FakeVehicle(last_location=at(HA_NOI))
    request_return(FakeDB(), v, actor, reason="x")
    assert v.return_requested_by_user_id == actor.id


def test_the_sweep_records_no_requester():
    """actor=None is the end-of-day sweep — the same is_automatic
    distinction dispatch_events already draws."""
    v = FakeVehicle(last_location=at(HA_NOI))
    request_return(FakeDB(), v, None, reason="end of day")
    assert v.return_requested_by_user_id is None


def test_cannot_call_home_a_car_already_at_base():
    v = FakeVehicle(last_location=at(BAC_GIANG))
    with pytest.raises(ReturnError, match="đã ở Bắc Giang"):
        request_return(FakeDB(), v, FakeUser(), reason="x")


def test_cannot_call_home_twice():
    v = FakeVehicle(status=VehicleStatus.returning, last_location=at(HA_NOI))
    with pytest.raises(ReturnError, match="đã được yêu cầu"):
        request_return(FakeDB(), v, FakeUser(), reason="x")


@pytest.mark.parametrize(
    "status",
    [
        VehicleStatus.assigned,
        VehicleStatus.on_trip,
        VehicleStatus.maintenance,
        VehicleStatus.offline,
    ],
)
def test_cannot_call_home_a_busy_car(status):
    v = FakeVehicle(status=status, last_location=at(HA_NOI))
    with pytest.raises(ReturnError):
        request_return(FakeDB(), v, FakeUser(), reason="x")


def test_a_live_trip_blocks_the_return_even_if_the_status_disagrees():
    """Belt and braces: the trip table is the authority on whether a
    car is committed, not the status flag on the car."""
    v = FakeVehicle(status=VehicleStatus.available, last_location=at(HA_NOI))
    db = FakeDB(committed=uuid4())
    with pytest.raises(ReturnError, match="đang hoạt động"):
        request_return(db, v, FakeUser(), reason="x")


# --------------------------------------------------------------------
# Confirming and cancelling
# --------------------------------------------------------------------


def test_confirming_moves_the_car_home_and_frees_it():
    v = FakeVehicle(status=VehicleStatus.returning, last_location=at(HA_NOI))
    v.return_requested_at = datetime.now(timezone.utc)
    confirm_return(FakeDB(), v, FakeUser(role=UserRole.driver))

    assert v.status is VehicleStatus.available
    assert v.return_requested_at is None
    assert v.return_requested_by_user_id is None
    assert v.last_location_at is not None
    # The WKT the service writes should carry the hub coordinates.
    assert str(BAC_GIANG[0]) in str(v.last_location.data)


def test_cannot_confirm_a_return_nobody_asked_for():
    v = FakeVehicle(status=VehicleStatus.available)
    with pytest.raises(ReturnError, match="không có yêu cầu"):
        confirm_return(FakeDB(), v, FakeUser())


def test_cannot_confirm_without_a_corridor_to_return_to():
    v = FakeVehicle(status=VehicleStatus.returning, home_corridor_id=None)
    with pytest.raises(ReturnError, match="chưa được gán tuyến"):
        confirm_return(FakeDB(), v, FakeUser())


def test_cancelling_frees_the_car_without_moving_it():
    """A cancelled return means the car is wanted where it is — its
    position hasn't changed and must not be rewritten."""
    where_it_is = at(HA_NOI)
    v = FakeVehicle(status=VehicleStatus.returning, last_location=where_it_is)
    v.return_requested_at = datetime.now(timezone.utc)

    cancel_return(FakeDB(), v, FakeUser())

    assert v.status is VehicleStatus.available
    assert v.return_requested_at is None
    assert v.last_location is where_it_is


def test_cannot_cancel_a_return_nobody_asked_for():
    with pytest.raises(ReturnError, match="không có yêu cầu"):
        cancel_return(FakeDB(), FakeVehicle(), FakeUser())


# --------------------------------------------------------------------
# The invariant the whole workflow rests on
# --------------------------------------------------------------------


def test_requesting_a_return_never_moves_the_car():
    """
    The sweep and the dispatcher both only ASK. Nothing may write a
    position the driver hasn't confirmed: _assign_vehicle trusts fresh
    timestamps and discards stale ones, so an assumed location wearing
    a fresh timestamp is worse than an honestly stale one.
    """
    where_it_is = at(HA_NOI)
    v = FakeVehicle(last_location=where_it_is, last_location_at=None)

    request_return(FakeDB(), v, None, reason="end of operating day")

    assert v.last_location is where_it_is
    assert v.last_location_at is None

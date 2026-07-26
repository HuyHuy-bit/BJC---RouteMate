"""
The driver/dispatcher workflow against a real database, driven through
the HTTP API.

Everything else in this suite runs on fake objects, which is fast and
needs no infrastructure — but it cannot see the things this workflow is
actually about: that a dispatcher's token is refused by a route, that
finalizing moves a vehicle's PostGIS position, that two transactions
racing for one car can't both win.

Skipped unless a real PostGIS database is reachable, so the default
`pytest` run stays offline and infrastructure-free:

    docker compose up -d db
    DATABASE_URL=postgresql+psycopg://xeghep:...@localhost:5432/xeghep \
        pytest -m integration

Each test seeds its own corridor/users/vehicle under a unique tag and
never asserts on global totals, so runs don't interfere with each other
or with existing data.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration


def _database_available() -> bool:
    """Skip rather than fail when there's no database — the point is
    that the rest of the suite stays runnable without one."""
    url = os.environ.get("DATABASE_URL", "")
    if "localhost:5432" not in url and "@db:" not in url and ":55432" not in url:
        return False
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytest.importorskip("fastapi.testclient")
if not _database_available():
    pytest.skip(
        "no PostGIS database reachable; run with docker compose up -d db",
        allow_module_level=True,
    )

from fastapi.testclient import TestClient  # noqa: E402
from geoalchemy2.elements import WKTElement  # noqa: E402
from geoalchemy2.shape import to_shape  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.booking import Booking  # noqa: E402
from app.models.corridor import Corridor  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.enums import (  # noqa: E402
    BookingDirection,
    BookingStatus,
    PaymentStatus,
    TripStatus,
    UserRole,
    VehicleStatus,
)
from app.models.payment import Payment  # noqa: E402
from app.models.trip import Trip  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402

BAC_GIANG = (21.2731, 106.1946)
HA_NOI = (21.0278, 105.8342)


def _point(lat_lng):
    lat, lng = lat_lng
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def auth(user) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def world(db):
    """A corridor, one of each role, one car, one rider, one assigned
    trip — the minimum needed to exercise the workflow."""
    tag = uuid.uuid4().hex[:8]

    corridor = Corridor(
        name=f"BG-HN {tag}",
        home_hub_name="Bắc Giang",
        home_hub_lat=BAC_GIANG[0],
        home_hub_lng=BAC_GIANG[1],
        away_hub_name="Hà Nội",
        away_hub_lat=HA_NOI[0],
        away_hub_lng=HA_NOI[1],
        is_active=True,
        base_fare_vnd=150_000,
    )
    admin = User(full_name="Admin", phone=f"a{tag}",
                 hashed_password=hash_password("x"), role=UserRole.admin)
    dispatcher = User(full_name="Dispatcher", phone=f"d{tag}",
                      hashed_password=hash_password("x"), role=UserRole.dispatcher)
    driver = User(full_name="Driver", phone=f"v{tag}",
                  hashed_password=hash_password("x"), role=UserRole.driver)
    other_driver = User(full_name="Other", phone=f"o{tag}",
                        hashed_password=hash_password("x"), role=UserRole.driver)
    db.add_all([corridor, admin, dispatcher, driver, other_driver])
    db.flush()

    vehicle = Vehicle(
        plate_number=f"29A-{tag[:5]}", label=f"Car-{tag[:4]}", seat_capacity=4,
        status=VehicleStatus.assigned, home_corridor_id=corridor.id,
        # default_driver_id is the only durable driver->car link, and is
        # what GET /vehicles/mine and the confirm-return permission both
        # resolve through.
        default_driver_id=driver.id,
        last_location=_point(BAC_GIANG),
        last_location_at=datetime.now(timezone.utc),
    )
    customer = Customer(full_name="Khách", phone=f"c{tag}",
                        phone_lookup_hash=f"h{tag}")
    db.add_all([vehicle, customer])
    db.flush()

    trip = Trip(
        corridor_id=corridor.id, direction=BookingDirection.outbound,
        status=TripStatus.assigned, vehicle_id=vehicle.id,
        driver_id=driver.id, vehicle_label=vehicle.label,
    )
    db.add(trip)
    db.flush()

    booking = Booking(
        customer_id=customer.id, trip_id=trip.id, corridor_id=corridor.id,
        pickup_address="A", pickup_point=_point(BAC_GIANG),
        dropoff_address="B", dropoff_point=_point(HA_NOI),
        price_vnd=150_000, seats=1, stop_order=1,
        requested_pickup_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        direction=BookingDirection.outbound, status=BookingStatus.locked,
    )
    db.add(booking)
    db.flush()
    db.add(Payment(booking_id=booking.id, expected_amount_vnd=150_000,
                   status=PaymentStatus.pending))
    db.commit()

    return {
        "tag": tag, "corridor": corridor, "admin": admin,
        "dispatcher": dispatcher, "driver": driver, "other_driver": other_driver,
        "vehicle": vehicle, "trip": trip, "booking": booking,
        "url": f"/api/v1/dispatch/trips/{trip.id}",
    }


# --------------------------------------------------------------------
# The role boundary, over HTTP
# --------------------------------------------------------------------


@pytest.mark.parametrize("actor_key", ["dispatcher", "admin"])
def test_staff_cannot_accept_or_start(client, world, actor_key):
    """Probed in the state where the transition IS legal, so a 403
    proves the ROLE was refused rather than merely the state."""
    actor = world[actor_key]
    assert client.post(f"{world['url']}/accept", headers=auth(actor)).status_code == 403

    client.post(f"{world['url']}/accept", headers=auth(world["driver"]))
    assert client.post(f"{world['url']}/start", headers=auth(actor)).status_code == 403


def test_driver_cannot_touch_another_drivers_trip(client, world):
    r = client.post(f"{world['url']}/accept", headers=auth(world["other_driver"]))
    assert r.status_code == 403


def test_nobody_can_start_a_trip_no_driver_accepted(client, world):
    r = client.post(f"{world['url']}/start", headers=auth(world["driver"]))
    assert r.status_code == 400


# --------------------------------------------------------------------
# The workflow
# --------------------------------------------------------------------


def test_completion_is_not_completion_until_finalized(client, db, world):
    url, driver = world["url"], world["driver"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))

    r = client.post(f"{url}/request-completion", headers=auth(driver))
    assert r.status_code == 200
    assert r.json()["status"] == "completion_requested"

    db.expire_all()
    trip = db.get(Trip, world["trip"].id)
    assert trip.completed_at is None, "a driver's claim must not complete the trip"
    assert db.get(Vehicle, world["vehicle"].id).status is VehicleStatus.on_trip

    # ...and the driver cannot sign off their own work.
    assert client.post(f"{url}/finalize", headers=auth(driver)).status_code == 403


def test_dispatcher_can_bounce_a_completion_back(client, db, world):
    url, driver = world["url"], world["driver"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))
    client.post(f"{url}/request-completion", headers=auth(driver))

    r = client.post(f"{url}/reject-completion", headers=auth(world["dispatcher"]),
                    json={"reason": "chưa trả khách cuối"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    db.expire_all()
    assert db.get(Trip, world["trip"].id).completed_at is None
    assert db.get(Vehicle, world["vehicle"].id).status is VehicleStatus.on_trip


def test_finalizing_moves_the_car_and_frees_it(client, db, world):
    """Requirements §1: a car that finishes in Hà Nội is an available
    Hà Nội car, and it never disappears."""
    url, driver = world["url"], world["driver"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))
    client.post(f"{url}/request-completion", headers=auth(driver))

    r = client.post(f"{url}/finalize", headers=auth(world["dispatcher"]))
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert r.json()["finalized_by_user_id"] == str(world["dispatcher"].id)

    db.expire_all()
    vehicle = db.get(Vehicle, world["vehicle"].id)
    assert vehicle is not None, "the vehicle must never be deleted"
    assert vehicle.status is VehicleStatus.available
    assert round(to_shape(vehicle.last_location).y, 2) == round(HA_NOI[0], 2)
    assert db.get(Booking, world["booking"].id).status is BookingStatus.completed


def test_finished_trip_leaves_live_trips_but_car_stays_on_the_roster(client, world):
    """The exact shape of the original bug: the fleet view was built
    from live trips, so a finished trip erased the car from the board."""
    url, driver, dispatcher = world["url"], world["driver"], world["dispatcher"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))
    client.post(f"{url}/request-completion", headers=auth(driver))
    client.post(f"{url}/finalize", headers=auth(dispatcher))

    live = client.get("/api/v1/dispatch/trips", headers=auth(dispatcher)).json()
    assert not any(t["id"] == str(world["trip"].id) for t in live)

    fleet = client.get("/api/v1/vehicles", headers=auth(dispatcher)).json()
    row = next((v for v in fleet if v["id"] == str(world["vehicle"].id)), None)
    assert row is not None, "the car vanished from the fleet — the original bug"
    assert row["status"] == "available"
    assert round(row["last_location_lat"], 2) == round(HA_NOI[0], 2)


def test_a_trip_cannot_be_finalized_twice(client, world):
    url, driver, dispatcher = world["url"], world["driver"], world["dispatcher"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))
    client.post(f"{url}/request-completion", headers=auth(driver))
    assert client.post(f"{url}/finalize", headers=auth(dispatcher)).status_code == 200
    assert client.post(f"{url}/finalize", headers=auth(dispatcher)).status_code == 400


def test_driver_keeps_the_trip_on_their_dashboard_until_signed_off(client, world):
    """`completion_requested` belongs to the driver's active list — the
    work is done but the trip is still theirs until approved."""
    url, driver = world["url"], world["driver"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))
    client.post(f"{url}/request-completion", headers=auth(driver))

    mine = client.get("/api/v1/dispatch/my-trips", headers=auth(driver)).json()
    assert any(t["id"] == str(world["trip"].id) for t in mine)


# --------------------------------------------------------------------
# Financial boundary
# --------------------------------------------------------------------


@pytest.mark.parametrize("actor_key", ["dispatcher", "driver"])
@pytest.mark.parametrize("path", ["/revenue-summary", "/dashboard"])
def test_admin_endpoints_are_admin_only(client, world, actor_key, path):
    r = client.get(f"/api/v1/admin{path}", headers=auth(world[actor_key]))
    assert r.status_code == 403


def test_admin_dashboard_survives_an_empty_window(client, world):
    """A window with no finalized trips must not divide by zero — the
    averages are the trap, and a fresh install hits it immediately."""
    r = client.get("/api/v1/admin/dashboard?days=7", headers=auth(world["admin"]))
    assert r.status_code == 200
    d = r.json()
    assert d["avg_revenue_per_trip_vnd"] >= 0
    assert d["avg_seats_per_trip"] >= 0
    assert isinstance(d["daily"], list)


def test_dispatcher_sees_no_money_on_any_booking_endpoint(client, world):
    """
    Requirements §2, the whole of it: no fare and no payment reaches a
    dispatcher from anywhere that carries a booking.
    """
    disp = world["dispatcher"]
    for url, is_flat in [
        ("/api/v1/dispatch/trips", False),
        ("/api/v1/dispatch/history", False),
        ("/api/v1/bookings", True),
    ]:
        r = client.get(url, headers=auth(disp))
        assert r.status_code == 200, url
        payload = r.json()
        rows = payload if is_flat else [b for t in payload for b in t["bookings"]]
        assert all(b["price_vnd"] is None for b in rows), url
        assert all(b["payment"] is None for b in rows), url


def test_driver_sees_fares_only_on_their_own_trips(client, db, world):
    """They collect the cash at the door, so they need the number —
    but only for the car they are actually driving."""
    mine = client.get("/api/v1/dispatch/my-trips", headers=auth(world["driver"])).json()
    assert any(
        b["price_vnd"] is not None for t in mine for b in t["bookings"]
    ), "a driver must see fares on their own trip"

    theirs = client.get(
        "/api/v1/dispatch/trips", headers=auth(world["other_driver"])
    ).json()
    rows = [b for t in theirs if t["id"] == str(world["trip"].id) for b in t["bookings"]]
    assert rows, "the trip should still be visible, just without money"
    assert all(b["price_vnd"] is None for b in rows)


def test_dispatcher_cannot_record_a_collection(client, world):
    r = client.post(
        f"/api/v1/payments/{world['booking'].id}/collect",
        headers=auth(world["dispatcher"]),
        json={"method": "cash", "collected_amount_vnd": 150_000},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------
# Return to base
# --------------------------------------------------------------------


def test_return_to_base_round_trip(client, db, world):
    """Requirements §1: a car stranded in Hà Nội gets called home, and
    the driver confirming is what moves its recorded position."""
    vehicle, dispatcher, driver = world["vehicle"], world["dispatcher"], world["driver"]

    # Strand it: finish the trip so the car is free, then put it in Hà Nội.
    url = world["url"]
    client.post(f"{url}/accept", headers=auth(driver))
    client.post(f"{url}/start", headers=auth(driver))
    client.post(f"{url}/request-completion", headers=auth(driver))
    client.post(f"{url}/finalize", headers=auth(dispatcher))

    db.expire_all()
    assert db.get(Vehicle, vehicle.id).status is VehicleStatus.available

    r = client.post(f"/api/v1/vehicles/{vehicle.id}/request-return", headers=auth(dispatcher))
    assert r.status_code == 200
    assert r.json()["status"] == "returning"
    assert r.json()["return_requested_at"] is not None

    # Still in Hà Nội — asking is not arriving.
    db.expire_all()
    assert round(to_shape(db.get(Vehicle, vehicle.id).last_location).y, 2) == round(
        HA_NOI[0], 2
    )

    r = client.post(f"/api/v1/vehicles/{vehicle.id}/confirm-return", headers=auth(driver))
    assert r.status_code == 200
    assert r.json()["status"] == "available"
    assert r.json()["return_requested_at"] is None
    assert round(r.json()["last_location_lat"], 2) == round(BAC_GIANG[0], 2)


def test_cannot_call_home_a_car_on_a_live_trip(client, world):
    r = client.post(
        f"/api/v1/vehicles/{world['vehicle'].id}/request-return",
        headers=auth(world["dispatcher"]),
    )
    assert r.status_code == 409


def test_only_the_cars_own_driver_confirms_the_return(client, db, world):
    vehicle, dispatcher, driver = world["vehicle"], world["dispatcher"], world["driver"]
    url = world["url"]
    for step in ("accept", "start", "request-completion"):
        client.post(f"{url}/{step}", headers=auth(driver))
    client.post(f"{url}/finalize", headers=auth(dispatcher))
    client.post(f"/api/v1/vehicles/{vehicle.id}/request-return", headers=auth(dispatcher))

    assert (
        client.post(
            f"/api/v1/vehicles/{vehicle.id}/confirm-return",
            headers=auth(world["other_driver"]),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/vehicles/{vehicle.id}/confirm-return", headers=auth(dispatcher)
        ).status_code
        == 403
    )


def test_a_returning_car_is_not_dispatchable(client, db, world):
    """It is physically driving to Bắc Giang — handing it a Hà Nội
    pickup would be a lie."""
    from app.services.dispatch_service import _assign_vehicle

    vehicle, dispatcher, driver = world["vehicle"], world["dispatcher"], world["driver"]
    url = world["url"]
    for step in ("accept", "start", "request-completion"):
        client.post(f"{url}/{step}", headers=auth(driver))
    client.post(f"{url}/finalize", headers=auth(dispatcher))
    client.post(f"/api/v1/vehicles/{vehicle.id}/request-return", headers=auth(dispatcher))

    db.expire_all()
    probe = Trip(
        corridor_id=world["corridor"].id,
        direction=BookingDirection.outbound,
        status=TripStatus.forming,
    )
    db.add(probe)
    db.flush()
    picked = _assign_vehicle(db, probe)
    db.rollback()

    assert picked is None or picked.id != vehicle.id


def test_driver_can_find_their_own_car(client, world):
    r = client.get("/api/v1/vehicles/mine", headers=auth(world["driver"]))
    assert r.status_code == 200
    assert r.json() is not None


def test_a_driver_with_no_car_gets_null_not_an_error(client, world):
    r = client.get("/api/v1/vehicles/mine", headers=auth(world["other_driver"]))
    assert r.status_code == 200
    assert r.json() is None


def test_admin_sees_revenue_summary(client, world):
    r = client.get("/api/v1/admin/revenue-summary", headers=auth(world["admin"]))
    assert r.status_code == 200
    assert set(r.json()) >= {"expected_vnd", "collected_vnd", "trips_finalized"}


@pytest.mark.parametrize("actor_key", ["dispatcher", "driver"])
def test_only_admins_may_waive_a_fare(client, world, actor_key):
    r = client.patch(f"/api/v1/payments/{world['booking'].id}",
                     headers=auth(world[actor_key]), json={"status": "waived"})
    assert r.status_code == 403


def test_dispatcher_still_sees_per_booking_fares(client, world):
    """Agreed scope: dispatchers lose money ROLLUPS, not the individual
    fare they quote a customer."""
    r = client.get("/api/v1/dispatch/trips", headers=auth(world["dispatcher"]))
    assert r.status_code == 200
    trip = next(t for t in r.json() if t["id"] == str(world["trip"].id))
    assert "price_vnd" in trip["bookings"][0]


# --------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------


def test_two_pools_cannot_commit_the_same_car(db, world):
    """Requirements §5, "multiple pending requests for the same vehicle".

    Nothing downstream would catch a double-commit: the database's
    capacity trigger guards seats within ONE trip, not one car across
    two. The FOR UPDATE SKIP LOCKED in _assign_vehicle is the only thing
    standing between two concurrent seals and the same car.
    """
    from app.services.dispatch_service import _assign_vehicle

    corridor = world["corridor"]
    tag = world["tag"]

    only_car = Vehicle(
        plate_number=f"99R-{tag[:5]}", label="OnlyCar", seat_capacity=4,
        status=VehicleStatus.available, home_corridor_id=corridor.id,
        last_location=_point(BAC_GIANG),
        last_location_at=datetime.now(timezone.utc),
    )
    db.add(only_car)
    db.flush()
    pools = []
    for _ in range(2):
        t = Trip(corridor_id=corridor.id, direction=BookingDirection.outbound,
                 status=TripStatus.forming)
        db.add(t)
        pools.append(t)
    db.flush()
    ids = [p.id for p in pools]
    car_id = only_car.id
    db.commit()

    session_a, session_b = SessionLocal(), SessionLocal()
    try:
        won_a = _assign_vehicle(session_a, session_a.get(Trip, ids[0]))
        # session_a holds the row lock and has not committed.
        won_b = _assign_vehicle(session_b, session_b.get(Trip, ids[1]))

        assert won_a is not None and won_a.id == car_id
        assert won_b is None or won_b.id != car_id, (
            "both transactions committed the same car"
        )
        session_a.commit()
        session_b.rollback()
    finally:
        session_a.close()
        session_b.close()

    db.expire_all()
    holders = (
        db.query(Trip)
        .filter(Trip.vehicle_id == car_id)
        .filter(Trip.corridor_id == corridor.id)
        .count()
    )
    assert holders == 1
    assert db.get(Vehicle, car_id).status is VehicleStatus.assigned

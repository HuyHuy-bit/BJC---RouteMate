"""
Getting cars home.

Every vehicle is based at its corridor's home hub and is stationed
there overnight. A car that finishes its last run in Hà Nội therefore
has to get back to Bắc Giang, and until it does, dispatch's picture of
where the fleet is spends the night wrong — the next morning's first
booking would be matched against yesterday's last dropoff.

Two ways home, matching how the business actually works:

  * a dispatcher calls a car back early, when Hà Nội has no demand left
  * the end-of-day sweep sends home whatever is still out there

Both put the car in `returning` and leave a `return_requested_at`
stamp. The driver confirming arrival is what actually moves the
recorded position — nothing here assumes a car got somewhere just
because it was told to go.

Home base is DERIVED from the vehicle's corridor, never hardcoded. The
Corridor table exists because these hubs used to be constants in
geo.py, which silently misclassified every booking on a second route;
writing "Bắc Giang" into this module would walk straight back into it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dispatch_config import AT_BASE_RADIUS_METERS
from app.models.corridor import Corridor
from app.models.enums import DispatchEventType, VehicleStatus
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.geo import haversine_m
from app.services.trip_state import VEHICLE_COMMITTED_STATUSES

logger = logging.getLogger(__name__)


class ReturnError(Exception):
    """Something about this return request doesn't make sense."""


# A car in one of these is doing something a return would interrupt.
# `returning` is absent on purpose — it is handled with its own, more
# specific message rather than a generic "busy".
_BUSY_STATUSES = (
    VehicleStatus.assigned,
    VehicleStatus.on_trip,
    VehicleStatus.maintenance,
    VehicleStatus.offline,
)


def home_base_of(db: Session, vehicle: Vehicle) -> tuple[float, float] | None:
    """(lat, lng) of this vehicle's base, or None if it isn't tagged to
    a corridor. Untagged vehicles are deliberately allowed to exist —
    see Vehicle.home_corridor_id — so every caller has to cope."""
    if vehicle.home_corridor_id is None:
        return None
    corridor = db.get(Corridor, vehicle.home_corridor_id)
    if corridor is None:
        return None
    return corridor.home_hub_lat, corridor.home_hub_lng


def is_at_base(db: Session, vehicle: Vehicle) -> bool:
    """
    Whether the car is already home.

    An unknown position is NOT treated as being at base: a car nobody
    can locate is exactly the one worth asking about, and assuming it's
    home would quietly suppress the instruction to bring it back.
    """
    base = home_base_of(db, vehicle)
    if base is None or vehicle.last_location is None:
        return False
    point = to_shape(vehicle.last_location)
    return haversine_m(base[0], base[1], point.y, point.x) <= AT_BASE_RADIUS_METERS


def _log(
    db: Session,
    event: DispatchEventType,
    vehicle: Vehicle,
    actor: User | None,
    reason: str,
) -> None:
    # Imported here rather than at module scope: dispatch_service
    # imports trip_state, and a top-level import of it from here would
    # close a cycle once dispatch_service starts calling this module.
    from app.services.dispatch_service import log_event

    log_event(
        db,
        event,
        vehicle_id=vehicle.id,
        actor_user_id=actor.id if actor is not None else None,
        reason=reason,
    )


def request_return(
    db: Session, vehicle: Vehicle, actor: User | None, reason: str
) -> None:
    """
    Tell a car to head home. `actor=None` means the end-of-day sweep.

    Refuses anything that would put the vehicle in two stories at once
    — mid-trip, already heading back, or already parked at base.
    """
    if vehicle.status is VehicleStatus.returning:
        raise ReturnError("Xe này đã được yêu cầu quay về Bắc Giang")
    if vehicle.status in _BUSY_STATUSES:
        raise ReturnError(
            f"Xe đang ở trạng thái {vehicle.status.value} — "
            "hãy hoàn tất hoặc huỷ chuyến trước khi gọi xe về"
        )

    # Belt and braces against the status flag drifting from reality: a
    # car whose trip row says it's committed must not be called home
    # even if its own status somehow says available.
    committed = (
        db.execute(
            select(Trip.id)
            .where(Trip.vehicle_id == vehicle.id)
            .where(Trip.status.in_(VEHICLE_COMMITTED_STATUSES))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if committed is not None:
        raise ReturnError("Xe vẫn đang gắn với một chuyến đang hoạt động")

    if is_at_base(db, vehicle):
        raise ReturnError("Xe đã ở Bắc Giang rồi")

    vehicle.status = VehicleStatus.returning
    vehicle.return_requested_at = datetime.now(timezone.utc)
    vehicle.return_requested_by_user_id = actor.id if actor is not None else None
    _log(db, DispatchEventType.return_requested, vehicle, actor, reason)


def confirm_return(db: Session, vehicle: Vehicle, actor: User | None) -> None:
    """
    The driver says they're back. This is the only thing that moves the
    recorded position home — being told to drive somewhere is not
    evidence of having arrived.
    """
    if vehicle.status is not VehicleStatus.returning:
        raise ReturnError("Xe này không có yêu cầu quay về đang chờ")

    base = home_base_of(db, vehicle)
    if base is None:
        raise ReturnError(
            "Xe chưa được gán tuyến nên không xác định được điểm về"
        )

    lat, lng = base
    vehicle.last_location = WKTElement(f"POINT({lng} {lat})", srid=4326)
    vehicle.last_location_at = datetime.now(timezone.utc)
    vehicle.status = VehicleStatus.available
    vehicle.return_requested_at = None
    vehicle.return_requested_by_user_id = None
    _log(
        db,
        DispatchEventType.return_confirmed,
        vehicle,
        actor,
        "driver confirmed arrival at base",
    )


def cancel_return(db: Session, vehicle: Vehicle, actor: User | None) -> None:
    """
    Call it off — usually because a booking turned up and the car is
    wanted where it already is. Returns it to the dispatchable pool
    without touching its position, which hasn't changed.
    """
    if vehicle.status is not VehicleStatus.returning:
        raise ReturnError("Xe này không có yêu cầu quay về đang chờ")

    vehicle.status = VehicleStatus.available
    vehicle.return_requested_at = None
    vehicle.return_requested_by_user_id = None
    _log(
        db,
        DispatchEventType.return_cancelled,
        vehicle,
        actor,
        "return called off",
    )


def send_stranded_vehicles_home(db: Session) -> int:
    """
    End-of-day sweep: every car that isn't at base and isn't busy gets
    told to come home.

    Raises the same `returning` request a dispatcher would, rather than
    silently teleporting the car's position to Bắc Giang. The business
    rule says cars sleep at base, but the system still shouldn't claim
    a car arrived somewhere until its driver says so — otherwise the
    morning's dispatch is built on an assumption wearing a fresh
    timestamp, which is worse than an honestly stale one.
    """
    candidates = (
        db.execute(select(Vehicle).where(Vehicle.status == VehicleStatus.available))
        .scalars()
        .all()
    )

    sent = 0
    for vehicle in candidates:
        try:
            request_return(
                db, vehicle, actor=None, reason="end of operating day"
            )
        except ReturnError:
            # Already home, or busy after all. Both are fine — this
            # sweep is a safety net, not an authority.
            continue
        sent += 1

    if sent:
        db.commit()
        logger.info("end-of-day sweep: asked %s vehicle(s) to return to base", sent)
    return sent

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.corridor import Corridor
from app.models.enums import UserRole
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleLocationPing,
    VehicleOut,
    VehicleUpdate,
)
from app.services.trip_state import (
    DRIVER_ACTIVE_STATUSES,
    VEHICLE_COMMITTED_STATUSES,
)
from app.services.vehicle_return import (
    ReturnError,
    cancel_return,
    confirm_return,
    request_return,
)

router = APIRouter(tags=["vehicles"])

# A vehicle actively committed to a trip cannot be deleted out from under
# real passengers — those states mean people are relying on this specific
# car. Anything else (never used, or only tied to trips already finished
# or cancelled) is safe to remove.
#
# Sourced from trip_state rather than spelled out again here: this list
# and three others like it were maintained by hand, so a new state was
# added to the enum and silently omitted from all of them.
BLOCKING_TRIP_STATUSES = list(VEHICLE_COMMITTED_STATUSES)


def _load_vehicle(db: Session, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
        )
    return vehicle


def to_vehicle_out(vehicle: Vehicle) -> VehicleOut:
    """last_location is a PostGIS Geography, which Pydantic's
    from_attributes cannot read — hence the explicit unpack rather than
    model_validate on its own."""
    lat = lng = None
    if vehicle.last_location is not None:
        point = to_shape(vehicle.last_location)
        lat, lng = point.y, point.x
    return VehicleOut(
        id=vehicle.id,
        plate_number=vehicle.plate_number,
        label=vehicle.label,
        seat_capacity=vehicle.seat_capacity,
        status=vehicle.status,
        default_driver_id=vehicle.default_driver_id,
        home_corridor_id=vehicle.home_corridor_id,
        last_location_at=vehicle.last_location_at,
        last_location_lat=lat,
        last_location_lng=lng,
        return_requested_at=vehicle.return_requested_at,
    )


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    return [
        to_vehicle_out(v)
        for v in db.query(Vehicle).order_by(Vehicle.plate_number).all()
    ]


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    existing = (
        db.query(Vehicle).filter(Vehicle.plate_number == payload.plate_number).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this plate number already exists",
        )
    data = payload.model_dump()
    if data.get("home_corridor_id") is None:
        active_corridors = (
            db.query(Corridor).filter(Corridor.is_active.is_(True)).all()
        )
        if len(active_corridors) == 1:
            data["home_corridor_id"] = active_corridors[0].id
    vehicle = Vehicle(**data)

    # A brand-new vehicle has never completed a trip, so it has no
    # recorded last_location — without this, _assign_vehicle's proximity
    # ordering would treat it as "location unknown, assume far away" and
    # deprioritize it, which is backwards: it's sitting at the depot.
    # Seed it to the home corridor's base hub so it's correctly treated
    # as "at base" from day one.
    if vehicle.home_corridor_id is not None:
        home_corridor = db.get(Corridor, vehicle.home_corridor_id)
        if home_corridor is not None:
            vehicle.last_location = WKTElement(
                f"POINT({home_corridor.home_hub_lng} {home_corridor.home_hub_lat})",
                srid=4326,
            )
            vehicle.last_location_at = datetime.now(timezone.utc)

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return to_vehicle_out(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
        )
    data = payload.model_dump(exclude_unset=True)
    lat = data.pop("last_location_lat", None)
    lng = data.pop("last_location_lng", None)
    for field, value in data.items():
        setattr(vehicle, field, value)
    if lat is not None and lng is not None:
        vehicle.last_location = WKTElement(f"POINT({lng} {lat})", srid=4326)
        vehicle.last_location_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(vehicle)
    return to_vehicle_out(vehicle)


@router.post("/{vehicle_id}/location", response_model=VehicleOut)
def report_location(
    vehicle_id: uuid.UUID,
    payload: VehicleLocationPing,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    A driver reporting where their currently-assigned vehicle is right
    now — see DriverDashboard's periodic ping while a trip is
    assigned/in_progress. Restricted to the driver actually on an active
    trip with this vehicle, not just any driver: last_location directly
    feeds which vehicle gets picked for the next trip, so letting anyone
    overwrite it would make that signal worthless.
    """
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
        )

    is_assigned_driver = (
        current_user.role == UserRole.driver
        and db.query(Trip)
        .filter(Trip.vehicle_id == vehicle_id)
        .filter(Trip.driver_id == current_user.id)
        .filter(Trip.status.in_(DRIVER_ACTIVE_STATUSES))
        .first()
        is not None
    )
    if not is_assigned_driver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the driver currently assigned to this vehicle can report its location",
        )

    vehicle.last_location = WKTElement(f"POINT({payload.lng} {payload.lat})", srid=4326)
    vehicle.last_location_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(vehicle)
    return to_vehicle_out(vehicle)


@router.get("/mine", response_model=VehicleOut | None)
def my_vehicle(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.driver)),
):
    """
    The car this driver is responsible for.

    Needed because a return-to-base instruction outlives the trip that
    stranded the car: once the trip is finalized the driver has no
    active trip to hang it off, so there would be nothing on their
    screen telling them to drive home. Resolved via
    Vehicle.default_driver_id, which is the only durable driver→car
    link in the schema.
    """
    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.default_driver_id == current_user.id)
        .order_by(Vehicle.plate_number)
        .first()
    )
    return to_vehicle_out(vehicle) if vehicle is not None else None


@router.post("/{vehicle_id}/request-return", response_model=VehicleOut)
def request_vehicle_return(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Call a car back to base early — the dispatcher's move when Hà Nội
    has no demand left and there's no reason for the car to wait there.
    """
    vehicle = _load_vehicle(db, vehicle_id)
    try:
        request_return(
            db, vehicle, actor=current_user, reason="dispatcher called the car home"
        )
    except ReturnError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    db.commit()
    db.refresh(vehicle)
    return to_vehicle_out(vehicle)


@router.post("/{vehicle_id}/confirm-return", response_model=VehicleOut)
def confirm_vehicle_return(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The driver reporting they're back at base. Only that car's own
    driver, for the same reason report_location is restricted: this
    write moves the position dispatch trusts when choosing the next
    car, so anyone being able to fake it makes the signal worthless.

    Admins may also confirm, for the case where a driver's phone is
    dead and someone has to record it by hand.
    """
    vehicle = _load_vehicle(db, vehicle_id)

    is_own_driver = (
        current_user.role is UserRole.driver
        and vehicle.default_driver_id == current_user.id
    )
    if not (is_own_driver or current_user.role is UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tài xế của xe này (hoặc quản trị viên) mới xác nhận được",
        )

    try:
        confirm_return(db, vehicle, actor=current_user)
    except ReturnError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    db.commit()
    db.refresh(vehicle)
    return to_vehicle_out(vehicle)


@router.post("/{vehicle_id}/cancel-return", response_model=VehicleOut)
def cancel_vehicle_return(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """Call the return off — a booking turned up and the car is wanted
    where it already is. Its position is untouched; only its
    availability changes."""
    vehicle = _load_vehicle(db, vehicle_id)
    try:
        cancel_return(db, vehicle, actor=current_user)
    except ReturnError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    db.commit()
    db.refresh(vehicle)
    return to_vehicle_out(vehicle)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Removing a car mid-operation is different from removing a customer:
    a vehicle can be mid-trip with real passengers depending on it, so
    deletion is refused (409) while it's actively committed to one.

    Once safe to delete, any trip that historically referenced this
    vehicle (completed, cancelled, or still-forming with no one
    committed yet) has its vehicle_id cleared rather than left dangling
    or blocking the delete forever — the trip and its dispatch history
    stay intact, they just lose the now-gone vehicle link.
    """
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found"
        )

    blocking = (
        db.query(Trip)
        .filter(Trip.vehicle_id == vehicle_id)
        .filter(Trip.status.in_(BLOCKING_TRIP_STATUSES))
        .first()
    )
    if blocking is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Xe đang được giao cho một chuyến đang hoạt động. "
                "Hãy hoàn thành hoặc huỷ chuyến đó trước khi xoá xe."
            ),
        )

    db.query(Trip).filter(Trip.vehicle_id == vehicle_id).update(
        {"vehicle_id": None}
    )
    db.delete(vehicle)
    db.commit()

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import TripStatus, UserRole
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleOut, VehicleUpdate

router = APIRouter(tags=["vehicles"])

# A vehicle actively committed to a trip cannot be deleted out from under
# real passengers — those states mean people are relying on this specific
# car. Anything else (never used, or only tied to trips already finished
# or cancelled) is safe to remove.
BLOCKING_TRIP_STATUSES = [
    TripStatus.sealed,
    TripStatus.assigned,
    TripStatus.in_progress,
    TripStatus.reassigning,
]


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    return db.query(Vehicle).order_by(Vehicle.plate_number).all()


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
    vehicle = Vehicle(**payload.model_dump())
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vehicle, field, value)
    db.commit()
    db.refresh(vehicle)
    return vehicle


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

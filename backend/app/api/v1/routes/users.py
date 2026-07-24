import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import TripStatus, UserRole
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(tags=["users"])

# A driver cannot be deleted if they're currently operating, or drove a
# trip recently enough that the record is still operationally relevant —
# 3 days chosen by the business as the cutoff.
DELETE_LOOKBACK_DAYS = 3
ACTIVE_TRIP_STATUSES = [
    TripStatus.sealed,
    TripStatus.assigned,
    TripStatus.in_progress,
    TripStatus.reassigning,
]


@router.get("", response_model=list[UserOut])
def list_users(
    role: UserRole | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Mainly exists so the dispatch board can populate a driver-assignment
    dropdown (?role=driver). Restricted to admin/dispatcher since it lists
    staff accounts, not something a driver needs to see.
    """
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return query.order_by(User.full_name).all()


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Admin-only. Deactivating rather than deleting is deliberate: a staff
    account is referenced by trips.driver_id, dispatch_events, and the
    audit log — deleting it would either break those foreign keys or
    silently erase who did what. Setting is_active=False revokes login
    immediately while keeping every historical record intact.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.id == current_user.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự khoá tài khoản của chính mình",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Deleting a staff account is a heavier action than deactivating one —
    it permanently frees their phone number for reuse, which deactivation
    deliberately does not do. Blocked while the account is operationally
    live: currently assigned to a trip, or drove/was assigned one within
    the last {DELETE_LOOKBACK_DAYS} days. Older accounts with no recent
    activity are safe to remove outright.

    Both trips.driver_id and vehicles.default_driver_id are real foreign
    keys to this table, so anything that survives the block check still
    needs those references cleared before the row can actually be
    deleted — same pattern as vehicle deletion clearing trip.vehicle_id.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự xoá tài khoản của chính mình",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=DELETE_LOOKBACK_DAYS)

    blocking = (
        db.query(Trip)
        .filter(Trip.driver_id == user.id)
        .filter(
            Trip.status.in_(ACTIVE_TRIP_STATUSES)
            | ((Trip.status == TripStatus.completed) & (Trip.completed_at >= cutoff))
            | ((Trip.status == TripStatus.cancelled) & (Trip.cancelled_at >= cutoff))
        )
        .first()
    )
    if blocking is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nhân viên này đang điều hành hoặc đã chạy chuyến trong "
                f"{DELETE_LOOKBACK_DAYS} ngày qua. Hãy khoá tài khoản thay vì xoá."
            ),
        )

    db.query(Vehicle).filter(Vehicle.default_driver_id == user.id).update(
        {"default_driver_id": None}
    )
    db.query(Trip).filter(Trip.driver_id == user.id).update({"driver_id": None})
    db.delete(user)
    db.commit()

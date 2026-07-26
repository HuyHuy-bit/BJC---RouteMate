import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import TripStatus, UserRole
from app.models.payment import Payment
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.user import UserOut, UserUpdate
from app.services.trip_state import VEHICLE_COMMITTED_STATUSES

router = APIRouter(tags=["users"])

# A driver cannot be deleted if they're currently operating, or drove a
# trip recently enough that the record is still operationally relevant —
# 3 days chosen by the business as the cutoff.
DELETE_LOOKBACK_DAYS = 3
# Sourced from trip_state so a newly added state can't quietly fall out
# of this guard — see the note on vehicles.BLOCKING_TRIP_STATUSES.
ACTIVE_TRIP_STATUSES = list(VEHICLE_COMMITTED_STATUSES)


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
    live: currently assigned to a trip, drove/was assigned one within the
    last {DELETE_LOOKBACK_DAYS} days, or collected money in that window.
    Older accounts with no recent activity are safe to remove outright.

    trips.driver_id, vehicles.default_driver_id AND
    payments.collected_by_user_id are all real foreign keys to this
    table, so anything that survives the block check still needs every
    one of those references cleared before the row can actually be
    deleted — same pattern as vehicle deletion clearing trip.vehicle_id.
    Missing any one of them turns this endpoint into a 500.
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

    # Money they handled recently counts as operationally live too — a
    # cash record from this morning still needs a name against it while
    # the day is being reconciled. Same cutoff as trips.
    recent_payment = (
        db.query(Payment)
        .filter(Payment.collected_by_user_id == user.id)
        .filter(Payment.collected_at >= cutoff)
        .first()
    )
    if recent_payment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Nhân viên này đã thu tiền trong {DELETE_LOOKBACK_DAYS} ngày qua. "
                "Hãy khoá tài khoản thay vì xoá."
            ),
        )

    db.query(Vehicle).filter(Vehicle.default_driver_id == user.id).update(
        {"default_driver_id": None}
    )
    db.query(Trip).filter(Trip.driver_id == user.id).update({"driver_id": None})
    # Who finalized a trip is a second, independent reference to this
    # table — a dispatcher who never drove anything still appears here.
    # The column is ON DELETE SET NULL at the database level too, but
    # clearing it explicitly keeps every users FK handled the same way
    # in one readable place.
    db.query(Trip).filter(Trip.finalized_by_user_id == user.id).update(
        {"finalized_by_user_id": None}
    )
    # Who asked a car to come home must never be the reason a staff
    # account can't be deleted. The return itself stays outstanding;
    # only the requester's name is dropped.
    db.query(Vehicle).filter(Vehicle.return_requested_by_user_id == user.id).update(
        {"return_requested_by_user_id": None}
    )
    # payments.collected_by_user_id is a real foreign key, so an older
    # collection record would otherwise block the delete outright with a
    # 500. Cleared like trips.driver_id above; the payment itself and its
    # amount are preserved, and dispatch_events/audit_log keep the
    # historical actor since neither constrains against this table.
    db.query(Payment).filter(Payment.collected_by_user_id == user.id).update(
        {"collected_by_user_id": None}
    )
    db.delete(user)
    db.commit()

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import BookingStatus, UserRole
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingOut
from app.services.audit import log_pii_access
from app.services.booking_service import create_booking, to_booking_out
from app.services.customer_service import get_or_create_customer
from app.services.dispatch_service import assign_booking, detach_booking_from_trip
from app.services.notification_service import notify_booking_cancelled

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bookings"])


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking_route(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = get_or_create_customer(db, payload.customer)
    booking = create_booking(db, customer, payload)

    log_pii_access(
        db,
        actor_user_id=current_user.id,
        action="create_booking",
        target_type="customer",
        target_id=customer.id,
    )

    # Persist the booking FIRST. Matching used to run inside this
    # transaction, which meant any failure in routing or pool insertion
    # threw away the customer's booking entirely — the one thing that
    # must never be lost. Now a matching failure leaves the booking
    # safely `queued`, and the scheduled dispatch cycle's unmatched-
    # booking sweep picks it up on the next tick.
    db.commit()
    db.refresh(booking)

    try:
        assign_booking(db, booking)
        db.commit()
    except Exception:
        logger.exception(
            "matching failed for booking %s; left queued for the dispatch cycle",
            booking.id,
        )
        db.rollback()

    db.refresh(booking)
    return to_booking_out(booking)


@router.get("", response_model=list[BookingOut])
def list_bookings(
    status_filter: BookingStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Booking).options(joinedload(Booking.customer))
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    bookings = query.order_by(Booking.created_at.desc()).all()

    for b in bookings:
        log_pii_access(
            db,
            actor_user_id=current_user.id,
            action="read_booking",
            target_type="booking",
            target_id=b.id,
        )
    db.commit()
    return [to_booking_out(b) for b in bookings]


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.customer))
        .filter(Booking.id == booking_id)
        .first()
    )
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    log_pii_access(
        db,
        actor_user_id=current_user.id,
        action="read_booking",
        target_type="booking",
        target_id=booking.id,
    )
    db.commit()
    return to_booking_out(booking)


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    A cancellation used to just flip a status flag, leaving a stale
    route and a possibly-reserved vehicle behind for every other
    passenger in the same car. Now it detaches the booking properly:
    the pool's remaining stops get re-optimized, or the whole trip and
    its vehicle are released if this was the last passenger.
    """
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.customer))
        .filter(Booking.id == booking_id)
        .first()
    )
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    detach_booking_from_trip(
        db,
        booking,
        new_status=BookingStatus.cancelled,
        reason="cancelled by customer/staff",
        actor_user_id=current_user.id,
    )
    notify_booking_cancelled(db, booking, reason="Khách hàng huỷ chuyến")

    log_pii_access(
        db,
        actor_user_id=current_user.id,
        action="cancel_booking",
        target_type="booking",
        target_id=booking.id,
    )
    db.commit()


@router.post("/{booking_id}/no-show", response_model=BookingOut)
def mark_no_show(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Driver waited, passenger never showed. Distinct from cancellation:
    this happened mid-operation, so the remaining stops on the route
    need re-optimizing immediately rather than the driver continuing to
    an empty pickup.
    """
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.customer), joinedload(Booking.trip))
        .filter(Booking.id == booking_id)
        .first()
    )
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    is_staff = current_user.role in (UserRole.admin, UserRole.dispatcher)
    is_assigned_driver = (
        current_user.role == UserRole.driver
        and booking.trip is not None
        and booking.trip.driver_id == current_user.id
    )
    if not (is_staff or is_assigned_driver):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff or this trip's driver can mark a no-show",
        )

    detach_booking_from_trip(
        db,
        booking,
        new_status=BookingStatus.no_show,
        reason="marked no-show",
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(booking)
    return to_booking_out(booking)


@router.post("/{booking_id}/unassign", response_model=BookingOut)
def unassign_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Manual override: pull a booking out of its current pool without
    cancelling it. It goes back to `queued`, where the next dispatch
    cycle's unmatched-booking sweep will try to place it again — useful
    when a dispatcher can see a better fit the algorithm didn't find, or
    wants to manually rebalance two forming pools.
    """
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.customer))
        .filter(Booking.id == booking_id)
        .first()
    )
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    if booking.trip_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking is not currently assigned to any trip",
        )

    detach_booking_from_trip(
        db,
        booking,
        new_status=BookingStatus.queued,
        reason="manually unassigned by dispatcher",
        actor_user_id=current_user.id,
    )
    booking.trip_id = None
    db.commit()
    db.refresh(booking)
    return to_booking_out(booking)

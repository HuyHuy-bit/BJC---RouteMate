import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import BookingStatus
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingOut
from app.services.audit import log_pii_access
from app.services.booking_service import create_booking, to_booking_out
from app.services.customer_service import get_or_create_customer
from app.services.dispatch_service import assign_booking

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
    # safely `queued`, and the scheduled dispatch cycle picks it up on
    # the next tick.
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
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    booking.status = BookingStatus.cancelled
    db.commit()

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import PaymentStatus, UserRole
from app.models.user import User
from app.schemas.payment import PaymentAdjust, PaymentCollect, PaymentOut

router = APIRouter(tags=["payments"])


def _load_booking_with_payment(db: Session, booking_id: uuid.UUID) -> Booking:
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.payment), joinedload(Booking.trip))
        .filter(Booking.id == booking_id)
        .first()
    )
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    if booking.payment is None:
        # Shouldn't happen — every booking gets a Payment row at creation
        # (see booking_service.py:create_booking) — but a booking that
        # predates the payments table entirely would hit this until the
        # migration's backfill runs. Fail clearly rather than silently.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This booking has no payment record",
        )
    return booking


@router.post("/{booking_id}/collect", response_model=PaymentOut)
def collect_payment(
    booking_id: uuid.UUID,
    payload: PaymentCollect,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Staff or the booking's assigned driver records what was actually
    collected. `status` becomes `disputed` rather than `collected` if the
    amount falls short — collecting less than owed needs a human to
    reconcile it, not a silent write.
    """
    booking = _load_booking_with_payment(db, booking_id)

    # Dispatchers lost this along with the rest of the financial
    # surface: they never handle the cash, and recording a collection
    # they didn't take is not an operational act. The driver at the
    # door does it; an admin can do it on their behalf.
    is_assigned_driver = (
        current_user.role == UserRole.driver
        and booking.trip is not None
        and booking.trip.driver_id == current_user.id
    )
    if not (current_user.role is UserRole.admin or is_assigned_driver):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only this trip's driver or an admin can record a payment",
        )

    payment = booking.payment
    payment.method = payload.method
    payment.collected_amount_vnd = payload.collected_amount_vnd
    payment.collected_by_user_id = current_user.id
    payment.collected_at = datetime.now(timezone.utc)
    payment.notes = payload.notes
    payment.status = (
        PaymentStatus.collected
        if payload.collected_amount_vnd >= payment.expected_amount_vnd
        else PaymentStatus.disputed
    )

    db.commit()
    db.refresh(payment)
    return PaymentOut.model_validate(payment)


@router.patch("/{booking_id}", response_model=PaymentOut)
def adjust_payment(
    booking_id: uuid.UUID,
    payload: PaymentAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Admin-only correction — waiving a fare, or resolving a disputed one
    after following up with the driver/customer.

    Dispatchers lost this. Writing off money owed is a financial
    decision, not an operational one: it changes what the business
    actually earned, and it is the single endpoint in this service that
    can make a debt disappear without anyone collecting anything.
    Dispatchers still see fares and payment status, because they
    coordinate the drivers who collect the cash — they just cannot
    forgive it.
    """
    booking = _load_booking_with_payment(db, booking_id)

    payment = booking.payment
    payment.status = payload.status
    if payload.notes is not None:
        payment.notes = payload.notes

    db.commit()
    db.refresh(payment)
    return PaymentOut.model_validate(payment)

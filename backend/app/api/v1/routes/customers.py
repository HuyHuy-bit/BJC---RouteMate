import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.trip import Trip
from app.models.user import User
from app.schemas.customer import CustomerOut
from app.services.audit import log_pii_access
from app.services.dispatch_service import release_vehicle_if_free

router = APIRouter(tags=["customers"])


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )

    log_pii_access(
        db,
        actor_user_id=current_user.id,
        action="read_customer_phone",
        target_type="customer",
        target_id=customer.id,
    )
    result = CustomerOut(
        id=customer.id,
        full_name=customer.full_name,
        phone=customer.phone,
        created_at=customer.created_at,
    )
    db.commit()
    return result


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    for c in customers:
        log_pii_access(
            db,
            actor_user_id=current_user.id,
            action="read_customer_phone",
            target_type="customer",
            target_id=c.id,
        )
    db.commit()
    return [
        CustomerOut(id=c.id, full_name=c.full_name, phone=c.phone, created_at=c.created_at)
        for c in customers
    ]


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Hard delete: removes the customer AND all of their bookings
    permanently. Also cleans up any Trip that ends up with zero bookings
    as a result — e.g. a 2-rider shared trip where one rider's customer
    record gets deleted now correctly disappears from the trips list
    instead of lingering as an empty car.
    """
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )

    log_pii_access(
        db,
        actor_user_id=current_user.id,
        action="delete_customer",
        target_type="customer",
        target_id=customer.id,
    )

    bookings = db.query(Booking).filter(Booking.customer_id == customer.id).all()
    affected_trip_ids = {b.trip_id for b in bookings if b.trip_id is not None}
    booking_ids = [b.id for b in bookings]

    # Anything that references those bookings has to go first, or the
    # delete below fails on a foreign key and the whole request 500s.
    # Both of these tables point at bookings.id: notifications (the
    # manual-relay message queue) and payments (one row per booking,
    # created automatically at booking time — so in practice EVERY
    # customer has at least one).
    if booking_ids:
        db.query(Notification).filter(
            Notification.booking_id.in_(booking_ids)
        ).delete(synchronize_session=False)
        db.query(Payment).filter(
            Payment.booking_id.in_(booking_ids)
        ).delete(synchronize_session=False)

    db.query(Booking).filter(Booking.customer_id == customer.id).delete()
    db.delete(customer)
    db.flush()

    for trip_id in affected_trip_ids:
        remaining = db.query(Booking).filter(Booking.trip_id == trip_id).count()
        if remaining == 0:
            trip = db.get(Trip, trip_id)
            if trip is not None:
                # Hand the car back BEFORE the trip row goes, or it is
                # stranded forever: _assign_vehicle only ever picks a
                # vehicle whose status is `available`, and
                # release_vehicle_if_free needs the trip row to work out
                # whether anything else still holds it.
                #
                # Found in production data — a car sat in `assigned`
                # with no trip referencing it at all, invisible to
                # dispatch and impossible to free through the UI,
                # because deleting a customer took its trip out from
                # under it without ever releasing it.
                release_vehicle_if_free(db, trip)
                db.delete(trip)

    db.commit()

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.customer import CustomerOut
from app.services.audit import log_pii_access

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
    permanently. This is deliberately destructive rather than a soft
    delete — it's what satisfies a real customer deletion request under
    Decree 13/2023/NĐ-CP (see docs/DATA_PROTECTION.md), and it's also just
    the practical way to clean up a test/mistaken entry.

    If a deleted booking was part of a Trip with other riders, those other
    riders' bookings are untouched — the Trip row just loses one member.
    A Trip that ends up with zero bookings is left dangling rather than
    auto-deleted; harmless, but worth knowing if you're inspecting the
    trips table directly.
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

    db.query(Booking).filter(Booking.customer_id == customer.id).delete()
    db.delete(customer)
    db.commit()

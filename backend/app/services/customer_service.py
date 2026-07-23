from sqlalchemy.orm import Session

from app.core.encryption import blind_index
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate


def get_or_create_customer(db: Session, payload: CustomerCreate) -> Customer:
    """
    Repeat customers shouldn't get a new row every time they book — look up
    by the phone blind index first (see app/core/encryption.py:blind_index
    for why this works on an encrypted column) and reuse the existing
    record if found. Updates the stored name if it changed.
    """
    lookup_hash = blind_index(payload.phone)
    existing = (
        db.query(Customer).filter(Customer.phone_lookup_hash == lookup_hash).first()
    )
    if existing:
        if existing.full_name != payload.full_name:
            existing.full_name = payload.full_name
        return existing

    customer = Customer(
        full_name=payload.full_name,
        phone=payload.phone,  # EncryptedString handles encryption on write
        phone_lookup_hash=lookup_hash,
    )
    db.add(customer)
    db.flush()  # get an id without committing yet — caller controls the transaction
    return customer

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import EncryptedString


class Customer(Base, TimestampMixin):
    """
    A rider. Phone number is encrypted at rest — the DB column is named
    phone_encrypted, but the Python attribute is just `phone`: reading
    customer.phone automatically decrypts (via EncryptedString), so this
    reads naturally everywhere else in the codebase.

    phone_lookup_hash is a deterministic HMAC of the phone number (see
    app/core/encryption.py:blind_index) so staff can search "does this
    customer already exist" without decrypting every row to compare.
    """

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column("phone_encrypted", EncryptedString(20))
    phone_lookup_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )

    bookings: Mapped[list["Booking"]] = relationship(back_populates="customer")

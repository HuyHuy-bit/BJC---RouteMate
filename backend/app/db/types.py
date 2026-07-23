"""
A column type that encrypts on write and decrypts on read, transparently.

Usage in a model:
    phone: Mapped[str] = mapped_column(EncryptedString(32))

The ORM code reads/writes plain strings as normal — encryption happens at
the DB boundary. What actually lands on disk is ciphertext.
"""

from sqlalchemy import String, TypeDecorator

from app.core.encryption import decrypt_field, encrypt_field


class EncryptedString(TypeDecorator):
    """
    Stores an encrypted string. `length` here describes the plaintext's
    expected max length for documentation purposes only — ciphertext is
    longer than plaintext, so the underlying DB column is sized generously
    and this type does not enforce a DB-level length constraint.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 255, *args, **kwargs):
        # ciphertext (Fernet) is roughly plaintext*1.4 + fixed overhead;
        # pad generously so legitimate values never get truncated
        super().__init__(*args, length=max(length * 2, 255), **kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_field(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_field(value)

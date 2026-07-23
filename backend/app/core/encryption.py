"""
Field-level encryption for PII columns (phone numbers, exact addresses).

Usage pattern: store the ciphertext in the DB column, decrypt only when a
request actually needs the raw value (and that read gets audit-logged at
the route level — see docs/DATA_PROTECTION.md).

PII_ENCRYPTION_KEY must be a Fernet key. Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Losing this key makes all encrypted data permanently unrecoverable — treat
it like a database password, store it in a secrets manager in production.
"""

from cryptography.fernet import Fernet
import hashlib
import hmac

from app.core.config import settings

_fernet = Fernet(settings.pii_encryption_key.encode())


def encrypt_field(plaintext: str) -> str:
    if plaintext is None:
        return None
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str) -> str:
    if ciphertext is None:
        return None
    return _fernet.decrypt(ciphertext.encode()).decode()


def blind_index(value: str) -> str:
    """
    Deterministic HMAC-SHA256 of a normalized value, for equality lookups
    on encrypted columns (e.g. "does this phone number already exist?").

    Fernet encryption is randomized — the same plaintext produces different
    ciphertext each time, which is good for security but means you can't
    query WHERE phone_encrypted = X. This blind index sits alongside the
    encrypted column: same input always produces the same hash, so it's
    indexable and searchable, but (unlike encryption) it can't be reversed
    back to the original value — it only supports exact-match lookup.
    """
    normalized = value.strip().lower()
    return hmac.new(
        settings.pii_encryption_key.encode(), normalized.encode(), hashlib.sha256
    ).hexdigest()

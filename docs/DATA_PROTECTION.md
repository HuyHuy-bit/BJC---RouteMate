# Data Protection

This system stores customer names, phone numbers, and home/work addresses.
Under Vietnam's **Decree 13/2023/NĐ-CP on Personal Data Protection**, this
counts as personal data, and precise pickup/dropoff location is arguably
sensitive personal data (it can reveal home address, workplace, routine).
This document is the working policy — update it as the system grows.

## Principles

1. **Collect only what's needed.** Name, phone, pickup/dropoff address. No
   ID numbers, no unnecessary demographic data.
2. **Encrypt PII at rest.** Phone numbers and exact addresses are encrypted
   at the application layer (not just relying on disk encryption), so a
   database dump alone doesn't expose customer data in plaintext.
3. **Encrypt in transit.** TLS required for any non-local deployment —
   local `docker compose` dev is the only place plaintext HTTP is allowed.
4. **Access control by role.** Dispatchers see what they need to do
   matching; drivers see only their own assigned trip's contact info, not
   the full customer database.
5. **Audit logging.** Every read of raw (decrypted) customer PII is logged:
   who, when, which record. This makes misuse detectable.
6. **Password security.** Argon2 hashing for all staff accounts, never
   logged or stored in plaintext.
7. **Retention & deletion.** Define a retention period (e.g. booking data
   kept 24 months for business records, then anonymized). Customers can
   request their data be deleted — this needs a real process, not just a
   policy statement.
8. **Backups are also PII.** Any database backup inherits all of the above
   — encrypted, access-controlled, not casually copied to a laptop.

## Technical implementation (as built)

| Control | Mechanism |
|---|---|
| PII field encryption | `app/core/encryption.py` — AES via the `cryptography` package, key from environment, never committed |
| Password hashing | `argon2-cffi` via `app/core/security.py` |
| Transport encryption | TLS termination at the reverse proxy in any real deployment |
| Access control | JWT role claims checked per-route in `app/api/v1/routes/` |
| Audit log | Dedicated `audit_log` table, written on every PII read/export |
| Secrets | `.env`, never committed (`.gitignore`'d), `.env.example` documents required keys with placeholder values only |

## Open items to decide with the business

- Formal retention period for cancelled/completed bookings
- Who is the designated person responsible for data protection requests
  (Decree 13 expects an accountable contact point)
- Whether customer consent needs to be captured explicitly at booking time
  (recommended: a short line in the booking confirmation message)

from datetime import datetime, timezone


def as_utc(dt: datetime) -> datetime:
    """
    Normalizes any datetime to timezone-aware UTC.

    Postgres `timestamptz` columns can come back either aware or naive
    depending on driver and session settings, and mixing the two raises
    `TypeError: can't subtract offset-naive and offset-aware datetimes`
    the moment a stored booking is compared against a fresh
    `datetime.now(timezone.utc)`. Normalizing at every boundary is the
    only reliable fix.

    Lives in core, not in a service, because traffic.py and
    pool_insertion.py both need it and pool_insertion already imports
    traffic — anywhere higher up would be an import cycle.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

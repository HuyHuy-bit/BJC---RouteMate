"""
Tripwire for the delete paths.

Two real 500s came from the same mistake: a table was added that
references `users` or `bookings`, but the delete endpoint that removes
those rows was never updated to clear the new reference first. Postgres
then refused the delete on a foreign key and the request blew up —
`DELETE /customers/{id}` broke for essentially every real customer
(payments are created for every booking), and `DELETE /users/{id}` broke
for any driver who had ever collected money.

These tests can't prove the delete logic is *correct* — that needs a
database, and is covered by manual verification. What they do is fail
loudly the moment someone adds another table pointing at users or
bookings, forcing whoever does it to go look at the delete paths rather
than finding out from a production 500.

Reads SQLAlchemy metadata only; no database connection needed.
"""

import app.models  # noqa: F401  (registers every model on the metadata)
from app.db.base import Base

# Every column that references these tables, and therefore has to be
# cleared or deleted before a row can be removed. UPDATE THIS LIST when
# you add a table — and update the matching delete endpoint with it.
EXPECTED_USER_DEPENDENTS = {
    ("trips", "driver_id"),  # cleared in users.delete_user
    ("vehicles", "default_driver_id"),  # cleared in users.delete_user
    ("payments", "collected_by_user_id"),  # cleared in users.delete_user
}

EXPECTED_BOOKING_DEPENDENTS = {
    ("notifications", "booking_id"),  # deleted in customers.delete_customer
    ("payments", "booking_id"),  # deleted in customers.delete_customer
}


def _dependents_of(target_table: str) -> set[tuple[str, str]]:
    """Every (table, column) in the schema with a foreign key pointing
    at `target_table`."""
    found: set[tuple[str, str]] = set()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == target_table:
                    found.add((table.name, column.name))
    return found


def test_every_table_referencing_users_is_accounted_for():
    actual = _dependents_of("users")
    unhandled = actual - EXPECTED_USER_DEPENDENTS
    assert not unhandled, (
        f"New foreign key(s) to users: {sorted(unhandled)}. "
        "users.delete_user must clear these before deleting the row, or "
        "deleting a staff account will 500 on a foreign key violation. "
        "Add them there, then to EXPECTED_USER_DEPENDENTS."
    )
    # Also catch the reverse: a reference removed from the schema but
    # still being cleared, which is dead code worth noticing.
    assert not (EXPECTED_USER_DEPENDENTS - actual), (
        "EXPECTED_USER_DEPENDENTS lists a foreign key that no longer exists"
    )


def test_every_table_referencing_bookings_is_accounted_for():
    actual = _dependents_of("bookings")
    unhandled = actual - EXPECTED_BOOKING_DEPENDENTS
    assert not unhandled, (
        f"New foreign key(s) to bookings: {sorted(unhandled)}. "
        "customers.delete_customer must remove these before deleting the "
        "bookings, or deleting a customer will 500 on a foreign key "
        "violation. Add them there, then to EXPECTED_BOOKING_DEPENDENTS."
    )
    assert not (EXPECTED_BOOKING_DEPENDENTS - actual), (
        "EXPECTED_BOOKING_DEPENDENTS lists a foreign key that no longer exists"
    )


def test_the_delete_paths_actually_mention_every_dependent_table():
    """
    Cheap source check: each delete endpoint should at least reference
    every model it has to clean up. Catches the specific slip that
    caused both bugs — adding the table to the schema and to the list
    above, but forgetting the endpoint itself.
    """
    import inspect

    from app.api.v1.routes import customers, users

    user_src = inspect.getsource(users.delete_user)
    for table, column in EXPECTED_USER_DEPENDENTS:
        assert column in user_src, (
            f"users.delete_user never mentions {table}.{column} — deleting a "
            "staff account will fail on that foreign key"
        )

    customer_src = inspect.getsource(customers.delete_customer)
    for table, _column in EXPECTED_BOOKING_DEPENDENTS:
        model = table.rstrip("s").capitalize()
        assert model in customer_src, (
            f"customers.delete_customer never mentions {table} — deleting a "
            "customer will fail on that foreign key"
        )

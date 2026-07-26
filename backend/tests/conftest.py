"""
Environment the test suite needs before anything imports app.core.config.

Settings are validated at import time, so without these the whole suite
died during collection with three "Field required" errors and no test
ran at all — you had to know to export them by hand, or read the
traceback to find out which. pytest imports conftest before any test
module, which is early enough.

These are deliberately fake. Nothing in the unit suite opens a socket
or a database connection; the DSN only has to parse. Anything that
would genuinely need Postgres belongs in an integration test with a
real container behind it, not here.
"""

import os

# setdefault, not assignment: a caller who has already exported real
# values (running against a scratch database, say) keeps them.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-outside-tests")
# A syntactically valid Fernet key. app.core.encryption builds a cipher
# at import time, so a placeholder string would fail before collection.
os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "LZFOsRe9hVQhWnEz3ByLpKLKjqUuxbUiZfBRl5vCPZk="
)

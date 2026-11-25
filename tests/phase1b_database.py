"""Phase 1B regression database guard.

This module reads DATABASE_URL and either accepts the single allowlisted
target or raises Phase1BTargetRefusal. It does not import a driver, create
an engine, or open a socket.
"""

from __future__ import annotations

import os

from sqlalchemy.engine.url import make_url

REQUIRED_DATABASE = "kabaman_phase1b_regression_test"
ALLOWED_DATABASES = frozenset({REQUIRED_DATABASE})
REFUSED_DATABASES = frozenset(
    {
        "kabaman_os",
        "kabaman_phase1b_test",
        "kabaman_phase1c_test",
    }
)
REQUIRED_PORT = 5432
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOOPBACK_ADDRESSES = frozenset({"127.0.0.1", "::1"})


class Phase1BTargetRefusal(RuntimeError):
    """Refusal whose message contains neither a URL nor a password."""


def validated_target():
    """Return the parsed allowlisted URL, or refuse before any connection."""
    raw = os.environ.get("DATABASE_URL")
    if raw is None or not raw.strip():
        raise Phase1BTargetRefusal("DATABASE_URL is not set. Refusing to connect.")
    try:
        parsed = make_url(raw.strip())
    except Exception:
        raise Phase1BTargetRefusal(
            "DATABASE_URL could not be parsed. Refusing to connect."
        ) from None
    if parsed.query:
        raise Phase1BTargetRefusal(
            "Refusing to connect: query parameters are not allowed."
        )
    database = parsed.database
    host = parsed.host
    port = parsed.port
    if (
        database in REFUSED_DATABASES
        or database not in ALLOWED_DATABASES
        or host not in ALLOWED_HOSTS
        or port != REQUIRED_PORT
    ):
        raise Phase1BTargetRefusal(
            "Refusing to connect: database=%r host=%r port=%r."
            % (database, host, port)
        )
    return parsed

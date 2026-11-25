"""Password hashing, sessions, origin checks, and the in-process throttle.

The database guard lives here so every guarded connection can use it before
any other SQL. It refuses every database other than kabaman_phase3_orders_test.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

REQUIRED_DATABASE = "kabaman_phase3_orders_test"
REFUSED_DATABASES = frozenset({
    "kabaman_os",
    "kabaman_phase1b_test",
    "kabaman_phase1c_test",
    "kabaman_phase1b_regression_test",
    "kabaman_phase2c_auth_test",
})
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOOPBACK_ADDRESSES = frozenset({"127.0.0.1", "::1"})
REQUIRED_PORT = 5432

PBKDF2_ROUNDS = 200_000
CUSTOMER_PASSWORD_MIN = 8
BOOTSTRAP_PASSWORD_MIN = 12
PASSWORD_MAX = 128

COOKIE_NAME = "kabaman_session"
SESSION_DAYS = 14
SESSION_SECONDS = SESSION_DAYS * 24 * 60 * 60

THROTTLE_LIMIT = 5
THROTTLE_WINDOW_SECONDS = 15 * 60

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MESSAGES = {
    "invalid_request": "The request is invalid.",
    "invalid_email": "Enter a valid email.",
    "password_too_short": "Use a password of at least 8 characters.",
    "password_too_long": "Use a password of at most 128 characters.",
    "name_required": "Add your name.",
    "name_too_long": "Use a name of at most 100 characters.",
    "phone_too_long": "Use a phone number of at most 40 characters.",
    "email_taken": "An account with that email already exists.",
    "invalid_credentials": "Email or password is incorrect.",
    "unauthenticated": "Sign in to continue.",
    "forbidden": "You do not have permission to do that.",
    "origin_rejected": "The request origin is not allowed.",
    "client_address_required": "A direct client address is required.",
    "too_many_requests": "Too many attempts. Try again later.",
}

BOOTSTRAP_PASSWORD_TOO_SHORT = "Use a password of at least 12 characters."
BOOTSTRAP_PROMPT = "Enter the password at the hidden prompt."

logger = logging.getLogger("kabaman.auth")

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def validated_database_url() -> str:
    """Refuse a bad target before any socket is opened."""
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL is not set. Refusing to connect.")
    try:
        parsed = make_url(raw)
    except Exception:
        raise RuntimeError("DATABASE_URL could not be parsed. Refusing to connect.") from None
    if parsed.query:
        raise RuntimeError("Refusing to connect: query parameters are not allowed.")
    database = parsed.database
    host = parsed.host
    port = parsed.port
    if database in REFUSED_DATABASES or database != REQUIRED_DATABASE or host not in ALLOWED_HOSTS or port != REQUIRED_PORT:
        raise RuntimeError(
            "Refusing to connect: database=%r host=%r port=%r." % (database, host, port)
        )
    return raw


def _verify_connection(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT current_database(), host(inet_server_addr()), inet_server_port()")
        database, address, server_port = cursor.fetchone()
    finally:
        cursor.close()
    if database != REQUIRED_DATABASE or address not in LOOPBACK_ADDRESSES or int(server_port) != REQUIRED_PORT:
        dbapi_connection.close()
        raise RuntimeError(
            "Refusing to use this connection: database=%r address=%r port=%r."
            % (database, address, server_port)
        )


def get_guarded_engine() -> Engine:
    """Return an engine whose first SQL on every connection is the section 13 check."""
    global _engine, _session_factory
    url = validated_database_url()
    if _engine is None:
        engine = create_engine(url, echo=False, pool_pre_ping=False, poolclass=NullPool)
        event.listen(engine, "connect", _verify_connection)
        _engine = engine
        _session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return _engine


def dispose_guarded_engine() -> None:
    """Drop the cached engine object. Does not open a connection."""
    global _engine, _session_factory
    engine = _engine
    _engine = None
    _session_factory = None
    if engine is not None:
        engine.dispose()


@contextmanager
def session_scope() -> Iterator[Session]:
    get_guarded_engine()
    if _session_factory is None:
        raise RuntimeError("Refusing to connect.")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def error_response(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "error": MESSAGES[code]})


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    )
    return "pbkdf2_sha256$%d$%s$%s" % (PBKDF2_ROUNDS, salt, digest.hex())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = str(stored).split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(rounds),
        )
        return hmac.compare_digest(check.hex(), digest)
    except (TypeError, ValueError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current + timedelta(days=SESSION_DAYS)


def direct_client_ip(request: Request) -> str | None:
    client = request.client
    if client is None:
        return None
    host = getattr(client, "host", None)
    if host is None or str(host).strip() == "":
        return None
    return str(host)


def _effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return int(port)
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return -1


def origin_allowed(request: Request) -> bool:
    """Compare Origin with the request URL. Forwarded headers are ignored."""
    origin = request.headers.get("origin")
    if origin is None:
        return request.headers.get("sec-fetch-site") == "same-origin"
    if origin == "":
        return False
    if origin[0].isspace() or origin[-1].isspace():
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in origin):
        return False
    try:
        parts = urlsplit(origin)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return False
        if parts.username is not None or parts.password is not None:
            return False
        if parts.path or parts.query or parts.fragment:
            return False
        if parts.netloc.endswith(":"):
            return False
        port = parts.port
    except ValueError:
        return False
    url = request.url
    return (
        parts.scheme == url.scheme
        and parts.hostname.lower() == (url.hostname or "").lower()
        and _effective_port(parts.scheme, port) == _effective_port(url.scheme, url.port)
    )


def attach_session_cookie(response: JSONResponse, request: Request, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
        secure=request.url.scheme == "https",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    """Expire the host-only session cookie with the same attributes used to set it."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )


class AttemptThrottle:
    """Temporary in-process throttle.

    Not a production-grade rate limit. Counters belong to this process, are
    not shared across workers, reset when the process restarts, and are not a
    public-launch control. Public deployment still waits on auth_rate_limits.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self.failures: dict[str, list[float]] = {}
        self.blocked_until: dict[str, float] = {}

    def _live(self, ip: str, now: float) -> list[float]:
        return [stamp for stamp in self.failures.get(ip, []) if now - stamp < THROTTLE_WINDOW_SECONDS]

    def blocked(self, ip: str) -> bool:
        """Block only when five counted failures are already recorded.

        The fifth recorded failure is allowed. This method does not record.
        """
        now = self._clock()
        until = self.blocked_until.get(ip)
        if until is not None:
            if now < until:
                return True
            self.blocked_until.pop(ip, None)
            self.failures.pop(ip, None)
            return False
        stamps = self._live(ip, now)
        self.failures[ip] = stamps
        if len(stamps) >= THROTTLE_LIMIT:
            self.blocked_until[ip] = now + THROTTLE_WINDOW_SECONDS
            return True
        return False

    def record_failure(self, ip: str) -> None:
        now = self._clock()
        stamps = self._live(ip, now)
        stamps.append(now)
        self.failures[ip] = stamps

    def failure_count(self, ip: str) -> int:
        return len(self._live(ip, self._clock()))


_throttle = AttemptThrottle()


def get_throttle() -> AttemptThrottle:
    return _throttle


def reset_throttle(clock: Callable[[], float] | None = None) -> AttemptThrottle:
    global _throttle
    _throttle = AttemptThrottle(clock=clock)
    return _throttle

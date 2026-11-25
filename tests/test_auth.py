"""Phase 1C authentication tests. Every connection uses the section 13 guard.

The throttle under test is per process, is not shared, and is not a public-launch control.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from starlette.requests import Request

from api import security
from api.deps import require_customer, require_employee, require_permission
from api.main import app
from api.models import Customer, Employee, EmployeeRole, Role, Session
from api.security import (
    BOOTSTRAP_PASSWORD_TOO_SHORT,
    BOOTSTRAP_PROMPT,
    COOKIE_NAME,
    MESSAGES,
    hash_token,
)

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = {"origin": "http://testserver"}


def _revision():
    path = ROOT / "alembic" / "versions" / "0001_phase1.py"
    spec = importlib.util.spec_from_file_location("kabaman_revision_0001_phase1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Revision 0001_phase1 could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_revision(connection, direction: str) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    revision = _revision()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        if direction == "up":
            revision.upgrade()
        else:
            revision.downgrade()


def _prepare(connection) -> None:
    present = connection.execute(text("SELECT to_regclass('public.customers') IS NOT NULL")).scalar()
    if present:
        _run_revision(connection, "down")
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    _run_revision(connection, "up")
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    )
    connection.execute(text("DELETE FROM alembic_version"))
    connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001_phase1')"))


@pytest.fixture(scope="session")
def phase1c_schema():
    security.dispose_guarded_engine()
    engine = security.get_guarded_engine()
    with engine.connect() as connection:
        with connection.begin():
            _prepare(connection)
    yield
    with engine.connect() as connection:
        with connection.begin():
            _run_revision(connection, "down")
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    security.dispose_guarded_engine()


@pytest.fixture
def database(phase1c_schema):
    security.reset_throttle()
    with security.session_scope() as db:
        db.execute(delete(Session))
        db.execute(delete(EmployeeRole))
        db.execute(delete(Employee))
        db.execute(delete(Customer))
    yield


def _client(address: str = "203.0.113.10") -> TestClient:
    return TestClient(app, client=(address, 50000))


def _body(response) -> dict:
    if not response.content:
        return {}
    return response.json()


def _cookie(response) -> str | None:
    return response.cookies.get(COOKIE_NAME)


def _request(cookie: str | None = None, client=("203.0.113.10", 9)) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", ("%s=%s" % (COOKIE_NAME, cookie)).encode("utf-8")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/me",
        "raw_path": b"/api/me",
        "query_string": b"",
        "headers": headers,
        "client": client,
        "server": ("testserver", 80),
    }
    return Request(scope)


def _invoke(method: str, path: str, payload: dict | None, headers: dict, client, scheme: str = "http"):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    raw_headers = []
    merged = dict(headers)
    if payload is not None:
        merged.setdefault("content-type", "application/json")
    for key, value in merged.items():
        raw_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": scheme,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 443 if scheme == "https" else 80),
    }

    async def run():
        await app(scope, receive, send)

    asyncio.run(run())
    status = 500
    response_headers = []
    chunks = []
    for message in sent:
        if message["type"] == "http.response.start":
            status = message["status"]
            response_headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))
    return status, response_headers, b"".join(chunks)


def test_database_guard_refuses_before_a_socket(monkeypatch):
    security.dispose_guarded_engine()
    calls = {"engine": 0}

    def reject_engine(*_args, **_kwargs):
        calls["engine"] += 1
        raise AssertionError("engine created")

    monkeypatch.setattr(security, "create_engine", reject_engine)
    for database in ("kabaman_os", "kabaman_phase1b_test", "kabaman_phase1c_test_extra"):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:secret@127.0.0.1:5432/%s" % database,
        )
        with pytest.raises(RuntimeError, match="Refusing to connect"):
            security.get_guarded_engine()
        assert calls["engine"] == 0
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:secret@192.0.2.10:5432/kabaman_phase1c_test",
    )
    with pytest.raises(RuntimeError, match="Refusing to connect"):
        security.get_guarded_engine()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:secret@127.0.0.1:5433/kabaman_phase1c_test",
    )
    with pytest.raises(RuntimeError, match="Refusing to connect"):
        security.get_guarded_engine()
    for query in (
        "host=192.0.2.20",
        "hostaddr=192.0.2.21",
        "service=remote",
        "host=192.0.2.20&hostaddr=198.51.100.8",
    ):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:secret@127.0.0.1:5432/kabaman_phase1c_test?%s" % query,
        )
        with pytest.raises(RuntimeError, match="Refusing to connect"):
            security.get_guarded_engine()
        assert calls["engine"] == 0
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        security.get_guarded_engine()
    assert calls["engine"] == 0


def test_register_success_stores_hash_and_cookie(database):
    client = _client()
    password = "correct-horse"
    response = client.post(
        "/api/register",
        json={"email": " Ada@Example.com ", "password": password, "name": " Ada ", "phone": " 555 "},
        headers=ORIGIN,
    )
    assert response.status_code == 201
    body = _body(response)
    assert body["role"] == "customer"
    assert body["customer"]["email"] == "ada@example.com"
    assert body["customer"]["name"] == "Ada"
    assert body["customer"]["phone"] == "555"
    assert "password_hash" not in response.text
    assert "token_hash" not in response.text
    cookie = _cookie(response)
    assert cookie
    assert password not in response.text
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "samesite=lax" in header.lower()
    assert "Path=/" in header or "path=/" in header.lower()
    assert "Max-Age=1209600" in header or "max-age=1209600" in header.lower()
    parts = [part.strip().lower() for part in header.split(";")]
    assert "secure" not in parts
    with security.session_scope() as db:
        customer = db.scalar(select(Customer).where(Customer.email == "ada@example.com"))
        assert customer is not None
        stored = customer.password_hash
        assert stored.startswith("pbkdf2_sha256$200000$")
        algo, rounds, salt, digest = stored.split("$")
        assert algo == "pbkdf2_sha256"
        assert rounds == "200000"
        assert len(salt) == 32
        assert len(digest) == 64
        assert security.verify_password(password, stored)
        assert not security.verify_password("other-password", stored)
        row = db.scalar(select(Session).where(Session.customer_id == customer.id))
        assert row is not None
        assert row.principal_type == "customer"
        assert row.employee_id is None
        assert cookie != row.token_hash
        assert hash_token(cookie) == row.token_hash
        assert cookie not in stored


def test_register_validation_order(database):
    client = _client()
    cases = [
        ({"email": "not-an-email", "password": "short", "name": ""}, "invalid_email"),
        ({"email": "ada@example.com", "password": "short", "name": "Ada"}, "password_too_short"),
        ({"email": "ada@example.com", "password": "p" * 129, "name": "Ada"}, "password_too_long"),
        ({"email": "ada@example.com", "password": "long-enough", "name": "  "}, "name_required"),
        (
            {"email": "ada@example.com", "password": "long-enough", "name": "n" * 101},
            "name_too_long",
        ),
        (
            {"email": "ada@example.com", "password": "long-enough", "name": "Ada", "phone": "p" * 41},
            "phone_too_long",
        ),
    ]
    for index, (payload, code) in enumerate(cases):
        response = _client("203.0.113.%d" % (21 + index)).post("/api/register", json=payload, headers=ORIGIN)
        assert response.status_code == 400
        assert _body(response) == {"code": code, "error": MESSAGES[code]}
    both = client.post(
        "/api/register",
        json={"email": "bad", "password": "short", "name": ""},
        headers=ORIGIN,
    )
    assert _body(both)["code"] == "invalid_email"
    boundary = client.post(
        "/api/register",
        json={"email": "boundary@example.com", "password": "long-enough", "name": "n" * 100, "phone": "p" * 40},
        headers=ORIGIN,
    )
    assert boundary.status_code == 201
    with security.session_scope() as db:
        assert db.scalar(select(Customer).where(Customer.email == "ada@example.com")) is None
        saved = db.scalar(select(Customer).where(Customer.email == "boundary@example.com"))
        assert saved is not None
        assert saved.name == "n" * 100
        assert saved.phone == "p" * 40


def test_duplicate_email_keeps_the_stored_hash(database):
    client = _client()
    first = client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "first-password", "name": "Ada"},
        headers=ORIGIN,
    )
    assert first.status_code == 201
    with security.session_scope() as db:
        before = db.scalar(select(Customer.password_hash).where(Customer.email == "ada@example.com"))
    second = client.post(
        "/api/register",
        json={"email": "Ada@Example.com", "password": "second-password", "name": "Other"},
        headers=ORIGIN,
    )
    assert second.status_code == 409
    assert _body(second)["code"] == "email_taken"
    with security.session_scope() as db:
        after = db.scalar(select(Customer.password_hash).where(Customer.email == "ada@example.com"))
        assert after == before
        assert not security.verify_password("second-password", after)


def test_customer_login_revokes_the_older_session(database):
    client = _client()
    client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers=ORIGIN,
    )
    first = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
        headers=ORIGIN,
    )
    assert first.status_code == 200
    older = _cookie(first)
    second = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
        headers=ORIGIN,
    )
    assert second.status_code == 200
    newer = _cookie(second)
    assert older and newer and older != newer
    stale = _client()
    stale.cookies.set(COOKIE_NAME, older)
    assert _body(stale.get("/api/me")) == {"role": ""}
    current = _client()
    current.cookies.set(COOKIE_NAME, newer)
    assert _body(current.get("/api/me"))["role"] == "customer"


def test_bad_customer_login_and_overlong_password_skip_pbkdf2(database, monkeypatch):
    client = _client()
    client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers=ORIGIN,
    )
    bad = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "wrong-password"},
        headers=ORIGIN,
    )
    assert bad.status_code == 401
    assert _body(bad) == {"code": "invalid_credentials", "error": MESSAGES["invalid_credentials"]}
    calls = {"n": 0}
    real = security.hashlib.pbkdf2_hmac

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(security.hashlib, "pbkdf2_hmac", wrapped)
    over = client.post(
        "/api/login",
        json={"email": "missing@example.com", "password": "x" * 129},
        headers=ORIGIN,
    )
    assert over.status_code == 401
    assert _body(over)["code"] == "invalid_credentials"
    assert calls["n"] == 0


def test_logout_revokes_only_the_current_session(database):
    client = _client()
    registered = client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers=ORIGIN,
    )
    cookie = _cookie(registered)
    logged_out = client.post("/api/logout", headers=ORIGIN)
    assert logged_out.status_code == 200
    assert logged_out.content == b""
    assert _body(client.get("/api/me")) == {"role": ""}
    with security.session_scope() as db:
        row = db.scalar(select(Session).where(Session.token_hash == hash_token(cookie)))
        assert row is not None
        assert row.revoked_at is not None
    missing = _client()
    assert missing.post("/api/logout", headers=ORIGIN).status_code == 204


class _LogoutScope:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self.database

    def __exit__(self, exc_type, exc, tb):
        return False


class _LogoutRow:
    def __init__(self, expires_at, revoked_at=None):
        self.expires_at = expires_at
        self.revoked_at = revoked_at


class _LogoutDatabase:
    def __init__(self, row):
        self.row = row
        self.lookups = 0

    def scalar(self, _statement):
        self.lookups += 1
        return self.row


def _block_real_database(monkeypatch):
    def reject(*_args, **_kwargs):
        raise AssertionError("database accessed")

    monkeypatch.setattr(security, "get_guarded_engine", reject)
    monkeypatch.setattr(security, "create_engine", reject)


def _install_logout_database(monkeypatch, row):
    _block_real_database(monkeypatch)
    database = _LogoutDatabase(row)
    monkeypatch.setattr(
        "api.routes.auth.session_scope",
        lambda: _LogoutScope(database),
    )
    return database


def _logout_call(cookie: str | None, scheme: str = "http", origin: str | None = "http://testserver"):
    headers = {}
    if origin is not None:
        headers["origin"] = origin
    if cookie is not None:
        headers["cookie"] = "%s=%s" % (COOKIE_NAME, cookie)
    if scheme == "https" and origin == "http://testserver":
        headers["origin"] = "https://testserver"
    return _invoke("POST", "/api/logout", None, headers, ("203.0.113.90", 9), scheme=scheme)


def _set_cookie_header(headers) -> str:
    values = [value.decode("latin-1") for key, value in headers if key == b"set-cookie"]
    assert len(values) == 1
    return values[0]


def _assert_clearing_cookie(header: str, secure: bool) -> None:
    assert header.startswith("%s=" % COOKIE_NAME)
    lowered = header.lower()
    assert "max-age=0" in lowered
    assert "path=/" in lowered
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    parts = [part.strip().lower() for part in header.split(";")]
    assert all(not part.startswith("domain") for part in parts)
    assert ("secure" in parts) is secure


def test_logout_success_revokes_session_and_clears_cookie(monkeypatch):
    row = _LogoutRow(datetime.now(timezone.utc) + timedelta(days=1))
    database = _install_logout_database(monkeypatch, row)
    status, headers, body = _logout_call("phase2c-logout-token")
    assert status == 200
    assert body == b""
    assert database.lookups == 1
    assert row.revoked_at is not None
    _assert_clearing_cookie(_set_cookie_header(headers), secure=False)
    assert "phase2c-logout-token" not in _set_cookie_header(headers)


def test_logout_clearing_cookie_is_secure_on_https(monkeypatch):
    row = _LogoutRow(datetime.now(timezone.utc) + timedelta(days=1))
    _install_logout_database(monkeypatch, row)
    status, headers, body = _logout_call("phase2c-logout-token", scheme="https")
    assert status == 200
    assert body == b""
    _assert_clearing_cookie(_set_cookie_header(headers), secure=True)


def test_logout_unusable_sessions_do_not_clear_or_revoke(monkeypatch):
    _block_real_database(monkeypatch)
    missing_status, missing_headers, missing_body = _logout_call(None)
    assert missing_status == 204
    assert missing_body == b""
    assert not any(key == b"set-cookie" for key, _value in missing_headers)

    unknown = _install_logout_database(monkeypatch, None)
    unknown_status, unknown_headers, unknown_body = _logout_call("unknown-token")
    assert unknown_status == 204
    assert unknown_body == b""
    assert unknown.lookups == 1
    assert not any(key == b"set-cookie" for key, _value in unknown_headers)

    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = _LogoutRow(expired_at)
    _install_logout_database(monkeypatch, expired)
    expired_status, expired_headers, expired_body = _logout_call("expired-token")
    assert expired_status == 204
    assert expired_body == b""
    assert expired.revoked_at is None
    assert not any(key == b"set-cookie" for key, _value in expired_headers)

    already = datetime.now(timezone.utc) - timedelta(minutes=5)
    revoked = _LogoutRow(datetime.now(timezone.utc) + timedelta(days=1), revoked_at=already)
    _install_logout_database(monkeypatch, revoked)
    revoked_status, revoked_headers, revoked_body = _logout_call("revoked-token")
    assert revoked_status == 204
    assert revoked_body == b""
    assert revoked.revoked_at == already
    assert not any(key == b"set-cookie" for key, _value in revoked_headers)


def test_logout_rejects_invalid_origin_without_clearing(monkeypatch):
    def reject_scope():
        raise AssertionError("database accessed")

    _block_real_database(monkeypatch)
    monkeypatch.setattr("api.routes.auth.session_scope", reject_scope)
    status, headers, body = _logout_call(
        "phase2c-logout-token",
        origin="http://evil.example",
    )
    assert status == 403
    assert json.loads(body) == {"code": "origin_rejected", "error": MESSAGES["origin_rejected"]}
    assert not any(key == b"set-cookie" for key, _value in headers)


def test_expired_revoked_and_copied_hash_do_not_authenticate(database):
    client = _client()
    response = client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers=ORIGIN,
    )
    cookie = _cookie(response)
    with security.session_scope() as db:
        row = db.scalar(select(Session))
        copied = row.token_hash
        db.execute(
            update(Session)
            .where(Session.id == row.id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    expired = _client()
    expired.cookies.set(COOKIE_NAME, cookie)
    assert _body(expired.get("/api/me")) == {"role": ""}
    with security.session_scope() as db:
        db.execute(
            update(Session).values(
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                revoked_at=datetime.now(timezone.utc),
            )
        )
    revoked = _client()
    revoked.cookies.set(COOKIE_NAME, cookie)
    assert _body(revoked.get("/api/me")) == {"role": ""}
    presented = _client()
    presented.cookies.set(COOKIE_NAME, copied)
    assert _body(presented.get("/api/me")) == {"role": ""}


def test_session_swap_and_permissions(database):
    from api.bootstrap_employee import main

    assert main(["ada@example.com", "Ada"], password_reader=lambda: "employee-password-1") == 0
    client = _client()
    registered = client.post(
        "/api/register",
        json={"email": "buyer@example.com", "password": "correct-horse", "name": "Buyer"},
        headers=ORIGIN,
    )
    customer_cookie = _cookie(registered)
    employee = client.post(
        "/api/employee/login",
        json={"email": "ada@example.com", "password": "employee-password-1"},
        headers=ORIGIN,
    )
    assert employee.status_code == 200
    assert employee.json()["role"] == "employee"
    assert "customer" not in employee.json()
    assert "password_hash" not in employee.text
    employee_cookie = _cookie(employee)
    with security.session_scope() as db:
        denied = require_employee(db, _request(customer_cookie))
        assert denied.status == 403
        assert denied.code == "forbidden"
        denied_customer = require_customer(db, _request(employee_cookie))
        assert denied_customer.status == 403
        assert denied_customer.code == "forbidden"
        allowed = require_permission(db, _request(employee_cookie), "orders.delete")
        assert allowed.employee.email == "ada@example.com"
        editor = Employee(
            email="editor@example.com",
            name="Editor",
            password_hash=security.hash_password("editor-password-1"),
            is_active=True,
        )
        db.add(editor)
        db.flush()
        site_editor = db.scalar(select(Role).where(Role.name == "site_editor"))
        db.add(EmployeeRole(employee_id=editor.id, role_id=site_editor.id))
        token = security.new_session_token()
        db.add(
            Session(
                token_hash=hash_token(token),
                principal_type="employee",
                customer_id=None,
                employee_id=editor.id,
                expires_at=security.session_expiry(),
            )
        )
        db.flush()
        missing = require_permission(db, _request(token), "orders.delete")
        assert missing.status == 403
        assert missing.code == "forbidden"


def test_inactive_login_and_deactivated_session_match_bad_credentials(database):
    from api.bootstrap_employee import main

    assert main(["ada@example.com", "Ada"], password_reader=lambda: "employee-password-1") == 0
    client = _client()
    signed = client.post(
        "/api/employee/login",
        json={"email": "ada@example.com", "password": "employee-password-1"},
        headers=ORIGIN,
    )
    cookie = _cookie(signed)
    with security.session_scope() as db:
        db.execute(update(Employee).values(is_active=False))
    inactive = client.post(
        "/api/employee/login",
        json={"email": "ada@example.com", "password": "employee-password-1"},
        headers=ORIGIN,
    )
    wrong = client.post(
        "/api/employee/login",
        json={"email": "ada@example.com", "password": "not-the-password"},
        headers=ORIGIN,
    )
    assert inactive.status_code == 401
    assert inactive.json() == wrong.json()
    assert inactive.json()["code"] == "invalid_credentials"
    holder = _client()
    holder.cookies.set(COOKIE_NAME, cookie)
    later = holder.get("/api/me")
    assert later.status_code == 401
    assert later.json()["code"] == "invalid_credentials"


def test_admin_login_is_absent_and_me_returns_the_current_principal(database):
    client = _client()
    assert _body(client.get("/api/me")) == {"role": ""}
    missing = client.post("/api/admin/login", json={"email": "a@b.co", "password": "correct-horse"})
    assert missing.status_code == 404
    assert "code" not in _body(missing)
    registered = client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers=ORIGIN,
    )
    assert client.get("/api/me").json()["role"] == "customer"
    assert "password_hash" not in registered.text
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True}


def test_origin_rules_ignore_forwarded_headers(database):
    client = _client()
    payload = {"email": "ada@example.com", "password": "correct-horse", "name": "Ada"}
    rejected = client.post(
        "/api/register",
        json=payload,
        headers={"origin": "http://evil.example", "x-forwarded-host": "evil.example"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "origin_rejected"
    same = client.post("/api/register", json=payload, headers={"sec-fetch-site": "same-origin"})
    assert same.status_code == 201
    status, headers, body = _invoke(
        "POST",
        "/api/login",
        {"email": "ada@example.com", "password": "correct-horse"},
        {"origin": "https://testserver"},
        ("203.0.113.20", 9),
        scheme="https",
    )
    assert status == 200
    raw = b"".join(value for key, value in headers if key == b"set-cookie")
    assert b"Secure" in raw


def test_origin_rejects_userinfo_path_query_fragment_port_and_scheme():
    security.reset_throttle()
    client = _client("203.0.113.70")
    payload = {"email": "ada@example.com", "password": "correct-horse", "name": "Ada"}
    rejected = (
        "http://user:secret@testserver",
        "http://user@testserver",
        "http://testserver/path",
        "http://testserver/",
        "http://testserver?next=/",
        "http://testserver#fragment",
        "http://testserver:abc",
        "http://testserver:99999",
        "ftp://testserver",
        "null",
    )
    for origin in rejected:
        response = client.post("/api/register", json=payload, headers={"origin": origin})
        assert response.status_code == 403
        assert response.json() == {"code": "origin_rejected", "error": MESSAGES["origin_rejected"]}
    assert security.get_throttle().failure_count("203.0.113.70") == 0


def test_origin_rejects_whitespace_controls_and_empty_port():
    security.reset_throttle()
    payload = {"email": "ada@example.com", "password": "correct-horse", "name": "Ada"}
    rejected = (
        " http://testserver",
        "http://testserver ",
        "http://testserver\t",
        "http://te\rstserver",
        "http://testserver\n",
        "http://test\x01server",
        "http://test\x7fserver",
        "http://testserver:",
    )
    for origin in rejected:
        status, _headers, body = _invoke(
            "POST",
            "/api/register",
            payload,
            {"origin": origin},
            ("203.0.113.72", 9),
        )
        assert status == 403
        assert json.loads(body) == {"code": "origin_rejected", "error": MESSAGES["origin_rejected"]}
    assert security.get_throttle().failure_count("203.0.113.72") == 0


def test_origin_rejects_userinfo_and_empty_header():
    security.reset_throttle()
    payload = {"email": "ada@example.com", "password": "correct-horse", "name": "Ada"}
    for origin in ("http://user@testserver", "http://user:secret@testserver"):
        status, _headers, body = _invoke(
            "POST",
            "/api/register",
            payload,
            {"origin": origin},
            ("203.0.113.73", 9),
        )
        assert status == 403
        assert json.loads(body) == {"code": "origin_rejected", "error": MESSAGES["origin_rejected"]}
    status, _headers, body = _invoke(
        "POST",
        "/api/register",
        payload,
        {"origin": "", "sec-fetch-site": "same-origin"},
        ("203.0.113.73", 9),
    )
    assert status == 403
    assert json.loads(body) == {"code": "origin_rejected", "error": MESSAGES["origin_rejected"]}
    assert security.get_throttle().failure_count("203.0.113.73") == 0


def test_absent_origin_uses_same_origin_fallback(database):
    client = _client()
    response = client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers={"sec-fetch-site": "same-origin"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "customer"


def test_origin_accepts_serialized_same_origin(database):
    client = _client()
    payload = {"email": "ada@example.com", "password": "correct-horse", "name": "Ada"}
    plain = client.post("/api/register", json=payload, headers={"origin": "http://testserver"})
    assert plain.status_code == 201
    explicit_port = client.post(
        "/api/register",
        json={"email": "port@example.com", "password": "correct-horse", "name": "Ada"},
        headers={"origin": "http://testserver:80"},
    )
    assert explicit_port.status_code == 201
    mixed_case = client.post(
        "/api/register",
        json={"email": "case@example.com", "password": "correct-horse", "name": "Ada"},
        headers={"origin": "http://TestServer"},
    )
    assert mixed_case.status_code == 201
    status, _headers, body = _invoke(
        "POST",
        "/api/login",
        {"email": "ada@example.com", "password": "correct-horse"},
        {"origin": "https://testserver"},
        ("203.0.113.71", 9),
        scheme="https",
    )
    assert status == 200
    assert json.loads(body)["role"] == "customer"


def test_invalid_utf8_counts_only_for_registration():
    security.reset_throttle()
    client = _client("203.0.113.80")
    raw = b"\xff"
    headers = {**ORIGIN, "content-type": "application/json"}
    register = client.post("/api/register", content=raw, headers=headers)
    assert register.status_code == 400
    assert register.json() == {"code": "invalid_request", "error": MESSAGES["invalid_request"]}
    assert security.get_throttle().failure_count("203.0.113.80") == 1
    login = client.post("/api/login", content=raw, headers=headers)
    assert login.status_code == 400
    assert login.json()["code"] == "invalid_request"
    employee = client.post("/api/employee/login", content=raw, headers=headers)
    assert employee.status_code == 400
    assert employee.json()["code"] == "invalid_request"
    assert security.get_throttle().failure_count("203.0.113.80") == 1


def test_bootstrap_refusals_and_role_assignment(database, capsys, monkeypatch):
    from api.bootstrap_employee import main

    assert main(["ada@example.com", "Ada"]) == 1
    assert BOOTSTRAP_PROMPT in capsys.readouterr().err
    assert main(["ada@example.com", "Ada"], password_reader=lambda: "short-pass") == 1
    assert BOOTSTRAP_PASSWORD_TOO_SHORT in capsys.readouterr().err
    assert main(["ada@example.com", "Ada"], password_reader=lambda: "x" * 129) == 1
    assert MESSAGES["password_too_long"] in capsys.readouterr().err
    secret = "from-the-flag"
    assert main(["-p", secret, "ada@example.com", "Ada"], password_reader=lambda: "employee-password-1") == 1
    captured = capsys.readouterr().err
    assert BOOTSTRAP_PROMPT in captured
    assert secret not in captured
    monkeypatch.setenv("KABAMAN_EMPLOYEE_PASSWORD", "environment-secret")
    assert main(["ada@example.com", "Ada"], password_reader=lambda: "employee-password-1") == 1
    assert "environment-secret" not in capsys.readouterr().err
    monkeypatch.delenv("KABAMAN_EMPLOYEE_PASSWORD", raising=False)
    assert main(["ada@example.com", "Ada Lovelace"], password_reader=lambda: "employee-password-1") == 0
    created = capsys.readouterr().err
    assert "employee-password-1" not in created
    with security.session_scope() as db:
        employee = db.scalar(select(Employee).where(Employee.email == "ada@example.com"))
        assert employee is not None
        assert security.verify_password("employee-password-1", employee.password_hash)
        names = set(
            db.scalars(
                select(Role.name)
                .join(EmployeeRole, EmployeeRole.role_id == Role.id)
                .where(EmployeeRole.employee_id == employee.id)
            )
        )
        assert names == {"order_reviewer", "site_editor", "operator"}


def test_throttle_allows_five_counted_failures_and_blocks_the_sixth(database):
    now = {"t": 1_000_000.0}
    security.reset_throttle(clock=lambda: now["t"])
    client = _client("203.0.113.40")
    client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "correct-horse", "name": "Ada"},
        headers=ORIGIN,
    )
    for _ in range(5):
        response = client.post(
            "/api/login",
            json={"email": "ada@example.com", "password": "wrong-password"},
            headers=ORIGIN,
        )
        assert response.status_code == 401
    assert security.get_throttle().failure_count("203.0.113.40") == 5
    blocked = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
        headers=ORIGIN,
    )
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "too_many_requests", "error": MESSAGES["too_many_requests"]}
    assert "retry" not in blocked.text.lower()
    assert security.get_throttle().failure_count("203.0.113.40") == 5
    assert _body(client.get("/api/me"))["role"] == "customer"
    now["t"] += 20
    again = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
        headers=ORIGIN,
    )
    assert again.status_code == 429
    assert security.get_throttle().failure_count("203.0.113.40") == 5
    now["t"] = 1_000_000.0 + 10 + 15 * 60
    opened = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "wrong-password"},
        headers=ORIGIN,
    )
    assert opened.status_code == 401
    assert security.get_throttle().failure_count("203.0.113.40") == 1


def test_throttle_ignores_origin_address_and_login_syntax_errors(database):
    now = {"t": 2_000_000.0}
    security.reset_throttle(clock=lambda: now["t"])
    client = _client("203.0.113.50")
    origin = client.post(
        "/api/login",
        json={"email": "ada@example.com", "password": "wrong-password"},
        headers={"origin": "https://evil.example"},
    )
    assert origin.status_code == 403
    status, _headers, body = _invoke(
        "POST",
        "/api/login",
        {"email": "ada@example.com", "password": "wrong-password"},
        {"origin": "http://testserver"},
        None,
    )
    assert status == 403
    assert json.loads(body)["code"] == "client_address_required"
    for _ in range(6):
        syntax = client.post("/api/login", json={"email": "ada@example.com", "extra": "no"}, headers=ORIGIN)
        assert syntax.status_code == 400
        assert syntax.json()["code"] == "invalid_request"
    assert security.get_throttle().failure_count("203.0.113.50") == 0
    for index in range(5):
        counted = client.post(
            "/api/register",
            json={"email": "not-email", "password": "long-enough", "name": "Ada"},
            headers=ORIGIN,
        )
        assert counted.status_code == 400
        assert index < 5
    assert security.get_throttle().failure_count("203.0.113.50") == 5
    sixth = client.post(
        "/api/register",
        json={"email": "ada@example.com", "password": "long-enough", "name": "Ada"},
        headers=ORIGIN,
    )
    assert sixth.status_code == 429


def test_logs_omit_secrets(database, caplog, capsys):
    from api.bootstrap_employee import main

    password = "correct-horse"
    with caplog.at_level(logging.INFO, logger="kabaman.auth"):
        client = _client()
        response = client.post(
            "/api/register",
            json={"email": "ada@example.com", "password": password, "name": "Ada"},
            headers=ORIGIN,
        )
        cookie = _cookie(response)
        client.post(
            "/api/login",
            json={"email": "ada@example.com", "password": "wrong-password"},
            headers=ORIGIN,
        )
        client.post("/api/logout", headers=ORIGIN)
        main(["boss@example.com", "Boss"], password_reader=lambda: "no")
    text = caplog.text
    assert "register" in text
    assert "customer_login_failed" in text
    assert "logout" in text
    assert "bootstrap_password_rejected" in text
    assert password not in text
    assert "wrong-password" not in text
    assert cookie not in text
    with security.session_scope() as db:
        stored = db.scalar(select(Customer.password_hash))
    assert stored not in text
    assert password not in capsys.readouterr().err


def test_schema_is_unchanged_and_protected_files_have_no_diff(database):
    with security.session_scope() as db:
        version = db.scalar(text("SELECT version_num FROM alembic_version"))
        rate_limits = db.scalar(text("SELECT to_regclass('public.auth_rate_limits')"))
    assert version == "0001_phase1"
    assert rate_limits is None
    revisions = sorted(path.name for path in (ROOT / "alembic" / "versions").glob("*.py"))
    assert revisions == ["0001_phase1.py"]
    import subprocess

    protected = [
        "api/models.py",
        "alembic/versions/0001_phase1.py",
        "tests/test_phase1b.py",
        "tests/conftest.py",
        "server.py",
    ]
    result = subprocess.run(
        ["git", "diff", "--exit-code", "--", *protected],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == ""

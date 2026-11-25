"""Mocked Phase 3 database-guard checks. No PostgreSQL connection is opened."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy

from api import security

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "alembic" / "env.py"
TARGET = "kabaman_phase3_orders_test"
REFUSED = (
    "kabaman_os",
    "kabaman_phase1b_test",
    "kabaman_phase1c_test",
    "kabaman_phase1b_regression_test",
    "kabaman_phase2c_auth_test",
)


def _url(database: str, host: str = "127.0.0.1", port: int | None = 5432, query: str = "") -> str:
    host_part = "[::1]" if host == "::1" else host
    port_part = "" if port is None else ":%s" % port
    query_part = "?%s" % query if query else ""
    return "postgresql+psycopg://phase3-mock:mock-not-a-secret@%s%s/%s%s" % (
        host_part,
        port_part,
        database,
        query_part,
    )


def _reject_engine(monkeypatch):
    calls = {"n": 0}

    def reject(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("engine created")

    monkeypatch.setattr(security, "create_engine", reject)
    return calls


def test_phase3_database_is_accepted_before_an_engine(monkeypatch):
    security.dispose_guarded_engine()
    calls = _reject_engine(monkeypatch)
    raw = _url(TARGET)
    monkeypatch.setenv("DATABASE_URL", raw)
    assert security.validated_database_url() == raw
    assert calls["n"] == 0
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_hosts_are_accepted_for_the_phase3_database(monkeypatch, host):
    calls = _reject_engine(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", _url(TARGET, host=host))
    security.validated_database_url()
    assert calls["n"] == 0
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.mark.parametrize("database", REFUSED + ("postgres", "kabaman_other"))
def test_other_database_names_are_refused_before_an_engine(monkeypatch, database):
    security.dispose_guarded_engine()
    calls = _reject_engine(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", _url(database))
    with pytest.raises(RuntimeError, match="Refusing to connect"):
        security.get_guarded_engine()
    assert calls["n"] == 0
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_wrong_host_port_query_and_blank_url_are_refused(monkeypatch):
    security.dispose_guarded_engine()
    calls = _reject_engine(monkeypatch)
    samples = (
        _url(TARGET, host="192.0.2.10"),
        _url(TARGET, port=5433),
        _url(TARGET, port=None),
        _url(TARGET, query="sslmode=disable"),
        "",
        "   ",
        "postgresql://127.0.0.1:nope/db",
    )
    for raw in samples:
        if raw.strip():
            monkeypatch.setenv("DATABASE_URL", raw)
        else:
            monkeypatch.setenv("DATABASE_URL", raw)
        with pytest.raises(RuntimeError, match="Refusing to connect|not set|could not be parsed"):
            security.get_guarded_engine()
        assert calls["n"] == 0
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        security.get_guarded_engine()
    assert calls["n"] == 0


def test_guarded_engine_registers_verification_before_connect(monkeypatch):
    security.dispose_guarded_engine()
    order = []

    def fake_create_engine(*_args, **_kwargs):
        order.append("create")

        class Engine:
            def connect(self):
                order.append("connect")
                raise AssertionError("connection opened")

            def dispose(self):
                order.append("dispose")

        return Engine()

    def fake_listen(_target, identifier, fn):
        order.append("listen")
        assert identifier == "connect"
        assert fn is security._verify_connection

    monkeypatch.setattr(security, "create_engine", fake_create_engine)
    monkeypatch.setattr(security.event, "listen", fake_listen)
    monkeypatch.setenv("DATABASE_URL", _url(TARGET))
    security.get_guarded_engine()
    assert order == ["create", "listen"]
    security.dispose_guarded_engine()
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_post_connection_check_accepts_only_the_phase3_loopback(monkeypatch):
    class Cursor:
        def __init__(self, row):
            self.row = row

        def execute(self, sql):
            assert "current_database()" in sql

        def fetchone(self):
            return self.row

        def close(self):
            return None

    class Connection:
        def __init__(self, row):
            self.row = row
            self.closed = False

        def cursor(self):
            return Cursor(self.row)

        def close(self):
            self.closed = True

    security._verify_connection(Connection((TARGET, "127.0.0.1", 5432)), None)
    security._verify_connection(Connection((TARGET, "::1", 5432)), None)
    refused = Connection(("kabaman_phase2c_auth_test", "127.0.0.1", 5432))
    with pytest.raises(RuntimeError, match="Refusing to use this connection"):
        security._verify_connection(refused, None)
    assert refused.closed is True
    remote = Connection((TARGET, "192.0.2.10", 5432))
    with pytest.raises(RuntimeError, match="Refusing to use this connection"):
        security._verify_connection(remote, None)
    assert remote.closed is True
    named_host = Connection((TARGET, "localhost", 5432))
    with pytest.raises(RuntimeError, match="Refusing to use this connection"):
        security._verify_connection(named_host, None)
    assert named_host.closed is True
    other_port = Connection((TARGET, "127.0.0.1", 5433))
    with pytest.raises(RuntimeError, match="Refusing to use this connection"):
        security._verify_connection(other_port, None)
    assert other_port.closed is True


def test_alembic_offline_mode_refuses_before_an_engine(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _url(TARGET))
    created = {"n": 0}

    def reject(*_args, **_kwargs):
        created["n"] += 1
        raise AssertionError("engine created")

    original_create_engine = sqlalchemy.create_engine
    sqlalchemy.create_engine = reject

    class Config:
        config_file_name = None

    import alembic.context as context

    context.config = Config()
    context.is_offline_mode = lambda: True
    context.configure_calls = []
    context.configure = lambda **_kwargs: context.configure_calls.append(True)

    spec = importlib.util.spec_from_file_location("alembic_env_phase3_" + uuid.uuid4().hex, ENV_PATH)
    module = importlib.util.module_from_spec(spec)
    try:
        with pytest.raises(RuntimeError, match="Offline Alembic migrations are refused"):
            spec.loader.exec_module(module)
        assert created["n"] == 0
        assert context.configure_calls == []
    finally:
        sqlalchemy.create_engine = original_create_engine
        monkeypatch.delenv("DATABASE_URL", raising=False)


def test_alembic_source_validates_before_connect():
    source = ENV_PATH.read_text(encoding="utf-8")
    online = source.split("def run_migrations_online", 1)[1]
    assert "validated_database_url()" in online
    assert online.index("validated_database_url()") < online.index("create_engine(")
    assert online.index("event.listen(") < online.index(".connect()")
    assert "_verify_connection" in online
    offline = source.split("def run_migrations_offline", 1)[1].split("def run_migrations_online", 1)[0]
    assert "raise RuntimeError" in offline
    assert "context.configure" not in offline
    assert "os.environ" not in source

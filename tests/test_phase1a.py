"""Phase 1A: the process imports, health is the only route, and secrets are not logged."""

import api.db as db
from api.config import load_settings
from api.main import app


SECRET = "phase1a-secret-token"


def test_app_imports():
    assert app is not None


def test_health_is_the_only_route():
    exposed = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods:
            exposed.append((tuple(sorted(methods)), route.path))
    assert exposed == [(("GET",), "/api/health")]


def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert list(response.json()) == ["ok"]


def test_docs_are_not_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/admin.html").status_code == 404


def test_settings_do_not_reveal_the_database_password(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://kabaman:%s@db.example:5432/kabaman" % SECRET,
    )
    monkeypatch.setenv("KABAMAN_BIND", "0.0.0.0")
    settings = load_settings()
    rendered = "%s %s %s" % (settings, repr(settings), settings.public_database_label())
    assert SECRET not in rendered
    assert "kabaman:" not in rendered
    assert settings.public_database_label() == "postgresql+psycopg://db.example/kabaman"
    assert settings.host == "127.0.0.1"


def test_engine_is_not_opened_on_import_or_lookup(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://kabaman:%s@127.0.0.1:1/kabaman" % SECRET,
    )
    db.dispose_engine()
    engine = db.get_engine()
    assert engine.pool.checkedout() == 0
    assert SECRET not in db.describe_engine()
    db.dispose_engine()


def test_missing_database_url_does_not_echo_the_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.dispose_engine()
    try:
        db.get_engine()
    except RuntimeError as exc:
        assert "DATABASE_URL is not set" in str(exc)
        assert SECRET not in str(exc)
    else:
        raise AssertionError("get_engine should fail when DATABASE_URL is unset")
    finally:
        db.dispose_engine()

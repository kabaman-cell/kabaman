"""SQLAlchemy connection layer. Creating the engine does not open a connection."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import load_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return a lazy engine. The first connection happens only when a caller asks for one."""
    global _engine, _session_factory
    if _engine is None:
        settings = load_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(settings.database_url, echo=False, pool_pre_ping=False)
        _session_factory = None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def dispose_engine() -> None:
    """Drop the cached engine object. Does not connect."""
    global _engine, _session_factory
    engine = _engine
    _engine = None
    _session_factory = None
    if engine is not None:
        engine.dispose()


def describe_engine() -> str:
    return load_settings().public_database_label()

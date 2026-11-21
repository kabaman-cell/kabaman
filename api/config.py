"""Environment configuration. Secrets stay in the environment and are not logged."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.engine.url import make_url

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 4174


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    host: str
    port: int

    def public_database_label(self) -> str:
        """Host and database name only. No user and no password."""
        if not self.database_url:
            return "unset"
        try:
            url = make_url(self.database_url)
        except Exception:
            return "invalid"
        host = url.host or "local"
        database = url.database or ""
        return "%s://%s/%s" % (url.drivername, host, database)

    def __str__(self) -> str:
        return "Settings(host=%s, port=%s, database=%s)" % (
            self.host,
            self.port,
            self.public_database_label(),
        )

    def __repr__(self) -> str:
        return self.__str__()


def _port() -> int:
    raw = os.environ.get("KABAMAN_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    if port < 1 or port > 65535:
        return DEFAULT_PORT
    return port


def load_settings() -> Settings:
    raw_url = os.environ.get("DATABASE_URL", "").strip()
    # Phase 1A is local only. A bind address in the environment cannot move it off loopback.
    return Settings(
        database_url=raw_url or None,
        host=LOOPBACK_HOST,
        port=_port(),
    )

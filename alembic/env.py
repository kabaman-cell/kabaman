"""Alembic environment. The database target is validated by api.security and is not printed."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event, pool

from api.models import Base
from api.security import _verify_connection, validated_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Offline Alembic migrations are refused. SQL generation cannot bypass the database-target safety checks."
    )


def run_migrations_online() -> None:
    url = validated_database_url()
    connectable = create_engine(url, poolclass=pool.NullPool, echo=False)
    event.listen(connectable, "connect", _verify_connection)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Initialize kabaman_phase1b_regression_test from revision 0001_phase1.

The URL guard runs before an engine exists. Identity is checked before any
catalog lock. Cleanliness failures and lock failures roll back. Nothing is
dropped.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from phase1b_database import (
    LOOPBACK_ADDRESSES,
    REQUIRED_DATABASE,
    REQUIRED_PORT,
    Phase1BTargetRefusal,
    validated_target,
)

# Reviewed order. These are per-database catalogs, not shared catalogs.
CATALOG_LOCKS = (
    "pg_am",
    "pg_attribute",
    "pg_attrdef",
    "pg_aggregate",
    "pg_cast",
    "pg_class",
    "pg_collation",
    "pg_constraint",
    "pg_conversion",
    "pg_default_acl",
    "pg_depend",
    "pg_enum",
    "pg_event_trigger",
    "pg_extension",
    "pg_foreign_data_wrapper",
    "pg_foreign_server",
    "pg_index",
    "pg_language",
    "pg_largeobject_metadata",
    "pg_namespace",
    "pg_opclass",
    "pg_operator",
    "pg_opfamily",
    "pg_policy",
    "pg_proc",
    "pg_publication",
    "pg_range",
    "pg_rewrite",
    "pg_sequence",
    "pg_statistic_ext",
    "pg_subscription",
    "pg_transform",
    "pg_trigger",
    "pg_ts_config",
    "pg_ts_dict",
    "pg_ts_parser",
    "pg_ts_template",
    "pg_type",
    "pg_user_mapping",
)

NAMESPACE_CATALOGS = (
    ("pg_class", "relnamespace"),
    ("pg_type", "typnamespace"),
    ("pg_proc", "pronamespace"),
    ("pg_operator", "oprnamespace"),
    ("pg_opclass", "opcnamespace"),
    ("pg_opfamily", "opfnamespace"),
    ("pg_collation", "collnamespace"),
    ("pg_conversion", "connamespace"),
    ("pg_ts_config", "cfgnamespace"),
    ("pg_ts_dict", "dictnamespace"),
    ("pg_ts_parser", "prsnamespace"),
    ("pg_ts_template", "tmplnamespace"),
    ("pg_statistic_ext", "stxnamespace"),
)

FIRST_NORMAL_OBJECT_ID = 16384
_CATALOG_NAME = re.compile(r"^pg_[a-z0-9_]+$")
_REVISION_ID = "0001_phase1"


class InitializerRefusal(RuntimeError):
    """Refusal whose message contains neither a URL nor a password."""


def _load_revision():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_phase1.py"
    spec = importlib.util.spec_from_file_location(
        "kabaman_phase1b_regression_revision", path
    )
    if spec is None or spec.loader is None:
        raise InitializerRefusal(
            "Refusing to initialize: revision 0001_phase1 could not be loaded."
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "revision", None) != _REVISION_ID:
        raise InitializerRefusal(
            "Refusing to initialize: revision 0001_phase1 could not be loaded."
        )
    if getattr(module, "downgrade", None) is None or getattr(module, "upgrade", None) is None:
        raise InitializerRefusal(
            "Refusing to initialize: revision 0001_phase1 could not be loaded."
        )
    return module


def _require_identity(connection) -> None:
    database, address, server_port = connection.execute(
        text(
            "SELECT current_database(), host(inet_server_addr()), "
            "inet_server_port()"
        )
    ).one()
    if (
        database != REQUIRED_DATABASE
        or address not in LOOPBACK_ADDRESSES
        or server_port != REQUIRED_PORT
    ):
        raise InitializerRefusal(
            "Refusing to initialize: database=%r address=%r port=%r."
            % (database, address, server_port)
        )


def _require_lock_privilege(connection) -> None:
    row = connection.execute(
        text(
            "SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user"
        )
    ).one_or_none()
    if row is not None and row[0]:
        return
    try:
        member = connection.execute(
            text(
                "SELECT pg_catalog.pg_has_role(current_user, 'pg_maintain', 'MEMBER')"
            )
        ).scalar()
    except Exception:
        raise InitializerRefusal(
            "Refusing to initialize: the current role cannot lock the system catalogs."
        ) from None
    if member is not True:
        raise InitializerRefusal(
            "Refusing to initialize: the current role cannot lock the system catalogs."
        )


def _set_timeouts(connection) -> None:
    connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '60s'"))
    connection.execute(text("SET LOCAL statement_timeout = '120s'"))


def _lock_catalogs(connection) -> None:
    if len(CATALOG_LOCKS) != 39 or len(set(CATALOG_LOCKS)) != 39:
        raise InitializerRefusal(
            "Refusing to initialize: catalog lock list is invalid."
        )
    for catalog in CATALOG_LOCKS:
        if _CATALOG_NAME.fullmatch(catalog) is None:
            raise InitializerRefusal(
                "Refusing to initialize: catalog lock list is invalid."
            )
        try:
            connection.execute(
                text(
                    "LOCK TABLE pg_catalog.%s IN SHARE ROW EXCLUSIVE MODE NOWAIT"
                    % catalog
                )
            )
        except InitializerRefusal:
            raise
        except Exception:
            raise InitializerRefusal(
                "Refusing to initialize: catalog lock was not acquired (%s)."
                % catalog
            ) from None


def _exists(connection, sql: str) -> bool:
    return connection.execute(text(sql)).first() is not None


def _refuse_if(connection, sql: str, label: str) -> None:
    if _exists(connection, sql):
        raise InitializerRefusal(
            "Refusing to initialize: unexpected database objects are present (%s)."
            % label
        )


def _assert_clean(connection) -> None:
    try:
        _refuse_if(
            connection,
            """
            SELECT 1
            FROM pg_catalog.pg_namespace
            WHERE nspname NOT IN (
                    'pg_catalog', 'information_schema', 'public', 'pg_toast'
                  )
              AND NOT starts_with(nspname, 'pg_temp_')
              AND NOT starts_with(nspname, 'pg_toast_temp_')
            LIMIT 1
            """,
            "schema",
        )
        for catalog, namespace_column in NAMESPACE_CATALOGS:
            _refuse_if(
                connection,
                """
                SELECT 1
                FROM pg_catalog.%s AS obj
                JOIN pg_catalog.pg_namespace AS n
                  ON n.oid = obj.%s
                WHERE n.nspname = 'public'
                LIMIT 1
                """
                % (catalog, namespace_column),
                "public.%s" % catalog,
            )
        _refuse_if(
            connection,
            """
            SELECT 1
            FROM pg_catalog.pg_default_acl
            WHERE defaclnamespace = 0
               OR defaclnamespace = (
                    SELECT oid FROM pg_catalog.pg_namespace WHERE nspname = 'public'
                  )
            LIMIT 1
            """,
            "pg_default_acl",
        )
        _refuse_if(
            connection,
            """
            SELECT 1
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE starts_with(n.nspname, 'pg_temp_')
            LIMIT 1
            """,
            "temporary relation",
        )
        _refuse_if(
            connection,
            """
            SELECT 1
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'pg_toast'
              AND c.oid >= %d
            LIMIT 1
            """
            % FIRST_NORMAL_OBJECT_ID,
            "pg_toast",
        )
        for catalog, namespace_column in NAMESPACE_CATALOGS:
            _refuse_if(
                connection,
                """
                SELECT 1
                FROM pg_catalog.%s AS obj
                JOIN pg_catalog.pg_namespace AS n
                  ON n.oid = obj.%s
                WHERE n.nspname = 'pg_catalog'
                  AND obj.oid >= %d
                  AND NOT EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_depend AS d
                        JOIN pg_catalog.pg_extension AS e
                          ON e.oid = d.refobjid
                         AND d.refclassid = 'pg_extension'::regclass
                        WHERE d.classid = '%s'::regclass
                          AND d.objid = obj.oid
                          AND d.deptype = 'e'
                          AND e.extname = 'plpgsql'
                  )
                LIMIT 1
                """
                % (catalog, namespace_column, FIRST_NORMAL_OBJECT_ID, catalog),
                "pg_catalog.%s" % catalog,
            )
        _refuse_if(
            connection,
            """
            SELECT 1 FROM pg_catalog.pg_extension
            WHERE extname <> 'plpgsql'
            LIMIT 1
            """,
            "pg_extension",
        )
        _refuse_if(
            connection,
            """
            SELECT 1 FROM pg_catalog.pg_language
            WHERE lanname NOT IN ('internal', 'c', 'sql', 'plpgsql')
            LIMIT 1
            """,
            "pg_language",
        )
        _refuse_if(
            connection,
            """
            SELECT 1 FROM pg_catalog.pg_am
            WHERE amname NOT IN (
                'heap', 'btree', 'hash', 'gist', 'gin', 'spgist', 'brin'
            )
            LIMIT 1
            """,
            "pg_am",
        )
        for catalog in (
            "pg_foreign_data_wrapper",
            "pg_foreign_server",
            "pg_user_mapping",
            "pg_event_trigger",
            "pg_publication",
            "pg_subscription",
            "pg_largeobject_metadata",
        ):
            _refuse_if(
                connection,
                "SELECT 1 FROM pg_catalog.%s LIMIT 1" % catalog,
                catalog,
            )
        for catalog in ("pg_cast", "pg_transform"):
            _refuse_if(
                connection,
                "SELECT 1 FROM pg_catalog.%s WHERE oid >= %d LIMIT 1"
                % (catalog, FIRST_NORMAL_OBJECT_ID),
                catalog,
            )
    except InitializerRefusal:
        raise
    except Exception:
        raise InitializerRefusal(
            "Refusing to initialize: catalog inspection failed."
        ) from None


def _stamp_version(connection) -> None:
    present = connection.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar()
    if present is not None:
        raise InitializerRefusal(
            "Refusing to initialize: alembic_version already exists."
        )
    connection.execute(
        text(
            "CREATE TABLE public.alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(
        text(
            "INSERT INTO public.alembic_version (version_num) VALUES ('0001_phase1')"
        )
    )
    count, version = connection.execute(
        text("SELECT count(*), min(version_num) FROM public.alembic_version")
    ).one()
    if count != 1 or version != _REVISION_ID:
        raise InitializerRefusal(
            "Refusing to initialize: alembic_version was not stamped."
        )


def _migrate(connection) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    revision = _load_revision()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        revision.upgrade()
    _stamp_version(connection)


def _initialize(connection) -> None:
    _require_identity(connection)
    _require_lock_privilege(connection)
    _set_timeouts(connection)
    _lock_catalogs(connection)
    _assert_clean(connection)
    _migrate(connection)


def main() -> int:
    try:
        parsed = validated_target()
    except Phase1BTargetRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            "Refusing to initialize the regression database (%s)."
            % type(exc).__name__,
            file=sys.stderr,
        )
        return 1

    engine = None
    try:
        engine = create_engine(
            parsed, poolclass=NullPool, echo=False, pool_pre_ping=False
        )
        with engine.connect() as connection:
            with connection.begin():
                _initialize(connection)
    except InitializerRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            "Refusing to initialize the regression database (%s)."
            % type(exc).__name__,
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception as exc:
                print(
                    "The regression database engine could not be released (%s)."
                    % type(exc).__name__,
                    file=sys.stderr,
                )
    print("Initialized kabaman_phase1b_regression_test.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

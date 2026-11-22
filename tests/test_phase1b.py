"""Phase 1B catalog checks.

Tests issue SELECT statements only. They read pg_catalog and the seeded rows.
This suite does not cover constraint enforcement through invalid insert attempts.
"""

import os
import re

import psycopg
import pytest
from sqlalchemy.engine.url import make_url

REQUIRED_DATABASE = "kabaman_phase1b_test"
REQUIRED_PORT = 5432
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_ADDRESSES = {"127.0.0.1", "::1"}

APPLICATION_TABLES = (
    "customers",
    "employees",
    "sessions",
    "roles",
    "permissions",
    "role_permissions",
    "employee_roles",
    "orders",
    "documents",
    "site_settings",
    "audit_logs",
)
PUBLIC_ORDINARY_TABLES = tuple(sorted(APPLICATION_TABLES + ("alembic_version",)))

WHATSAPP_STATUSES = (
    "Nouveau",
    "Confirm\u00e9e",
    "En pr\u00e9paration",
    "Exp\u00e9di\u00e9e",
    "Livr\u00e9e",
    "Annul\u00e9e",
)
WEB_FORMS = ("sourcing", "importation", "inspection", "auction")
WEB_STATUSES = ("Verified", "Not verified")
DOCUMENT_TYPES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
)
ACTOR_TYPES = ("customer", "employee", "anonymous")

ROLES = ("operator", "order_reviewer", "site_editor")
PERMISSIONS = (
    "audit.read",
    "documents.read",
    "orders.delete",
    "orders.read_all",
    "orders.reply",
    "orders.update_status",
    "site.write",
    "whatsapp.read",
    "whatsapp.write",
)
GRANTS = (
    ("operator", "audit.read"),
    ("operator", "orders.delete"),
    ("operator", "whatsapp.read"),
    ("operator", "whatsapp.write"),
    ("order_reviewer", "documents.read"),
    ("order_reviewer", "orders.read_all"),
    ("order_reviewer", "orders.reply"),
    ("order_reviewer", "orders.update_status"),
    ("site_editor", "site.write"),
)

CHECK_TABLES = {
    "ck_customers_email_lowercase": "customers",
    "ck_employees_email_lowercase": "employees",
    "ck_sessions_principal": "sessions",
    "ck_orders_source_shape": "orders",
    "ck_documents_content_type": "documents",
    "ck_documents_byte_size": "documents",
    "ck_documents_bytes_removed": "documents",
    "ck_site_settings_id": "site_settings",
    "ck_audit_logs_actor_type": "audit_logs",
}

FOREIGN_KEYS = (
    ("documents", "created_by_customer_id", "customers", "id", "r"),
    ("documents", "order_id", "orders", "id", "r"),
    ("employee_roles", "employee_id", "employees", "id", "c"),
    ("employee_roles", "role_id", "roles", "id", "c"),
    ("orders", "customer_id", "customers", "id", "r"),
    ("orders", "entered_by_employee_id", "employees", "id", "r"),
    ("role_permissions", "permission_id", "permissions", "id", "c"),
    ("role_permissions", "role_id", "roles", "id", "c"),
    ("sessions", "customer_id", "customers", "id", "c"),
    ("sessions", "employee_id", "employees", "id", "c"),
    ("site_settings", "updated_by_employee_id", "employees", "id", "n"),
)

UNIQUE_CONSTRAINTS = {
    "uq_customers_email": ("customers", ("email",)),
    "uq_employees_email": ("employees", ("email",)),
    "uq_sessions_token_hash": ("sessions", ("token_hash",)),
    "uq_roles_name": ("roles", ("name",)),
    "uq_permissions_code": ("permissions", ("code",)),
    "uq_orders_ref": ("orders", ("ref",)),
    "uq_documents_storage_key": ("documents", ("storage_key",)),
}

PRIMARY_KEYS = {
    "customers": ("id",),
    "employees": ("id",),
    "sessions": ("id",),
    "roles": ("id",),
    "permissions": ("id",),
    "role_permissions": ("role_id", "permission_id"),
    "employee_roles": ("employee_id", "role_id"),
    "orders": ("id",),
    "documents": ("id",),
    "site_settings": ("id",),
    "audit_logs": ("id",),
}

INDEXES = {
    "ix_sessions_expires_at_open": ("sessions", ("expires_at",), "revoked_at IS NULL"),
    "ix_orders_customer_created": ("orders", ("customer_id", "created_at"), None),
    "ix_orders_source_status": ("orders", ("source", "status"), None),
    "ix_orders_form": ("orders", ("form",), None),
    "ix_documents_order_id": ("documents", ("order_id",), None),
    "ix_audit_logs_at": ("audit_logs", ("at",), None),
    "ix_audit_logs_object": ("audit_logs", ("object_type", "object_id"), None),
}


def column(name, typ, nullable=False, identity="", default=None):
    return (name, typ, nullable, identity, default)


def identity_column(name="id", typ="bigint"):
    return column(name, typ, identity="d")


def stamp(name):
    return column(name, "timestamp with time zone", default="now()")


def optional_stamp(name):
    return column(name, "timestamp with time zone", nullable=True)


EXPECTED_COLUMNS = {
    "customers": (
        identity_column(),
        column("email", "text"),
        column("name", "text"),
        column("phone", "text", default="''::text"),
        column("password_hash", "text"),
        stamp("created_at"),
        stamp("updated_at"),
    ),
    "employees": (
        identity_column(),
        column("email", "text"),
        column("name", "text"),
        column("password_hash", "text"),
        column("is_active", "boolean", default="true"),
        stamp("created_at"),
        stamp("updated_at"),
    ),
    "sessions": (
        identity_column(),
        column("token_hash", "text"),
        column("principal_type", "text"),
        column("customer_id", "bigint", nullable=True),
        column("employee_id", "bigint", nullable=True),
        stamp("created_at"),
        column("expires_at", "timestamp with time zone"),
        optional_stamp("revoked_at"),
    ),
    "roles": (
        identity_column(),
        column("name", "text"),
    ),
    "permissions": (
        identity_column(),
        column("code", "text"),
    ),
    "role_permissions": (
        column("role_id", "bigint"),
        column("permission_id", "bigint"),
    ),
    "employee_roles": (
        column("employee_id", "bigint"),
        column("role_id", "bigint"),
    ),
    "orders": (
        identity_column(),
        column("ref", "text"),
        column("customer_id", "bigint", nullable=True),
        column("entered_by_employee_id", "bigint", nullable=True),
        column("source", "text"),
        column("form", "text", nullable=True),
        column("status", "text"),
        column("reply", "text", default="''::text"),
        column("details", "jsonb"),
        column("has_document", "boolean", default="false"),
        optional_stamp("deletion_requested_at"),
        stamp("created_at"),
        stamp("updated_at"),
    ),
    "documents": (
        identity_column(),
        column("order_id", "bigint"),
        column("filename", "text"),
        column("content_type", "text"),
        column("byte_size", "integer"),
        column("sha256", "text"),
        column("storage_key", "text"),
        stamp("created_at"),
        column("created_by_customer_id", "bigint", nullable=True),
        optional_stamp("deletion_requested_at"),
        optional_stamp("bytes_removed_at"),
    ),
    "site_settings": (
        column("id", "smallint"),
        column("data", "jsonb"),
        stamp("updated_at"),
        column("updated_by_employee_id", "bigint", nullable=True),
    ),
    "audit_logs": (
        identity_column(),
        stamp("at"),
        column("actor_type", "text"),
        column("actor_id", "bigint", nullable=True),
        column("action", "text"),
        column("object_type", "text"),
        column("object_id", "text"),
        column("metadata", "jsonb", default="'{}'::jsonb"),
    ),
}


def _target_from_environment():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        pytest.fail("DATABASE_URL is not set. Refusing to connect.")
    try:
        parsed = make_url(raw)
    except Exception:
        pytest.fail("DATABASE_URL could not be parsed. Refusing to connect.")
    if (
        parsed.database != REQUIRED_DATABASE
        or parsed.host not in ALLOWED_HOSTS
        or parsed.port != REQUIRED_PORT
    ):
        pytest.fail(
            "Refusing to connect: database=%r host=%r port=%r."
            % (parsed.database, parsed.host, parsed.port)
        )
    return parsed


def _connect(parsed):
    kwargs = {
        "host": parsed.host,
        "port": parsed.port,
        "dbname": parsed.database,
        "connect_timeout": 3,
        "options": "-c default_transaction_read_only=on",
    }
    if parsed.username:
        kwargs["user"] = parsed.username
    if parsed.password is not None:
        kwargs["password"] = parsed.password
    try:
        return psycopg.connect(**kwargs)
    except Exception as exc:
        pytest.fail(
            "Refusing to continue: the loopback test database did not open (%s)."
            % type(exc).__name__
        )


@pytest.fixture
def db():
    parsed = _target_from_environment()
    conn = _connect(parsed)
    try:
        row = conn.execute(
            "SELECT current_database(), host(inet_server_addr()), "
            "inet_server_port(), current_setting('transaction_read_only')"
        ).fetchone()
        database, address, server_port, read_only = row
        if (
            database != REQUIRED_DATABASE
            or address not in LOOPBACK_ADDRESSES
            or server_port != REQUIRED_PORT
            or read_only != "on"
        ):
            pytest.fail(
                "Refusing to use this connection: database=%r address=%r port=%r read_only=%r."
                % (database, address, server_port, read_only)
            )
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def _fold(definition):
    return " ".join(definition.replace("::text", "").split())


def _quoted_literals(definition):
    return re.findall(r"'((?:[^']|'')*)'", definition)


def _bare(expression):
    if expression is None:
        return None
    text = " ".join(expression.split())
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return text


def _columns(conn):
    found = {name: [] for name in APPLICATION_TABLES}
    sql = """
        SELECT c.relname, a.attname,
               pg_catalog.format_type(a.atttypid, a.atttypmod),
               a.attnotnull,
               COALESCE(a.attidentity::text, ''),
               pg_get_expr(d.adbin, d.adrelid)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = 'public'
          AND c.relname = ANY(%s)
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY c.relname, a.attnum
    """
    for table, name, typ, not_null, identity, default in conn.execute(
        sql, (list(APPLICATION_TABLES),)
    ):
        found[table].append((name, typ, not not_null, (identity or "").strip(), default))
    return {table: tuple(cols) for table, cols in found.items()}


def _check_definitions(conn):
    sql = """
        SELECT con.conname, rel.relname, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = 'public' AND con.contype = 'c'
        ORDER BY con.conname
    """
    return list(conn.execute(sql))


def test_connection_is_the_phase1b_loopback_database(db):
    database, address, server_port, read_only = db.execute(
        "SELECT current_database(), host(inet_server_addr()), "
        "inet_server_port(), current_setting('transaction_read_only')"
    ).fetchone()
    assert database == REQUIRED_DATABASE
    assert address in LOOPBACK_ADDRESSES
    assert server_port == REQUIRED_PORT
    assert read_only == "on"


def test_application_tables_exist(db):
    found = [
        row[0]
        for row in db.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (list(APPLICATION_TABLES),),
        )
    ]
    assert found == sorted(APPLICATION_TABLES)


def test_public_ordinary_tables_are_exact(db):
    # relkind r is an ordinary table. The public schema must contain these 12 and no others.
    found = [
        row[0]
        for row in db.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
            ORDER BY c.relname
            """
        )
    ]
    assert found == list(PUBLIC_ORDINARY_TABLES)


def test_alembic_version_is_0001_phase1(db):
    versions = [row[0] for row in db.execute("SELECT version_num FROM alembic_version")]
    assert versions == ["0001_phase1"]


def test_columns_types_nullability_and_defaults(db):
    assert _columns(db) == EXPECTED_COLUMNS


def test_check_constraints(db):
    # Catalog text only. This test does not submit invalid rows.
    rows = _check_definitions(db)
    assert {name: table for name, table, _definition in rows} == CHECK_TABLES
    by_name = {name: definition for name, _table, definition in rows}

    customers = _fold(by_name["ck_customers_email_lowercase"])
    employees = _fold(by_name["ck_employees_email_lowercase"])
    assert "email = lower(email)" in customers
    assert "email = lower(email)" in employees

    sessions = _fold(by_name["ck_sessions_principal"])
    for fragment in (
        "principal_type = 'customer'",
        "customer_id IS NOT NULL",
        "employee_id IS NULL",
        "principal_type = 'employee'",
        "employee_id IS NOT NULL",
        "customer_id IS NULL",
    ):
        assert fragment in sessions

    assert "id = 1" in _fold(by_name["ck_site_settings_id"])
    assert set(_quoted_literals(by_name["ck_audit_logs_actor_type"])) == set(ACTOR_TYPES)

    documents_removed = _fold(by_name["ck_documents_bytes_removed"])
    assert "bytes_removed_at IS NULL" in documents_removed
    assert "deletion_requested_at IS NOT NULL" in documents_removed

    byte_size = _fold(by_name["ck_documents_byte_size"])
    assert "byte_size >= 1" in byte_size
    assert "byte_size <= 1800000" in byte_size
    assert set(_quoted_literals(by_name["ck_documents_content_type"])) == set(DOCUMENT_TYPES)


def test_foreign_keys_and_delete_actions(db):
    rows = [
        tuple(row)
        for row in db.execute(
            """
            SELECT src.relname, src_att.attname, dst.relname, dst_att.attname, con.confdeltype
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = src.relnamespace
            JOIN pg_class dst ON dst.oid = con.confrelid
            JOIN unnest(con.conkey, con.confkey) AS cols(src_num, dst_num) ON true
            JOIN pg_attribute src_att
              ON src_att.attrelid = src.oid AND src_att.attnum = cols.src_num
            JOIN pg_attribute dst_att
              ON dst_att.attrelid = dst.oid AND dst_att.attnum = cols.dst_num
            WHERE n.nspname = 'public' AND con.contype = 'f'
            ORDER BY src.relname, src_att.attname
            """
        )
    ]
    assert rows == list(FOREIGN_KEYS)


def test_unique_constraints_and_primary_keys(db):
    unique = {}
    primary = {name: [] for name in APPLICATION_TABLES}
    sql = """
        SELECT rel.relname, con.contype, con.conname,
               array_agg(att.attname ORDER BY cols.ord)
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        JOIN unnest(con.conkey) WITH ORDINALITY AS cols(attnum, ord) ON true
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = cols.attnum
        WHERE n.nspname = 'public' AND con.contype IN ('u', 'p')
        GROUP BY rel.relname, con.contype, con.conname
    """
    for table, contype, name, columns in db.execute(sql):
        key = tuple(columns)
        if contype == "u":
            unique[name] = (table, key)
        elif table in primary:
            primary[table].append(key)
    assert unique == UNIQUE_CONSTRAINTS
    assert {table: keys[0] for table, keys in primary.items()} == PRIMARY_KEYS
    assert all(len(keys) == 1 for keys in primary.values())


def test_seven_nonunique_indexes(db):
    found = {}
    sql = """
        SELECT c.relname, t.relname, i.indisunique,
               pg_get_expr(i.indpred, i.indrelid),
               (
                 SELECT array_agg(a.attname ORDER BY cols.ord)
                 FROM unnest(i.indkey) WITH ORDINALITY AS cols(attnum, ord)
                 JOIN pg_attribute a
                   ON a.attrelid = t.oid AND a.attnum = cols.attnum
               )
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND t.relname = ANY(%s)
          AND NOT i.indisunique
    """
    for name, table, unique, predicate, columns in db.execute(sql, (list(APPLICATION_TABLES),)):
        assert unique is False
        found[name] = (table, tuple(columns), _bare(predicate))
    assert found == INDEXES


def test_seeded_roles_permissions_and_grants(db):
    roles = [row[0] for row in db.execute("SELECT name FROM roles ORDER BY name")]
    permissions = [row[0] for row in db.execute("SELECT code FROM permissions ORDER BY code")]
    grants = [
        tuple(row)
        for row in db.execute(
            """
            SELECT r.name, p.code
            FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            ORDER BY r.name, p.code
            """
        )
    ]
    employee_rows = db.execute("SELECT count(*) FROM employees").fetchone()[0]
    employee_role_rows = db.execute("SELECT count(*) FROM employee_roles").fetchone()[0]
    assert roles == list(ROLES)
    assert permissions == list(PERMISSIONS)
    assert grants == list(GRANTS)
    assert employee_rows == 0
    assert employee_role_rows == 0


def test_sessions_use_token_hash_and_have_no_raw_token(db):
    names = [
        row[0]
        for row in db.execute(
            """
            SELECT a.attname
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'sessions'
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
            """
        )
    ]
    assert "token_hash" in names
    assert "token" not in names
    assert [name for name in names if "token" in name] == ["token_hash"]


def test_orders_source_status_form_rules(db):
    # Catalog text only. This test does not submit a web row with a WhatsApp status.
    definition = dict((name, body) for name, _table, body in _check_definitions(db))[
        "ck_orders_source_shape"
    ]
    for char in definition:
        if ord(char) > 127:
            assert ord(char) == 0x00E9
    assert set(_quoted_literals(definition)) == set(WEB_FORMS) | set(WEB_STATUSES) | set(
        WHATSAPP_STATUSES
    ) | {"web", "whatsapp_manual"}
    folded = _fold(definition)
    for fragment in (
        "source = 'web'",
        "customer_id IS NOT NULL",
        "source = 'whatsapp_manual'",
        "form IS NULL",
        "entered_by_employee_id IS NOT NULL",
    ):
        assert fragment in folded
    assert "legacy_cart" not in folded


def test_documents_metadata_content_types_size_and_deletion(db):
    columns = _columns(db)["documents"]
    assert columns == EXPECTED_COLUMNS["documents"]
    assert all(item[1] != "bytea" for item in columns)
    definitions = dict((name, body) for name, _table, body in _check_definitions(db))
    assert set(_quoted_literals(definitions["ck_documents_content_type"])) == set(DOCUMENT_TYPES)
    byte_size = _fold(definitions["ck_documents_byte_size"])
    assert "byte_size >= 1" in byte_size
    assert "byte_size <= 1800000" in byte_size
    removed = _fold(definitions["ck_documents_bytes_removed"])
    assert "bytes_removed_at IS NULL" in removed
    assert "deletion_requested_at IS NOT NULL" in removed


def test_orders_deletion_requested_at_is_present(db):
    match = [
        item
        for item in _columns(db)["orders"]
        if item[0] == "deletion_requested_at"
    ]
    assert match == [optional_stamp("deletion_requested_at")]


def test_no_auth_rate_limits_and_no_document_bytea(db):
    rate_tables = [
        tuple(row)
        for row in db.execute(
            """
            SELECT n.nspname, c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'auth_rate_limits'
              AND c.relkind IN ('r', 'p', 'f')
            """
        )
    ]
    bytea_columns = [
        row[0]
        for row in db.execute(
            """
            SELECT a.attname
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'documents'
              AND a.attnum > 0
              AND NOT a.attisdropped
              AND pg_catalog.format_type(a.atttypid, a.atttypmod) = 'bytea'
            """
        )
    ]
    assert rate_tables == []
    assert bytea_columns == []

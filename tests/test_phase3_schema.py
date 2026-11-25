"""Static Phase 3 schema checks. Importing these modules does not open PostgreSQL."""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import configure_mappers
from sqlalchemy.sql.elements import TextClause

from api.models import (
    CK_IDENTITY_BYTES_REMOVED,
    CK_IDENTITY_EXPIRY,
    CK_IDENTITY_RETENTION,
    IDENTITY_BYTE_RETENTION_DAYS,
    MAX_SERVICE_ORDER_ITEMS,
    ORDER_ITEM_LIMIT_ENFORCED_BY,
    WHATSAPP_NONCE_RETENTION_SECONDS,
    WHATSAPP_SIGNATURE_WINDOW_SECONDS,
    Base,
    Order,
    next_identity_page_sequence,
    whatsapp_accepted_request_replayable_after_cleanup,
    whatsapp_nonce_deleted_at,
    whatsapp_timestamp_accepted,
)
from api.security import REFUSED_DATABASES, REQUIRED_DATABASE

ROOT = Path(__file__).resolve().parents[1]
REVISION_0001 = ROOT / "alembic" / "versions" / "0001_phase1.py"
REVISION_0002 = ROOT / "alembic" / "versions" / "0002_phase3_orders.py"
REVISION_0001_SHA256 = "d513d58b0df9bfa13edab68f8c95a9b71708463f044db6f494d002e7d7c69f14"

LEGACY_TABLES = {
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
}
PHASE3_TABLES = {
    "service_types",
    "identity_verifications",
    "identity_documents",
    "service_orders",
    "order_items",
    "order_attachments",
    "order_status_events",
    "order_assignments",
    "notification_outbox",
    "service_credentials",
    "service_request_nonces",
}
LEGACY_ORDER_COLUMNS = {
    "id",
    "ref",
    "customer_id",
    "entered_by_employee_id",
    "source",
    "form",
    "status",
    "reply",
    "details",
    "has_document",
    "deletion_requested_at",
    "created_at",
    "updated_at",
}
LEGACY_ORDER_CONSTRAINTS = {
    "ck_orders_source_shape",
    "ix_orders_customer_created",
    "ix_orders_source_status",
    "ix_orders_form",
    "uq_orders_ref",
}
LEGACY_DOCUMENT_COLUMNS = {
    "id",
    "order_id",
    "filename",
    "content_type",
    "byte_size",
    "sha256",
    "storage_key",
    "created_at",
    "created_by_customer_id",
    "deletion_requested_at",
    "bytes_removed_at",
}
PARTIAL_INDEXES = {
    "uq_identity_one_pending": "status = 'pending_review'",
    "uq_identity_one_approved": "status = 'approved'",
    "uq_identity_one_front": "page_kind = 'front'",
    "uq_identity_one_back": "page_kind = 'back'",
    "uq_one_open_assignment": "released_at IS NULL",
}
PROTECTED_DATABASES = {
    "kabaman_os",
    "kabaman_phase1b_test",
    "kabaman_phase1c_test",
    "kabaman_phase1b_regression_test",
    "kabaman_phase2c_auth_test",
}


def _load_revision(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _where_text(index: Index) -> str:
    clause = index.dialect_options["postgresql"]["where"]
    if isinstance(clause, TextClause):
        return str(clause.text)
    return str(clause)


def test_mappers_configure_without_a_connection():
    configure_mappers()
    assert Base.metadata.tables["service_orders"].name == "service_orders"


def test_metadata_adds_phase3_tables_without_removing_legacy_tables():
    assert set(Base.metadata.tables) == LEGACY_TABLES | PHASE3_TABLES


def test_legacy_orders_and_documents_keep_their_shape():
    orders = Base.metadata.tables["orders"]
    documents = Base.metadata.tables["documents"]
    assert set(orders.columns.keys()) == LEGACY_ORDER_COLUMNS
    named = {item.name for item in orders.constraints if item.name} | {index.name for index in orders.indexes}
    assert named == LEGACY_ORDER_CONSTRAINTS
    assert list(orders.primary_key.columns.keys()) == ["id"]
    shape = next(item for item in orders.constraints if item.name == "ck_orders_source_shape")
    assert isinstance(shape, CheckConstraint)
    assert "source = 'web'" in str(shape.sqltext)
    assert "source = 'whatsapp_manual'" in str(shape.sqltext)
    assert "ck_orders_source_shape" in Order.__table_args__[0].name
    assert set(documents.columns.keys()) == LEGACY_DOCUMENT_COLUMNS
    assert {item.name for item in documents.constraints if item.name} >= {
        "ck_documents_content_type",
        "ck_documents_byte_size",
        "ck_documents_bytes_removed",
        "uq_documents_storage_key",
    }


def test_phase3_revision_follows_phase1_and_phase1_file_is_unchanged():
    phase1 = _load_revision(REVISION_0001, "kabaman_revision_0001_static")
    phase3 = _load_revision(REVISION_0002, "kabaman_revision_0002_static")
    assert phase1.revision == "0001_phase1"
    assert phase1.down_revision is None
    assert phase3.revision == "0002_phase3_orders"
    assert phase3.down_revision == "0001_phase1"
    assert hashlib.sha256(REVISION_0001.read_bytes()).hexdigest() == REVISION_0001_SHA256
    assert not hasattr(phase3, "upgrade") or callable(phase3.upgrade)
    assert phase3.upgrade.__defaults__ is None


def test_migration_source_is_additive():
    source = REVISION_0002.read_text(encoding="utf-8")
    assert re.search(r"""create_table\(\s*["']orders["']""", source) is None
    assert re.search(r"""create_table\(\s*["']documents["']""", source) is None
    assert re.search(r"""alter_table\(\s*["']orders["']""", source) is None
    assert re.search(r"""alter_table\(\s*["']documents["']""", source) is None
    assert "ck_orders_source_shape" not in source
    assert '"orders.id"' not in source
    assert "'orders.id'" not in source
    assert '"documents.id"' not in source
    assert "'documents.id'" not in source
    assert "create_all" not in source
    assert "INSERT INTO employee_roles" not in source
    for name in PROTECTED_DATABASES:
        assert name not in source
    for table_name in PHASE3_TABLES:
        assert 'create_table(\n        "%s"' % table_name in source


def test_service_orders_do_not_reference_legacy_orders():
    table = Base.metadata.tables["service_orders"]
    targets = set()
    for constraint in table.foreign_key_constraints:
        targets.add(tuple(element.column.table.name for element in constraint.elements))
    assert ("orders",) not in targets
    assert ("documents",) not in targets
    composite = next(item for item in table.foreign_key_constraints if item.name == "fk_service_orders_identity_customer")
    assert isinstance(composite, ForeignKeyConstraint)
    assert [element.parent.name for element in composite.elements] == [
        "identity_verification_id",
        "customer_id",
    ]
    assert [element.column.name for element in composite.elements] == ["id", "customer_id"]
    assert composite.elements[0].column.table.name == "identity_verifications"
    assert composite.ondelete == "RESTRICT"


def test_partial_unique_indexes_and_named_checks_are_present():
    found = {}
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            if index.name in PARTIAL_INDEXES:
                found[index.name] = (index.unique, _where_text(index))
    assert found == {name: (True, clause) for name, clause in PARTIAL_INDEXES.items()}
    identity = Base.metadata.tables["identity_verifications"]
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_identity_id_customer"
        for item in identity.constraints
    )
    orders = Base.metadata.tables["service_orders"]
    assert any(isinstance(item, UniqueConstraint) and item.name == "uq_order_idempotency" for item in orders.constraints)
    checks = {
        item.name
        for table in Base.metadata.tables.values()
        if table.name in PHASE3_TABLES
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    }
    assert {
        "ck_service_types_code",
        "ck_identity_expiry",
        "ck_service_orders_identity",
        "ck_service_orders_waiting",
        "ck_identity_retention",
        "ck_order_items_weight",
        "ck_service_credentials_scope",
        "ck_service_nonces_nonce",
    } <= checks


def test_identity_retention_and_item_limit_constants():
    column = Base.metadata.tables["identity_documents"].columns["retain_bytes_until"]
    assert IDENTITY_BYTE_RETENTION_DAYS == 365
    assert "365 days" in str(column.server_default.arg)
    assert CK_IDENTITY_RETENTION == "retain_bytes_until >= created_at"
    assert "bytes_removed_at >= retain_bytes_until" in CK_IDENTITY_BYTES_REMOVED
    documents = Base.metadata.tables["identity_documents"]
    assert any(item.name == "ck_identity_retention" for item in documents.constraints)
    assert any(item.name == "ck_identity_bytes_removed" for item in documents.constraints)
    assert "national_id" in CK_IDENTITY_EXPIRY and "expires_on IS NULL" in CK_IDENTITY_EXPIRY
    assert "passport" in CK_IDENTITY_EXPIRY and "driving_license" in CK_IDENTITY_EXPIRY
    assert "expires_on IS NOT NULL" in CK_IDENTITY_EXPIRY
    assert any(item.name == "ck_identity_expiry" for item in Base.metadata.tables["identity_verifications"].constraints)
    assert MAX_SERVICE_ORDER_ITEMS == 20
    assert ORDER_ITEM_LIMIT_ENFORCED_BY == "order_engine"
    for table_name in ("service_orders", "order_items"):
        for item in Base.metadata.tables[table_name].constraints:
            if isinstance(item, CheckConstraint):
                assert "20" not in str(item.sqltext)
    weight = Base.metadata.tables["order_items"].columns["weight_kg"]
    assert weight.type.precision == 8
    assert weight.type.scale == 3
    service_weight = Base.metadata.tables["service_types"].columns["max_total_weight_kg"]
    assert isinstance(service_weight.type.precision, int)
    assert service_weight.type.scale == 3


def test_revision_seeds_match_the_approved_grants():
    phase3 = _load_revision(REVISION_0002, "kabaman_revision_0002_seeds")
    assert phase3.SERVICE_TYPE_ROWS == (
        {"code": "sourcing", "min_total_quantity": None, "max_total_weight_kg": None},
        {"code": "importation", "min_total_quantity": 250, "max_total_weight_kg": phase3.SERVICE_TYPE_ROWS[1]["max_total_weight_kg"]},
        {"code": "inspection", "min_total_quantity": None, "max_total_weight_kg": None},
        {"code": "auction", "min_total_quantity": None, "max_total_weight_kg": None},
    )
    assert str(phase3.SERVICE_TYPE_ROWS[1]["max_total_weight_kg"]) == "100.000"
    assert phase3.NEW_ROLE_PERMISSIONS == {
        "order_clerk": ("orders.create", "orders.update", "orders.read"),
        "order_approver": ("orders.read_all", "orders.review", "orders.approve", "orders.reject"),
        "fulfillment_operator": ("orders.assign", "orders.read"),
        "identity_reviewer": ("identity.read", "identity.review", "identity.approve", "identity.reject"),
        "order_reader": ("orders.read_all",),
        "administrator": (
            "orders.create",
            "orders.read",
            "orders.read_all",
            "orders.update",
            "orders.review",
            "orders.approve",
            "orders.reject",
            "orders.assign",
            "identity.read",
            "identity.review",
            "identity.approve",
            "identity.reject",
            "employees.roles.manage",
            "audit.read",
        ),
    }
    denied = {"orders.delete", "site.write", "whatsapp.read", "whatsapp.write", "orders.update_status"}
    assert denied.isdisjoint(phase3.NEW_ROLE_PERMISSIONS["administrator"])
    assert "orders.read_all" not in phase3.NEW_PERMISSION_CODES
    assert "audit.read" not in phase3.NEW_PERMISSION_CODES
    assert "order_reviewer" not in phase3.NEW_ROLE_PERMISSIONS
    assert "operator" not in phase3.NEW_ROLE_PERMISSIONS
    assert "site_editor" not in phase3.NEW_ROLE_PERMISSIONS


def test_phase1_role_seed_remains_the_original_three_roles():
    phase1 = _load_revision(REVISION_0001, "kabaman_revision_0001_roles")
    assert set(phase1.ROLE_PERMISSIONS) == {"order_reviewer", "site_editor", "operator"}
    assert phase1.ROLE_PERMISSIONS["order_reviewer"] == (
        "orders.read_all",
        "orders.update_status",
        "orders.reply",
        "documents.read",
    )


def test_database_allowlist_is_unchanged():
    assert REQUIRED_DATABASE == "kabaman_phase3_orders_test"
    assert REFUSED_DATABASES == PROTECTED_DATABASES


def test_administrator_includes_orders_read_all_without_employee_grants():
    phase3 = _load_revision(REVISION_0002, "kabaman_revision_0002_administrator")
    grants = phase3.NEW_ROLE_PERMISSIONS["administrator"]
    assert "orders.read_all" in grants
    assert "employees.roles.manage" in grants
    assert "audit.read" in grants
    assert "orders.read_all" not in phase3.NEW_PERMISSION_CODES
    source = REVISION_0002.read_text(encoding="utf-8")
    assert "INSERT INTO employee_roles" not in source
    assert "order_reviewer" not in phase3.NEW_ROLE_PERMISSIONS
    assert "site_editor" not in phase3.NEW_ROLE_PERMISSIONS
    assert "operator" not in phase3.NEW_ROLE_PERMISSIONS


def test_extra_pages_have_unique_sequences_for_one_kind():
    table = Base.metadata.tables["identity_documents"]
    constraint = next(item for item in table.constraints if item.name == "uq_identity_document_page")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == [
        "verification_id",
        "page_kind",
        "page_sequence",
    ]
    kind_only = [
        item
        for item in table.constraints
        if isinstance(item, UniqueConstraint)
        and [column.name for column in item.columns] == ["verification_id", "page_kind"]
    ]
    assert kind_only == []
    assert "uq_identity_one_front" in {index.name for index in table.indexes}
    assert "uq_identity_one_back" in {index.name for index in table.indexes}
    assert "uq_identity_document_page" in REVISION_0002.read_text(encoding="utf-8")
    assert next_identity_page_sequence([]) == 1
    assert next_identity_page_sequence([1, 2, 4]) == 5
    assert next_identity_page_sequence([1]) == next_identity_page_sequence([1])


def test_whatsapp_timestamp_window_rejects_the_future():
    server_time = 1_700_000_000
    assert whatsapp_timestamp_accepted(server_time, server_time) is True
    assert whatsapp_timestamp_accepted(server_time, server_time - WHATSAPP_SIGNATURE_WINDOW_SECONDS) is True
    assert whatsapp_timestamp_accepted(server_time, server_time - WHATSAPP_SIGNATURE_WINDOW_SECONDS - 1) is False
    assert whatsapp_timestamp_accepted(server_time, server_time + 1) is False
    assert whatsapp_timestamp_accepted(server_time, server_time + WHATSAPP_SIGNATURE_WINDOW_SECONDS) is False


def test_cleanup_cannot_make_an_accepted_whatsapp_request_replayable():
    table = Base.metadata.tables["service_request_nonces"]
    assert list(table.primary_key.columns.keys()) == ["credential_id", "nonce"]
    assert WHATSAPP_SIGNATURE_WINDOW_SECONDS == 600
    assert WHATSAPP_NONCE_RETENTION_SECONDS == 15 * 60
    accepted_at = 1_700_000_000
    for skew in range(WHATSAPP_SIGNATURE_WINDOW_SECONDS + 1):
        signed_timestamp = accepted_at - skew
        assert whatsapp_timestamp_accepted(accepted_at, signed_timestamp) is True
        last_valid_at = signed_timestamp + WHATSAPP_SIGNATURE_WINDOW_SECONDS
        deleted_at = accepted_at + WHATSAPP_NONCE_RETENTION_SECONDS
        assert deleted_at > last_valid_at
        assert whatsapp_timestamp_accepted(deleted_at, signed_timestamp) is False
        assert whatsapp_nonce_deleted_at(accepted_at, deleted_at) is True
        for checked_at in range(accepted_at, last_valid_at + 1):
            assert whatsapp_nonce_deleted_at(accepted_at, checked_at) is False
            assert (
                whatsapp_accepted_request_replayable_after_cleanup(
                    accepted_at,
                    signed_timestamp,
                    checked_at,
                )
                is False
            )
        assert (
            whatsapp_accepted_request_replayable_after_cleanup(
                accepted_at,
                signed_timestamp,
                deleted_at,
            )
            is False
        )
    assert whatsapp_timestamp_accepted(accepted_at, accepted_at + WHATSAPP_SIGNATURE_WINDOW_SECONDS) is False
    assert "DELETE FROM service_request_nonces" not in REVISION_0002.read_text(encoding="utf-8")


def test_named_foreign_keys_use_restrict_except_nonce_cascade():
    expected_delete = {"fk_service_request_nonces_credential": "CASCADE"}
    for table_name in PHASE3_TABLES:
        table = Base.metadata.tables[table_name]
        for constraint in table.foreign_key_constraints:
            if constraint.name in expected_delete:
                assert constraint.ondelete == "CASCADE"
            else:
                assert constraint.ondelete == "RESTRICT"
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                assert foreign_key.ondelete in {"RESTRICT", "CASCADE"}
                if foreign_key.name == "fk_service_request_nonces_credential":
                    assert foreign_key.ondelete == "CASCADE"

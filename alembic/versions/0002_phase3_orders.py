"""Phase 3 order foundation. Additive tables and seeds only.

Revision ID: 0002_phase3_orders
Revises: 0001_phase1
Create Date: 2026-11-24

This revision does not alter the legacy order table, the legacy document table,
or their existing checks. It does not insert employee role assignments.
"""

from __future__ import annotations

from decimal import Decimal

from alembic import op
import sqlalchemy as sa

from api.models import (
    CK_IDENTITY_BYTE_SIZE,
    CK_IDENTITY_BYTES_REMOVED,
    CK_IDENTITY_CONTENT_TYPE,
    CK_IDENTITY_DECISION,
    CK_IDENTITY_DOCUMENT_TYPE,
    CK_IDENTITY_ENCRYPTION,
    CK_IDENTITY_EXPIRY,
    CK_IDENTITY_PAGE_KIND,
    CK_IDENTITY_PAGE_SEQUENCE,
    CK_IDENTITY_PENDING,
    CK_IDENTITY_REJECTION_REASON,
    CK_IDENTITY_RETENTION,
    CK_IDENTITY_SHA256,
    CK_IDENTITY_STATUS,
    CK_ORDER_ATTACHMENT_BYTE_SIZE,
    CK_ORDER_ATTACHMENT_CONTENT_TYPE,
    CK_ORDER_ATTACHMENT_CREATOR,
    CK_ORDER_ATTACHMENT_ENCRYPTION,
    CK_ORDER_ATTACHMENT_SHA256,
    CK_ORDER_EVENT_ACTOR,
    CK_ORDER_EVENT_FROM_STATUS,
    CK_ORDER_EVENT_TO_STATUS,
    CK_ORDER_EVENT_VERSION,
    CK_ORDER_ITEM_BID,
    CK_ORDER_ITEM_POSITION,
    CK_ORDER_ITEM_QUANTITY,
    CK_ORDER_ITEM_WEIGHT,
    CK_SERVICE_CREDENTIAL_ALGORITHM,
    CK_SERVICE_CREDENTIAL_KEY,
    CK_SERVICE_CREDENTIAL_SCOPE,
    CK_SERVICE_NONCE,
    CK_SERVICE_NONCE_HASH,
    CK_SERVICE_ORDER_ACTOR,
    CK_SERVICE_ORDER_CHANNEL,
    CK_SERVICE_ORDER_DRAFT,
    CK_SERVICE_ORDER_HASH,
    CK_SERVICE_ORDER_IDENTITY,
    CK_SERVICE_ORDER_STATUS,
    CK_SERVICE_ORDER_VERSION,
    CK_SERVICE_ORDER_WAITING,
    CK_SERVICE_TYPES_CODE,
    CK_SERVICE_TYPES_MAX_WEIGHT,
    CK_SERVICE_TYPES_MIN_QUANTITY,
    RETAIN_BYTES_UNTIL_DEFAULT,
)

revision = "0002_phase3_orders"
down_revision = "0001_phase1"
branch_labels = None
depends_on = None

SERVICE_TYPE_ROWS = (
    {"code": "sourcing", "min_total_quantity": None, "max_total_weight_kg": None},
    {"code": "importation", "min_total_quantity": 250, "max_total_weight_kg": Decimal("100.000")},
    {"code": "inspection", "min_total_quantity": None, "max_total_weight_kg": None},
    {"code": "auction", "min_total_quantity": None, "max_total_weight_kg": None},
)

NEW_PERMISSION_CODES = (
    "orders.create",
    "orders.read",
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
)

NEW_ROLE_PERMISSIONS = {
    "order_clerk": (
        "orders.create",
        "orders.update",
        "orders.read",
    ),
    "order_approver": (
        "orders.read_all",
        "orders.review",
        "orders.approve",
        "orders.reject",
    ),
    "fulfillment_operator": (
        "orders.assign",
        "orders.read",
    ),
    "identity_reviewer": (
        "identity.read",
        "identity.review",
        "identity.approve",
        "identity.reject",
    ),
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


def upgrade() -> None:
    op.create_table(
        "service_types",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("min_total_quantity", sa.Integer()),
        sa.Column("max_total_weight_kg", sa.Numeric(8, 3)),
        sa.CheckConstraint(CK_SERVICE_TYPES_CODE, name="ck_service_types_code"),
        sa.CheckConstraint(CK_SERVICE_TYPES_MIN_QUANTITY, name="ck_service_types_min_quantity"),
        sa.CheckConstraint(CK_SERVICE_TYPES_MAX_WEIGHT, name="ck_service_types_max_weight"),
    )
    op.create_table(
        "identity_verifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.BigInteger(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT", name="fk_identity_verifications_customer"),
            nullable=False,
        ),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expires_on", sa.Date()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column(
            "reviewed_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT", name="fk_identity_verifications_reviewer"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("id", "customer_id", name="uq_identity_id_customer"),
        sa.CheckConstraint(CK_IDENTITY_DOCUMENT_TYPE, name="ck_identity_document_type"),
        sa.CheckConstraint(CK_IDENTITY_STATUS, name="ck_identity_status"),
        sa.CheckConstraint(CK_IDENTITY_EXPIRY, name="ck_identity_expiry"),
        sa.CheckConstraint(CK_IDENTITY_REJECTION_REASON, name="ck_identity_rejection_reason"),
        sa.CheckConstraint(CK_IDENTITY_DECISION, name="ck_identity_decision"),
        sa.CheckConstraint(CK_IDENTITY_PENDING, name="ck_identity_pending"),
    )
    op.create_index("ix_identity_customer_created", "identity_verifications", ["customer_id", "created_at"])
    op.create_index(
        "uq_identity_one_pending",
        "identity_verifications",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending_review'"),
    )
    op.create_index(
        "uq_identity_one_approved",
        "identity_verifications",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.create_table(
        "identity_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "verification_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "identity_verifications.id",
                ondelete="RESTRICT",
                name="fk_identity_documents_verification",
            ),
            nullable=False,
        ),
        sa.Column("page_kind", sa.Text(), nullable=False),
        sa.Column("page_sequence", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("wrap_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("wrap_tag", sa.LargeBinary(), nullable=False),
        sa.Column("file_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("file_tag", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "retain_bytes_until",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(RETAIN_BYTES_UNTIL_DEFAULT),
        ),
        sa.Column("bytes_removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(CK_IDENTITY_PAGE_KIND, name="ck_identity_page_kind"),
        sa.CheckConstraint(CK_IDENTITY_PAGE_SEQUENCE, name="ck_identity_page_sequence"),
        sa.CheckConstraint(CK_IDENTITY_SHA256, name="ck_identity_sha256"),
        sa.CheckConstraint(CK_IDENTITY_CONTENT_TYPE, name="ck_identity_content_type"),
        sa.CheckConstraint(CK_IDENTITY_BYTE_SIZE, name="ck_identity_byte_size"),
        sa.CheckConstraint(CK_IDENTITY_ENCRYPTION, name="ck_identity_encryption"),
        sa.CheckConstraint(CK_IDENTITY_RETENTION, name="ck_identity_retention"),
        sa.CheckConstraint(CK_IDENTITY_BYTES_REMOVED, name="ck_identity_bytes_removed"),
        sa.UniqueConstraint("storage_key", name="uq_identity_documents_storage_key"),
        sa.UniqueConstraint(
            "verification_id",
            "page_kind",
            "page_sequence",
            name="uq_identity_document_page",
        ),
    )
    op.create_index("ix_identity_documents_verification", "identity_documents", ["verification_id"])
    op.create_index(
        "uq_identity_one_front",
        "identity_documents",
        ["verification_id"],
        unique=True,
        postgresql_where=sa.text("page_kind = 'front'"),
    )
    op.create_index(
        "uq_identity_one_back",
        "identity_documents",
        ["verification_id"],
        unique=True,
        postgresql_where=sa.text("page_kind = 'back'"),
    )
    op.create_table(
        "service_orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column(
            "customer_id",
            sa.BigInteger(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT", name="fk_service_orders_customer"),
            nullable=False,
        ),
        sa.Column(
            "entered_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT", name="fk_service_orders_entered_by"),
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "service_code",
            sa.Text(),
            sa.ForeignKey("service_types.code", ondelete="RESTRICT", name="fk_service_orders_service"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("identity_verification_id", sa.BigInteger()),
        sa.Column(
            "assigned_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT", name="fk_service_orders_assignee"),
        ),
        sa.Column("customer_notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("reply", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("waiting_return_status", sa.Text()),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["identity_verification_id", "customer_id"],
            ["identity_verifications.id", "identity_verifications.customer_id"],
            name="fk_service_orders_identity_customer",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(CK_SERVICE_ORDER_CHANNEL, name="ck_service_orders_channel"),
        sa.CheckConstraint(CK_SERVICE_ORDER_STATUS, name="ck_service_orders_status"),
        sa.CheckConstraint(CK_SERVICE_ORDER_VERSION, name="ck_service_orders_version"),
        sa.CheckConstraint(CK_SERVICE_ORDER_HASH, name="ck_service_orders_hash"),
        sa.CheckConstraint(CK_SERVICE_ORDER_DRAFT, name="ck_service_orders_draft"),
        sa.CheckConstraint(CK_SERVICE_ORDER_IDENTITY, name="ck_service_orders_identity"),
        sa.CheckConstraint(CK_SERVICE_ORDER_ACTOR, name="ck_service_orders_actor"),
        sa.CheckConstraint(CK_SERVICE_ORDER_WAITING, name="ck_service_orders_waiting"),
        sa.UniqueConstraint("ref", name="uq_service_orders_ref"),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="uq_order_idempotency"),
    )
    op.create_index(
        "ix_service_orders_customer_created",
        "service_orders",
        ["customer_id", "created_at"],
    )
    op.create_index("ix_service_orders_status", "service_orders", ["status", "created_at"])
    op.create_index(
        "ix_service_orders_assignee",
        "service_orders",
        ["assigned_employee_id", "status"],
    )
    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "service_order_id",
            sa.BigInteger(),
            sa.ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_items_order"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("product_url", sa.Text()),
        sa.Column("quantity", sa.Integer()),
        sa.Column("weight_kg", sa.Numeric(8, 3)),
        sa.Column("origin_country", sa.Text()),
        sa.Column("specification", sa.Text()),
        sa.Column("supplier_country", sa.Text()),
        sa.Column("supplier_address", sa.Text()),
        sa.Column("supplier_phone", sa.Text()),
        sa.Column("checklist", sa.Text()),
        sa.Column("bid_amount", sa.Numeric(12, 2)),
        sa.CheckConstraint(CK_ORDER_ITEM_POSITION, name="ck_order_items_position"),
        sa.CheckConstraint(CK_ORDER_ITEM_QUANTITY, name="ck_order_items_quantity"),
        sa.CheckConstraint(CK_ORDER_ITEM_WEIGHT, name="ck_order_items_weight"),
        sa.CheckConstraint(CK_ORDER_ITEM_BID, name="ck_order_items_bid"),
        sa.UniqueConstraint("service_order_id", "position", name="uq_order_items_position"),
    )
    op.create_table(
        "order_attachments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "service_order_id",
            sa.BigInteger(),
            sa.ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_attachments_order"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("wrap_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("wrap_tag", sa.LargeBinary(), nullable=False),
        sa.Column("file_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("file_tag", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT", name="fk_order_attachments_employee"),
        ),
        sa.Column(
            "created_by_customer_id",
            sa.BigInteger(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT", name="fk_order_attachments_customer"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("bytes_removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(CK_ORDER_ATTACHMENT_SHA256, name="ck_order_attachments_sha256"),
        sa.CheckConstraint(CK_ORDER_ATTACHMENT_CONTENT_TYPE, name="ck_order_attachments_content_type"),
        sa.CheckConstraint(CK_ORDER_ATTACHMENT_BYTE_SIZE, name="ck_order_attachments_byte_size"),
        sa.CheckConstraint(CK_ORDER_ATTACHMENT_ENCRYPTION, name="ck_order_attachments_encryption"),
        sa.CheckConstraint(CK_ORDER_ATTACHMENT_CREATOR, name="ck_order_attachments_creator"),
        sa.UniqueConstraint("storage_key", name="uq_order_attachments_storage_key"),
    )
    op.create_index("ix_order_attachments_order", "order_attachments", ["service_order_id"])
    op.create_table(
        "order_status_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "service_order_id",
            sa.BigInteger(),
            sa.ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_status_events_order"),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text()),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(CK_ORDER_EVENT_FROM_STATUS, name="ck_order_events_from_status"),
        sa.CheckConstraint(CK_ORDER_EVENT_TO_STATUS, name="ck_order_events_to_status"),
        sa.CheckConstraint(CK_ORDER_EVENT_ACTOR, name="ck_order_events_actor"),
        sa.CheckConstraint(CK_ORDER_EVENT_VERSION, name="ck_order_events_version"),
    )
    op.create_index(
        "ix_order_status_events_order_at",
        "order_status_events",
        ["service_order_id", "at"],
    )
    op.create_table(
        "order_assignments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "service_order_id",
            sa.BigInteger(),
            sa.ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_assignments_order"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT", name="fk_order_assignments_employee"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT", name="fk_order_assignments_assigned_by"),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("released_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_one_open_assignment",
        "order_assignments",
        ["service_order_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "service_order_id",
            sa.BigInteger(),
            sa.ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_notification_outbox_order"),
            nullable=False,
        ),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "service_credentials",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "replaces_credential_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "service_credentials.id",
                ondelete="RESTRICT",
                name="fk_service_credentials_replaces",
            ),
        ),
        sa.CheckConstraint(CK_SERVICE_CREDENTIAL_KEY, name="ck_service_credentials_key"),
        sa.CheckConstraint(CK_SERVICE_CREDENTIAL_ALGORITHM, name="ck_service_credentials_algorithm"),
        sa.CheckConstraint(CK_SERVICE_CREDENTIAL_SCOPE, name="ck_service_credentials_scope"),
        sa.UniqueConstraint("key_id", name="uq_service_credentials_key_id"),
    )
    op.create_table(
        "service_request_nonces",
        sa.Column(
            "credential_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "service_credentials.id",
                ondelete="CASCADE",
                name="fk_service_request_nonces_credential",
            ),
            primary_key=True,
        ),
        sa.Column("nonce", sa.Text(), primary_key=True),
        sa.Column("body_sha256", sa.Text(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(CK_SERVICE_NONCE, name="ck_service_nonces_nonce"),
        sa.CheckConstraint(CK_SERVICE_NONCE_HASH, name="ck_service_nonces_hash"),
    )
    _seed_reference_data()


def _seed_reference_data() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO service_types (code, min_total_quantity, max_total_weight_kg) "
            "VALUES (:code, :min_total_quantity, :max_total_weight_kg)"
        ),
        list(SERVICE_TYPE_ROWS),
    )
    connection.execute(
        sa.text("INSERT INTO roles (name) VALUES (:name)"),
        [{"name": name} for name in NEW_ROLE_PERMISSIONS],
    )
    connection.execute(
        sa.text("INSERT INTO permissions (code) VALUES (:code)"),
        [{"code": code} for code in NEW_PERMISSION_CODES],
    )
    roles = dict(connection.execute(sa.text("SELECT name, id FROM roles")).all())
    permissions = dict(connection.execute(sa.text("SELECT code, id FROM permissions")).all())
    rows = []
    for role_name, codes in NEW_ROLE_PERMISSIONS.items():
        for code in codes:
            rows.append({"role_id": roles[role_name], "permission_id": permissions[code]})
    connection.execute(
        sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"),
        rows,
    )


def _delete_in(sql: str, names: tuple[str, ...]) -> None:
    statement = sa.text(sql).bindparams(sa.bindparam("names", expanding=True))
    op.get_bind().execute(statement, {"names": list(names)})


def downgrade() -> None:
    op.drop_table("service_request_nonces")
    op.drop_table("service_credentials")
    op.drop_table("notification_outbox")
    op.drop_index("uq_one_open_assignment", table_name="order_assignments")
    op.drop_table("order_assignments")
    op.drop_index("ix_order_status_events_order_at", table_name="order_status_events")
    op.drop_table("order_status_events")
    op.drop_index("ix_order_attachments_order", table_name="order_attachments")
    op.drop_table("order_attachments")
    op.drop_table("order_items")
    op.drop_index("ix_service_orders_assignee", table_name="service_orders")
    op.drop_index("ix_service_orders_status", table_name="service_orders")
    op.drop_index("ix_service_orders_customer_created", table_name="service_orders")
    op.drop_table("service_orders")
    op.drop_index("uq_identity_one_back", table_name="identity_documents")
    op.drop_index("uq_identity_one_front", table_name="identity_documents")
    op.drop_index("ix_identity_documents_verification", table_name="identity_documents")
    op.drop_table("identity_documents")
    op.drop_index("uq_identity_one_approved", table_name="identity_verifications")
    op.drop_index("uq_identity_one_pending", table_name="identity_verifications")
    op.drop_index("ix_identity_customer_created", table_name="identity_verifications")
    op.drop_table("identity_verifications")
    op.drop_table("service_types")
    _delete_in(
        "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name IN :names)",
        tuple(NEW_ROLE_PERMISSIONS),
    )
    _delete_in("DELETE FROM roles WHERE name IN :names", tuple(NEW_ROLE_PERMISSIONS))
    _delete_in("DELETE FROM permissions WHERE code IN :names", NEW_PERMISSION_CODES)

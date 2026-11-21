"""Phase 1 schema: customers, employees, sessions, RBAC, orders, documents, site, audit.

Revision ID: 0001_phase1
Revises:
Create Date: 2026-11-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None

ROLE_PERMISSIONS = {
    "order_reviewer": (
        "orders.read_all",
        "orders.update_status",
        "orders.reply",
        "documents.read",
    ),
    "site_editor": ("site.write",),
    "operator": (
        "orders.delete",
        "whatsapp.read",
        "whatsapp.write",
        "audit.read",
    ),
}
PERMISSION_CODES = (
    "orders.read_all",
    "orders.update_status",
    "orders.reply",
    "orders.delete",
    "documents.read",
    "site.write",
    "whatsapp.read",
    "whatsapp.write",
    "audit.read",
)


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("email = lower(email)", name="ck_customers_email_lowercase"),
        sa.UniqueConstraint("email", name="uq_customers_email"),
    )
    op.create_table(
        "employees",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("email = lower(email)", name="ck_employees_email_lowercase"),
        sa.UniqueConstraint("email", name="uq_employees_email"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("principal_type", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id", ondelete="CASCADE")),
        sa.Column("employee_id", sa.BigInteger(), sa.ForeignKey("employees.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(principal_type = 'customer' AND customer_id IS NOT NULL AND employee_id IS NULL) "
            "OR (principal_type = 'employee' AND employee_id IS NOT NULL AND customer_id IS NULL)",
            name="ck_sessions_principal",
        ),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index(
        "ix_sessions_expires_at_open",
        "sessions",
        ["expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "permission_id",
            sa.BigInteger(),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "employee_roles",
        sa.Column(
            "employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id", ondelete="RESTRICT")),
        sa.Column(
            "entered_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("form", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("has_document", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(source = 'web' AND form IN ('sourcing', 'importation', 'inspection', 'auction') "
            "AND status IN ('Verified', 'Not verified') AND customer_id IS NOT NULL) "
            "OR (source = 'whatsapp_manual' AND form IS NULL "
            "AND status IN ('Nouveau', 'Confirmée', 'En préparation', 'Expédiée', 'Livrée', 'Annulée') "
            "AND entered_by_employee_id IS NOT NULL)",
            name="ck_orders_source_shape",
        ),
        sa.UniqueConstraint("ref", name="uq_orders_ref"),
    )
    op.create_index("ix_orders_customer_created", "orders", ["customer_id", "created_at"])
    op.create_index("ix_orders_source_status", "orders", ["source", "status"])
    op.create_index("ix_orders_form", "orders", ["form"])
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "created_by_customer_id",
            sa.BigInteger(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
        ),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True)),
        sa.Column("bytes_removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf')",
            name="ck_documents_content_type",
        ),
        sa.CheckConstraint(
            "byte_size >= 1 AND byte_size <= 1800000",
            name="ck_documents_byte_size",
        ),
        sa.CheckConstraint(
            "bytes_removed_at IS NULL OR deletion_requested_at IS NOT NULL",
            name="ck_documents_bytes_removed",
        ),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )
    op.create_index("ix_documents_order_id", "documents", ["order_id"])
    op.create_table(
        "site_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_by_employee_id",
            sa.BigInteger(),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint("id = 1", name="ck_site_settings_id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.BigInteger()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text(), nullable=False),
        sa.Column("object_id", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "actor_type IN ('customer', 'employee', 'anonymous')",
            name="ck_audit_logs_actor_type",
        ),
    )
    op.create_index("ix_audit_logs_at", "audit_logs", ["at"])
    op.create_index("ix_audit_logs_object", "audit_logs", ["object_type", "object_id"])
    _seed_roles()


def _seed_roles() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("INSERT INTO roles (name) VALUES (:name)"),
        [{"name": name} for name in ROLE_PERMISSIONS],
    )
    connection.execute(
        sa.text("INSERT INTO permissions (code) VALUES (:code)"),
        [{"code": code} for code in PERMISSION_CODES],
    )
    roles = dict(connection.execute(sa.text("SELECT name, id FROM roles")).all())
    permissions = dict(connection.execute(sa.text("SELECT code, id FROM permissions")).all())
    rows = []
    for role_name, codes in ROLE_PERMISSIONS.items():
        for code in codes:
            rows.append({"role_id": roles[role_name], "permission_id": permissions[code]})
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"
        ),
        rows,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_object", table_name="audit_logs")
    op.drop_index("ix_audit_logs_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("site_settings")
    op.drop_index("ix_documents_order_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_orders_form", table_name="orders")
    op.drop_index("ix_orders_source_status", table_name="orders")
    op.drop_index("ix_orders_customer_created", table_name="orders")
    op.drop_table("orders")
    op.drop_table("employee_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_index("ix_sessions_expires_at_open", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("employees")
    op.drop_table("customers")

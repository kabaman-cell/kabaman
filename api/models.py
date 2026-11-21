"""SQLAlchemy 2.0 schema for revision 0001_phase1. No connections are opened here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MAX_DOCUMENT_BYTES = 1_800_000


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_customers_email_lowercase"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    orders: Mapped[list[Order]] = relationship(back_populates="customer")
    sessions: Mapped[list[Session]] = relationship(back_populates="customer")
    documents: Mapped[list[Document]] = relationship(back_populates="created_by")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_employees_email_lowercase"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    orders_entered: Mapped[list[Order]] = relationship(back_populates="entered_by")
    sessions: Mapped[list[Session]] = relationship(back_populates="employee")
    role_links: Mapped[list[EmployeeRole]] = relationship(back_populates="employee")
    site_edits: Mapped[list[SiteSetting]] = relationship(back_populates="updated_by")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "(principal_type = 'customer' AND customer_id IS NOT NULL AND employee_id IS NULL) "
            "OR (principal_type = 'employee' AND employee_id IS NOT NULL AND customer_id IS NULL)",
            name="ck_sessions_principal",
        ),
        Index(
            "ix_sessions_expires_at_open",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    principal_type: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE")
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer | None] = relationship(back_populates="sessions")
    employee: Mapped[Employee | None] = relationship(back_populates="sessions")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    permission_links: Mapped[list[RolePermission]] = relationship(back_populates="role")
    employee_links: Mapped[list[EmployeeRole]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    role_links: Mapped[list[RolePermission]] = relationship(back_populates="permission")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role: Mapped[Role] = relationship(back_populates="permission_links")
    permission: Mapped[Permission] = relationship(back_populates="role_links")


class EmployeeRole(Base):
    __tablename__ = "employee_roles"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )

    employee: Mapped[Employee] = relationship(back_populates="role_links")
    role: Mapped[Role] = relationship(back_populates="employee_links")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "(source = 'web' AND form IN ('sourcing', 'importation', 'inspection', 'auction') "
            "AND status IN ('Verified', 'Not verified') AND customer_id IS NOT NULL) "
            "OR (source = 'whatsapp_manual' AND form IS NULL "
            "AND status IN ('Nouveau', 'Confirmée', 'En préparation', 'Expédiée', 'Livrée', 'Annulée') "
            "AND entered_by_employee_id IS NOT NULL)",
            name="ck_orders_source_shape",
        ),
        Index("ix_orders_customer_created", "customer_id", "created_at"),
        Index("ix_orders_source_status", "source", "status"),
        Index("ix_orders_form", "form"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ref: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT")
    )
    entered_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    form: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reply: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    has_document: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    customer: Mapped[Customer | None] = relationship(back_populates="orders")
    entered_by: Mapped[Employee | None] = relationship(back_populates="orders_entered")
    documents: Mapped[list[Document]] = relationship(back_populates="order")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf')",
            name="ck_documents_content_type",
        ),
        CheckConstraint(
            "byte_size >= 1 AND byte_size <= %d" % MAX_DOCUMENT_BYTES,
            name="ck_documents_byte_size",
        ),
        CheckConstraint(
            "bytes_removed_at IS NULL OR deletion_requested_at IS NOT NULL",
            name="ck_documents_bytes_removed",
        ),
        Index("ix_documents_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT")
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bytes_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="documents")
    created_by: Mapped[Customer | None] = relationship(back_populates="documents")


class SiteSetting(Base):
    __tablename__ = "site_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_site_settings_id"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )

    updated_by: Mapped[Employee | None] = relationship(back_populates="site_edits")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('customer', 'employee', 'anonymous')",
            name="ck_audit_logs_actor_type",
        ),
        Index("ix_audit_logs_at", "at"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

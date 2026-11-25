"""SQLAlchemy 2.0 schema for revisions 0001_phase1 and 0002_phase3_orders.

No connections are opened here. Revision 0002 adds Phase 3 tables only.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MAX_DOCUMENT_BYTES = 1_800_000
MAX_SERVICE_ORDER_ITEMS = 20
# The later order engine rejects an order with more lines than this. No table check counts child rows.
ORDER_ITEM_LIMIT_ENFORCED_BY = "order_engine"
IDENTITY_BYTE_RETENTION_DAYS = 365
WHATSAPP_SIGNATURE_WINDOW_SECONDS = 600
WHATSAPP_NONCE_RETENTION_SECONDS = 15 * 60

SERVICE_CODES = ("sourcing", "importation", "inspection", "auction")
SERVICE_ORDER_STATUSES = (
    "draft",
    "new",
    "under_review",
    "waiting_for_customer",
    "approved",
    "rejected",
    "in_progress",
    "completed",
    "cancelled",
)
_STATUS_SQL = ", ".join("'%s'" % status for status in SERVICE_ORDER_STATUSES)
_SERVICE_SQL = ", ".join("'%s'" % code for code in SERVICE_CODES)
_MIME_SQL = "'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'"
_SHA256_SQL = "sha256 ~ '^[0-9a-f]{64}$'"
_ENCRYPTION_SQL = (
    "key_version >= 1 "
    "AND octet_length(wrap_nonce) = 12 AND octet_length(wrap_tag) = 16 "
    "AND octet_length(file_nonce) = 12 AND octet_length(file_tag) = 16"
)
RETAIN_BYTES_UNTIL_DEFAULT = "now() + interval '%d days'" % IDENTITY_BYTE_RETENTION_DAYS

CK_SERVICE_TYPES_CODE = "code IN (%s)" % _SERVICE_SQL
CK_SERVICE_TYPES_MIN_QUANTITY = "min_total_quantity IS NULL OR min_total_quantity >= 1"
CK_SERVICE_TYPES_MAX_WEIGHT = "max_total_weight_kg IS NULL OR max_total_weight_kg > 0"
CK_IDENTITY_DOCUMENT_TYPE = "document_type IN ('national_id', 'passport', 'driving_license')"
CK_IDENTITY_STATUS = "status IN ('pending_review', 'approved', 'rejected', 'expired', 'superseded')"
CK_IDENTITY_EXPIRY = (
    "(document_type = 'national_id' AND expires_on IS NULL) "
    "OR (document_type IN ('passport', 'driving_license') AND expires_on IS NOT NULL)"
)
CK_IDENTITY_REJECTION_REASON = "status <> 'rejected' OR length(btrim(rejection_reason)) > 0"
CK_IDENTITY_DECISION = (
    "status NOT IN ('approved', 'rejected') "
    "OR (reviewed_by_employee_id IS NOT NULL AND reviewed_at IS NOT NULL)"
)
CK_IDENTITY_PENDING = (
    "status <> 'pending_review' OR ("
    "reviewed_by_employee_id IS NULL AND reviewed_at IS NULL AND rejection_reason IS NULL)"
)
CK_IDENTITY_PAGE_KIND = "page_kind IN ('front', 'back', 'extra')"
CK_IDENTITY_PAGE_SEQUENCE = "page_sequence >= 1 AND (page_kind = 'extra' OR page_sequence = 1)"
CK_IDENTITY_SHA256 = _SHA256_SQL
CK_IDENTITY_CONTENT_TYPE = "content_type IN (%s)" % _MIME_SQL
CK_IDENTITY_BYTE_SIZE = "byte_size >= 1 AND byte_size <= %d" % MAX_DOCUMENT_BYTES
CK_IDENTITY_ENCRYPTION = _ENCRYPTION_SQL
CK_IDENTITY_RETENTION = "retain_bytes_until >= created_at"
CK_IDENTITY_BYTES_REMOVED = "bytes_removed_at IS NULL OR bytes_removed_at >= retain_bytes_until"
CK_SERVICE_ORDER_CHANNEL = "channel IN ('staff', 'customer_portal', 'whatsapp')"
CK_SERVICE_ORDER_STATUS = "status IN (%s)" % _STATUS_SQL
CK_SERVICE_ORDER_VERSION = "version >= 1"
CK_SERVICE_ORDER_HASH = "request_hash ~ '^[0-9a-f]{64}$'"
CK_SERVICE_ORDER_DRAFT = "status <> 'draft' OR channel = 'staff'"
CK_SERVICE_ORDER_IDENTITY = "status = 'draft' OR identity_verification_id IS NOT NULL"
CK_SERVICE_ORDER_ACTOR = (
    "(channel = 'staff' AND entered_by_employee_id IS NOT NULL) "
    "OR (channel = 'whatsapp' AND entered_by_employee_id IS NULL) "
    "OR channel = 'customer_portal'"
)
CK_SERVICE_ORDER_WAITING = (
    "(status = 'waiting_for_customer' AND waiting_return_status IN ('under_review', 'in_progress')) "
    "OR (status <> 'waiting_for_customer' AND waiting_return_status IS NULL)"
)
CK_ORDER_ITEM_POSITION = "position >= 1"
CK_ORDER_ITEM_QUANTITY = "quantity IS NULL OR quantity >= 1"
CK_ORDER_ITEM_WEIGHT = "weight_kg IS NULL OR weight_kg > 0"
CK_ORDER_ITEM_BID = "bid_amount IS NULL OR bid_amount > 0"
CK_ORDER_ATTACHMENT_SHA256 = _SHA256_SQL
CK_ORDER_ATTACHMENT_CONTENT_TYPE = "content_type IN (%s)" % _MIME_SQL
CK_ORDER_ATTACHMENT_BYTE_SIZE = "byte_size >= 1 AND byte_size <= %d" % MAX_DOCUMENT_BYTES
CK_ORDER_ATTACHMENT_ENCRYPTION = _ENCRYPTION_SQL
CK_ORDER_ATTACHMENT_CREATOR = (
    "(created_by_employee_id IS NOT NULL AND created_by_customer_id IS NULL) "
    "OR (created_by_employee_id IS NULL AND created_by_customer_id IS NOT NULL)"
)
CK_ORDER_EVENT_FROM_STATUS = "from_status IS NULL OR from_status IN (%s)" % _STATUS_SQL
CK_ORDER_EVENT_TO_STATUS = "to_status IN (%s)" % _STATUS_SQL
CK_ORDER_EVENT_ACTOR = "actor_type IN ('employee', 'customer', 'service')"
CK_ORDER_EVENT_VERSION = "version >= 1"
CK_SERVICE_CREDENTIAL_KEY = "octet_length(public_key) = 32"
CK_SERVICE_CREDENTIAL_ALGORITHM = "algorithm = 'ed25519'"
CK_SERVICE_CREDENTIAL_SCOPE = "scope = 'whatsapp.order_intake'"
CK_SERVICE_NONCE = "nonce ~ '^[A-Za-z0-9_-]{22}$'"
CK_SERVICE_NONCE_HASH = "body_sha256 ~ '^[0-9a-f]{64}$'"


def next_identity_page_sequence(existing_sequences: list[int]) -> int:
    """Choose the next page sequence after the verification row is locked.

    Callers that read the same snapshot choose the same number. The unique key
    uq_identity_document_page rejects the insert that loses that race.
    """
    if any(isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1 for sequence in existing_sequences):
        raise ValueError("page sequence must be an integer of at least 1")
    if not existing_sequences:
        return 1
    return max(existing_sequences) + 1


def _whole_seconds(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("time must be a whole number of seconds")


def whatsapp_timestamp_accepted(server_time: int, signed_timestamp: int) -> bool:
    """Reject a future timestamp. Accept only the past 600 seconds, including now.

    A symmetric window would let a timestamp 600 seconds ahead remain valid for
    600 seconds after that, which is 1,200 seconds after the nonce is stored.
    Nonce retention is 900 seconds, so that future timestamp would become
    replayable. Future timestamps are therefore refused.
    """
    _whole_seconds(server_time)
    _whole_seconds(signed_timestamp)
    skew = server_time - signed_timestamp
    return 0 <= skew <= WHATSAPP_SIGNATURE_WINDOW_SECONDS


def whatsapp_nonce_deleted_at(accepted_at: int, checked_at: int) -> bool:
    """A nonce row is removed once it is at least 15 minutes old."""
    _whole_seconds(accepted_at)
    _whole_seconds(checked_at)
    if checked_at < accepted_at:
        raise ValueError("cleanup is checked after the nonce is stored")
    return checked_at - accepted_at >= WHATSAPP_NONCE_RETENTION_SECONDS


def whatsapp_accepted_request_replayable_after_cleanup(
    accepted_at: int,
    signed_timestamp: int,
    checked_at: int,
) -> bool:
    """True when an already accepted signature is still valid and its nonce is gone."""
    if not whatsapp_timestamp_accepted(accepted_at, signed_timestamp):
        raise ValueError("the request was not accepted")
    _whole_seconds(checked_at)
    if checked_at < accepted_at:
        raise ValueError("replay is checked after acceptance")
    return whatsapp_timestamp_accepted(checked_at, signed_timestamp) and whatsapp_nonce_deleted_at(
        accepted_at,
        checked_at,
    )


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_customers_email_lowercase"),
        UniqueConstraint("email", name="uq_customers_email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
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
    identity_verifications: Mapped[list[IdentityVerification]] = relationship(back_populates="customer")
    service_orders: Mapped[list[ServiceOrder]] = relationship(
        back_populates="customer",
        foreign_keys="ServiceOrder.customer_id",
    )
    order_attachments: Mapped[list[OrderAttachment]] = relationship(back_populates="created_by_customer")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_employees_email_lowercase"),
        UniqueConstraint("email", name="uq_employees_email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
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
    identity_reviews: Mapped[list[IdentityVerification]] = relationship(back_populates="reviewed_by")
    service_orders_entered: Mapped[list[ServiceOrder]] = relationship(
        back_populates="entered_by",
        foreign_keys="ServiceOrder.entered_by_employee_id",
    )
    service_orders_assigned: Mapped[list[ServiceOrder]] = relationship(
        back_populates="assigned_employee",
        foreign_keys="ServiceOrder.assigned_employee_id",
    )
    assignments_received: Mapped[list[OrderAssignment]] = relationship(
        back_populates="employee",
        foreign_keys="OrderAssignment.employee_id",
    )
    assignments_made: Mapped[list[OrderAssignment]] = relationship(
        back_populates="assigned_by",
        foreign_keys="OrderAssignment.assigned_by_employee_id",
    )
    order_attachments: Mapped[list[OrderAttachment]] = relationship(back_populates="created_by_employee")


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
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
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
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    permission_links: Mapped[list[RolePermission]] = relationship(back_populates="role")
    employee_links: Mapped[list[EmployeeRole]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permissions_code"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)

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
        UniqueConstraint("ref", name="uq_orders_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
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
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
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

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
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


class ServiceType(Base):
    """Order-total limits only. Field requirements stay in the order engine."""

    __tablename__ = "service_types"
    __table_args__ = (
        CheckConstraint(CK_SERVICE_TYPES_CODE, name="ck_service_types_code"),
        CheckConstraint(CK_SERVICE_TYPES_MIN_QUANTITY, name="ck_service_types_min_quantity"),
        CheckConstraint(CK_SERVICE_TYPES_MAX_WEIGHT, name="ck_service_types_max_weight"),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    min_total_quantity: Mapped[int | None] = mapped_column(Integer)
    max_total_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))

    service_orders: Mapped[list[ServiceOrder]] = relationship(back_populates="service_type")


class IdentityVerification(Base):
    """One identity decision for a customer. Rows remain after document bytes are removed."""

    __tablename__ = "identity_verifications"
    __table_args__ = (
        UniqueConstraint("id", "customer_id", name="uq_identity_id_customer"),
        CheckConstraint(CK_IDENTITY_DOCUMENT_TYPE, name="ck_identity_document_type"),
        CheckConstraint(CK_IDENTITY_STATUS, name="ck_identity_status"),
        CheckConstraint(CK_IDENTITY_EXPIRY, name="ck_identity_expiry"),
        CheckConstraint(CK_IDENTITY_REJECTION_REASON, name="ck_identity_rejection_reason"),
        CheckConstraint(CK_IDENTITY_DECISION, name="ck_identity_decision"),
        CheckConstraint(CK_IDENTITY_PENDING, name="ck_identity_pending"),
        Index("ix_identity_customer_created", "customer_id", "created_at"),
        Index(
            "uq_identity_one_pending",
            "customer_id",
            unique=True,
            postgresql_where=text("status = 'pending_review'"),
        ),
        Index(
            "uq_identity_one_approved",
            "customer_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT", name="fk_identity_verifications_customer"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_identity_verifications_reviewer")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    customer: Mapped[Customer] = relationship(back_populates="identity_verifications")
    reviewed_by: Mapped[Employee | None] = relationship(back_populates="identity_reviews")
    documents: Mapped[list[IdentityDocument]] = relationship(back_populates="verification")
    service_orders: Mapped[list[ServiceOrder]] = relationship(
        back_populates="identity_verification",
        foreign_keys="[ServiceOrder.identity_verification_id, ServiceOrder.customer_id]",
        viewonly=True,
    )


class IdentityDocument(Base):
    """Private identity-file metadata. Ciphertext stays outside PostgreSQL.

    Several extra pages may belong to one verification. Front and back remain
    single pages. Sequence assignment locks the verification and uses
    next_identity_page_sequence for that page kind.
    """

    __tablename__ = "identity_documents"
    __table_args__ = (
        CheckConstraint(CK_IDENTITY_PAGE_KIND, name="ck_identity_page_kind"),
        CheckConstraint(CK_IDENTITY_PAGE_SEQUENCE, name="ck_identity_page_sequence"),
        CheckConstraint(CK_IDENTITY_SHA256, name="ck_identity_sha256"),
        CheckConstraint(CK_IDENTITY_CONTENT_TYPE, name="ck_identity_content_type"),
        CheckConstraint(CK_IDENTITY_BYTE_SIZE, name="ck_identity_byte_size"),
        CheckConstraint(CK_IDENTITY_ENCRYPTION, name="ck_identity_encryption"),
        CheckConstraint(CK_IDENTITY_RETENTION, name="ck_identity_retention"),
        CheckConstraint(CK_IDENTITY_BYTES_REMOVED, name="ck_identity_bytes_removed"),
        UniqueConstraint("storage_key", name="uq_identity_documents_storage_key"),
        UniqueConstraint(
            "verification_id",
            "page_kind",
            "page_sequence",
            name="uq_identity_document_page",
        ),
        Index("ix_identity_documents_verification", "verification_id"),
        Index(
            "uq_identity_one_front",
            "verification_id",
            unique=True,
            postgresql_where=text("page_kind = 'front'"),
        ),
        Index(
            "uq_identity_one_back",
            "verification_id",
            unique=True,
            postgresql_where=text("page_kind = 'back'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey(
            "identity_verifications.id",
            ondelete="RESTRICT",
            name="fk_identity_documents_verification",
        ),
        nullable=False,
    )
    page_kind: Mapped[str] = mapped_column(Text, nullable=False)
    page_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrap_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrap_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    retain_bytes_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text(RETAIN_BYTES_UNTIL_DEFAULT),
    )
    bytes_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    verification: Mapped[IdentityVerification] = relationship(back_populates="documents")


class ServiceOrder(Base):
    """Phase 3 order header. It has no foreign key to the legacy orders table."""

    __tablename__ = "service_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["identity_verification_id", "customer_id"],
            ["identity_verifications.id", "identity_verifications.customer_id"],
            name="fk_service_orders_identity_customer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(CK_SERVICE_ORDER_CHANNEL, name="ck_service_orders_channel"),
        CheckConstraint(CK_SERVICE_ORDER_STATUS, name="ck_service_orders_status"),
        CheckConstraint(CK_SERVICE_ORDER_VERSION, name="ck_service_orders_version"),
        CheckConstraint(CK_SERVICE_ORDER_HASH, name="ck_service_orders_hash"),
        CheckConstraint(CK_SERVICE_ORDER_DRAFT, name="ck_service_orders_draft"),
        CheckConstraint(CK_SERVICE_ORDER_IDENTITY, name="ck_service_orders_identity"),
        CheckConstraint(CK_SERVICE_ORDER_ACTOR, name="ck_service_orders_actor"),
        CheckConstraint(CK_SERVICE_ORDER_WAITING, name="ck_service_orders_waiting"),
        UniqueConstraint("ref", name="uq_service_orders_ref"),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_order_idempotency"),
        Index("ix_service_orders_customer_created", "customer_id", "created_at"),
        Index("ix_service_orders_status", "status", "created_at"),
        Index("ix_service_orders_assignee", "assigned_employee_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT", name="fk_service_orders_customer"),
        nullable=False,
    )
    entered_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_service_orders_entered_by")
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    service_code: Mapped[str] = mapped_column(
        ForeignKey("service_types.code", ondelete="RESTRICT", name="fk_service_orders_service"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    identity_verification_id: Mapped[int | None] = mapped_column(BigInteger)
    assigned_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_service_orders_assignee")
    )
    customer_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    reply: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    waiting_return_status: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    customer: Mapped[Customer] = relationship(
        back_populates="service_orders",
        foreign_keys=[customer_id],
    )
    entered_by: Mapped[Employee | None] = relationship(
        back_populates="service_orders_entered",
        foreign_keys=[entered_by_employee_id],
    )
    assigned_employee: Mapped[Employee | None] = relationship(
        back_populates="service_orders_assigned",
        foreign_keys=[assigned_employee_id],
    )
    service_type: Mapped[ServiceType] = relationship(back_populates="service_orders")
    identity_verification: Mapped[IdentityVerification | None] = relationship(
        back_populates="service_orders",
        primaryjoin=(
            "and_(ServiceOrder.identity_verification_id == IdentityVerification.id, "
            "ServiceOrder.customer_id == IdentityVerification.customer_id)"
        ),
        foreign_keys=[identity_verification_id, customer_id],
        viewonly=True,
    )
    items: Mapped[list[OrderItem]] = relationship(back_populates="service_order")
    attachments: Mapped[list[OrderAttachment]] = relationship(back_populates="service_order")
    status_events: Mapped[list[OrderStatusEvent]] = relationship(back_populates="service_order")
    assignments: Mapped[list[OrderAssignment]] = relationship(back_populates="service_order")
    notifications: Mapped[list[NotificationOutbox]] = relationship(back_populates="service_order")


class OrderItem(Base):
    """One product line.

    MAX_SERVICE_ORDER_ITEMS is enforced by the later order engine. This table
    does not count sibling rows.
    """

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(CK_ORDER_ITEM_POSITION, name="ck_order_items_position"),
        CheckConstraint(CK_ORDER_ITEM_QUANTITY, name="ck_order_items_quantity"),
        CheckConstraint(CK_ORDER_ITEM_WEIGHT, name="ck_order_items_weight"),
        CheckConstraint(CK_ORDER_ITEM_BID, name="ck_order_items_bid"),
        UniqueConstraint("service_order_id", "position", name="uq_order_items_position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_order_id: Mapped[int] = mapped_column(
        ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_items_order"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    product_url: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    origin_country: Mapped[str | None] = mapped_column(Text)
    specification: Mapped[str | None] = mapped_column(Text)
    supplier_country: Mapped[str | None] = mapped_column(Text)
    supplier_address: Mapped[str | None] = mapped_column(Text)
    supplier_phone: Mapped[str | None] = mapped_column(Text)
    checklist: Mapped[str | None] = mapped_column(Text)
    bid_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    service_order: Mapped[ServiceOrder] = relationship(back_populates="items")


class OrderAttachment(Base):
    """Product-file metadata. These rows are not identity documents."""

    __tablename__ = "order_attachments"
    __table_args__ = (
        CheckConstraint(CK_ORDER_ATTACHMENT_SHA256, name="ck_order_attachments_sha256"),
        CheckConstraint(CK_ORDER_ATTACHMENT_CONTENT_TYPE, name="ck_order_attachments_content_type"),
        CheckConstraint(CK_ORDER_ATTACHMENT_BYTE_SIZE, name="ck_order_attachments_byte_size"),
        CheckConstraint(CK_ORDER_ATTACHMENT_ENCRYPTION, name="ck_order_attachments_encryption"),
        CheckConstraint(CK_ORDER_ATTACHMENT_CREATOR, name="ck_order_attachments_creator"),
        UniqueConstraint("storage_key", name="uq_order_attachments_storage_key"),
        Index("ix_order_attachments_order", "service_order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_order_id: Mapped[int] = mapped_column(
        ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_attachments_order"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    key_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrap_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrap_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_order_attachments_employee")
    )
    created_by_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT", name="fk_order_attachments_customer")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    bytes_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_order: Mapped[ServiceOrder] = relationship(back_populates="attachments")
    created_by_employee: Mapped[Employee | None] = relationship(back_populates="order_attachments")
    created_by_customer: Mapped[Customer | None] = relationship(back_populates="order_attachments")


class OrderStatusEvent(Base):
    """Append-only status history. actor_id is not a foreign key because actors differ."""

    __tablename__ = "order_status_events"
    __table_args__ = (
        CheckConstraint(CK_ORDER_EVENT_FROM_STATUS, name="ck_order_events_from_status"),
        CheckConstraint(CK_ORDER_EVENT_TO_STATUS, name="ck_order_events_to_status"),
        CheckConstraint(CK_ORDER_EVENT_ACTOR, name="ck_order_events_actor"),
        CheckConstraint(CK_ORDER_EVENT_VERSION, name="ck_order_events_version"),
        Index("ix_order_status_events_order_at", "service_order_id", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_order_id: Mapped[int] = mapped_column(
        ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_status_events_order"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    service_order: Mapped[ServiceOrder] = relationship(back_populates="status_events")


class OrderAssignment(Base):
    """Assignment history. At most one row per order has released_at null."""

    __tablename__ = "order_assignments"
    __table_args__ = (
        Index(
            "uq_one_open_assignment",
            "service_order_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_order_id: Mapped[int] = mapped_column(
        ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_order_assignments_order"),
        nullable=False,
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_order_assignments_employee"),
        nullable=False,
    )
    assigned_by_employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_order_assignments_assigned_by"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_order: Mapped[ServiceOrder] = relationship(back_populates="assignments")
    employee: Mapped[Employee] = relationship(
        back_populates="assignments_received",
        foreign_keys=[employee_id],
    )
    assigned_by: Mapped[Employee] = relationship(
        back_populates="assignments_made",
        foreign_keys=[assigned_by_employee_id],
    )


class NotificationOutbox(Base):
    """Queued notification intent. Phase 3 inserts rows and does not send them."""

    __tablename__ = "notification_outbox"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    service_order_id: Mapped[int] = mapped_column(
        ForeignKey("service_orders.id", ondelete="RESTRICT", name="fk_notification_outbox_order"),
        nullable=False,
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_order: Mapped[ServiceOrder] = relationship(back_populates="notifications")


class ServiceCredential(Base):
    """WhatsApp public key. The private key is never a column."""

    __tablename__ = "service_credentials"
    __table_args__ = (
        CheckConstraint(CK_SERVICE_CREDENTIAL_KEY, name="ck_service_credentials_key"),
        CheckConstraint(CK_SERVICE_CREDENTIAL_ALGORITHM, name="ck_service_credentials_algorithm"),
        CheckConstraint(CK_SERVICE_CREDENTIAL_SCOPE, name="ck_service_credentials_scope"),
        UniqueConstraint("key_id", name="uq_service_credentials_key_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaces_credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_credentials.id", ondelete="RESTRICT", name="fk_service_credentials_replaces")
    )

    replaced: Mapped[ServiceCredential | None] = relationship(
        remote_side=[id],
        foreign_keys=[replaces_credential_id],
    )
    nonces: Mapped[list[ServiceRequestNonce]] = relationship(back_populates="credential")


class ServiceRequestNonce(Base):
    """One accepted WhatsApp nonce. The primary key rejects a repeated pair.

    The signature clock rejects future timestamps, so an accepted signature
    expires at most 600 seconds after the nonce is stored. Cleanup removes the
    row only at 900 seconds, after that signature has expired.
    """

    __tablename__ = "service_request_nonces"
    __table_args__ = (
        CheckConstraint(CK_SERVICE_NONCE, name="ck_service_nonces_nonce"),
        CheckConstraint(CK_SERVICE_NONCE_HASH, name="ck_service_nonces_hash"),
    )

    credential_id: Mapped[int] = mapped_column(
        ForeignKey(
            "service_credentials.id",
            ondelete="CASCADE",
            name="fk_service_request_nonces_credential",
        ),
        primary_key=True,
    )
    nonce: Mapped[str] = mapped_column(Text, primary_key=True)
    body_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    credential: Mapped[ServiceCredential] = relationship(back_populates="nonces")

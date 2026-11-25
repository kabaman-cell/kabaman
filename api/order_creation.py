"""Staff order creation for Phase 3C stage 2.

Transactions, in order, each with its own commit:

1. Authorize the employee and the customer. This read does not look up an order.
2. After validation and hashing, look up a committed order by customer and
   idempotency key. A match returns that order. A different hash returns 409.
3. When a new submitted order needs an identity, expire a past passport or
   driving license in its own transaction and commit that change.
4. Create the order in a later transaction. A rollback here does not undo the
   expiry commit.

National ID is never expired by date. This module does not deliver outbox
mail, accept WhatsApp credentials, or open a connection except through the
guarded session.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.deps import employee_permission_codes
from api.models import (
    AuditLog,
    Customer,
    Employee,
    IdentityDocument,
    IdentityVerification,
    OrderItem,
    OrderStatusEvent,
    ServiceOrder,
)
from api.order_validation import (
    SUBMISSION_DRAFT,
    SUBMISSION_SUBMIT,
    OrderValidationError,
    OrderValidationFailure,
    ValidatedOrderRequest,
    validate_order_request,
)
from api.security import session_scope

_CREATE_PERMISSION = "orders.create"
_DATE_LIMITED_DOCUMENTS = frozenset({"passport", "driving_license"})

_MESSAGES = {
    "unauthenticated": (401, "Sign in to continue."),
    "forbidden": (403, "You do not have permission to do that."),
    "not_found": (404, "That order was not found."),
    "idempotency_key_required": (422, "Provide an idempotency key."),
    "idempotency_conflict": (409, "This idempotency key was already used with a different request."),
    "identity_required": (422, "Identity verification is required before this order."),
    "identity_expired": (403, "This identity document has expired."),
    "identity_unavailable": (403, "Submit a new identity document before ordering."),
    "invalid_request": (422, "The request is invalid."),
}


class _Rollback(Exception):
    def __init__(self, failure: OrderCreateFailure) -> None:
        self.failure = failure


@dataclass(frozen=True)
class OrderCreateFailure:
    status: int
    code: str
    error: str


@dataclass(frozen=True)
class OrderCreateResult:
    order_id: int
    created: bool
    customer_id: int
    status: str
    request_hash: str
    identity_verification_id: int | None
    ref: str
    version: int
    channel: str


def identity_date_valid(document_type: str, expires_on: date | None, today: date) -> bool:
    """National ID does not expire by date. Passport and license must still be in date."""
    if document_type == "national_id":
        return True
    if document_type not in _DATE_LIMITED_DOCUMENTS:
        return False
    expires = _as_date(expires_on)
    return expires is not None and expires >= today


def identity_expired_by_date(document_type: str, expires_on: date | None, today: date) -> bool:
    """True only when a passport or driving license date is before today."""
    if document_type == "national_id" or document_type not in _DATE_LIMITED_DOCUMENTS:
        return False
    expires = _as_date(expires_on)
    return expires is not None and expires < today


def idempotency_outcome(existing_hash: str | None, request_hash: str) -> str:
    """Classify a committed key as absent, replay, or conflict."""
    if existing_hash is None:
        return "absent"
    if existing_hash == request_hash:
        return "replay"
    return "conflict"


def create_staff_order(
    *,
    employee_id: int,
    customer_id: int,
    idempotency_key: str,
    service_code: str,
    submit: bool,
    items: Sequence[Mapping[str, Any]],
    customer_notes: str | None = None,
) -> OrderCreateResult | OrderCreateFailure:
    """Create one staff order or return the committed order for the same request."""
    authorized = _run(lambda db: _authorize(db, employee_id, customer_id))
    if isinstance(authorized, OrderCreateFailure):
        return authorized
    if not isinstance(idempotency_key, str) or idempotency_key.strip() == "":
        return _failure("idempotency_key_required")
    try:
        validated = validate_order_request(
            customer_id=customer_id,
            service_code=service_code,
            channel="staff",
            submit=submit,
            items=items,
            customer_notes=customer_notes,
        )
    except OrderValidationError:
        return _failure("invalid_request")
    if isinstance(validated, OrderValidationFailure):
        return OrderCreateFailure(422, validated.code, validated.error)

    replay = _run(lambda db: _lookup_committed(db, employee_id, customer_id, idempotency_key, validated.request_hash))
    if replay is not None:
        return replay
    if validated.submission_intent == SUBMISSION_SUBMIT:
        expired = _run(lambda db: _commit_identity_expiry(db, employee_id, customer_id))
        if isinstance(expired, OrderCreateFailure):
            return expired
    _before_order_transaction()
    return _run(
        lambda db: _create_order_row(
            db,
            employee_id=employee_id,
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            validated=validated,
        )
    )


def _before_order_transaction() -> None:
    """No-op seam. A test may commit another order here, after lookup and expiry."""


def _run(work):
    try:
        with session_scope() as db:
            result = work(db)
            if isinstance(result, OrderCreateFailure):
                raise _Rollback(result)
            return result
    except _Rollback as exc:
        return exc.failure


def _failure(code: str) -> OrderCreateFailure:
    status, error = _MESSAGES[code]
    return OrderCreateFailure(status=status, code=code, error=error)


def _authorize(db: Session, employee_id: int, customer_id: int) -> OrderCreateFailure | None:
    employee = _locked_employee(db, employee_id)
    if isinstance(employee, OrderCreateFailure):
        return employee
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    if customer is None:
        return _failure("not_found")
    return None


def _lookup_committed(
    db: Session,
    employee_id: int,
    customer_id: int,
    idempotency_key: str,
    request_hash: str,
) -> OrderCreateResult | OrderCreateFailure | None:
    authorized = _authorize(db, employee_id, customer_id)
    if isinstance(authorized, OrderCreateFailure):
        return authorized
    order = _order_for_key(db, customer_id, idempotency_key, lock=False)
    if order is None:
        return None
    return _existing_decision(order, request_hash)


def _commit_identity_expiry(db: Session, employee_id: int, customer_id: int) -> OrderCreateFailure | None:
    """Commit a date expiry outside the order transaction. National ID is unchanged."""
    employee = _locked_employee(db, employee_id)
    if isinstance(employee, OrderCreateFailure):
        return employee
    today = _server_today(db)
    verification = db.scalar(
        select(IdentityVerification)
        .where(
            IdentityVerification.customer_id == customer_id,
            IdentityVerification.status == "approved",
        )
        .with_for_update()
    )
    if verification is None:
        return None
    if not identity_expired_by_date(verification.document_type, verification.expires_on, today):
        return None
    verification.status = "expired"
    db.add(
        AuditLog(
            actor_type="employee",
            actor_id=employee.id,
            action="identity_expired",
            object_type="identity_verification",
            object_id=str(verification.id),
            metadata_json={"status": "expired"},
        )
    )
    return None


def _create_order_row(
    db: Session,
    *,
    employee_id: int,
    customer_id: int,
    idempotency_key: str,
    validated: ValidatedOrderRequest,
) -> OrderCreateResult | OrderCreateFailure:
    employee = _locked_employee(db, employee_id)
    if isinstance(employee, OrderCreateFailure):
        return employee
    customer = db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
    if customer is None:
        return _failure("not_found")

    existing = _order_for_key(db, customer_id, idempotency_key, lock=True)
    if existing is not None:
        return _existing_decision(existing, validated.request_hash)

    verification_id: int | None = None
    if validated.submission_intent == SUBMISSION_SUBMIT:
        blocked = _identity_for_new_order(db, customer_id, idempotency_key, validated.request_hash)
        if isinstance(blocked, OrderCreateFailure):
            return blocked
        if isinstance(blocked, OrderCreateResult):
            return blocked
        verification_id = blocked

    inserted_id = _insert_order(
        db,
        employee_id=employee.id,
        customer_id=customer_id,
        idempotency_key=idempotency_key,
        validated=validated,
        verification_id=verification_id,
    )
    winner = _order_for_key(db, customer_id, idempotency_key, lock=True)
    if winner is None:
        return _failure("invalid_request")
    if winner.request_hash != validated.request_hash:
        return _failure("idempotency_conflict")
    if inserted_id is None:
        return _snapshot(winner, created=False)
    _insert_children(db, winner, employee.id, validated)
    return _snapshot(winner, created=True)


def _identity_for_new_order(
    db: Session,
    customer_id: int,
    idempotency_key: str,
    request_hash: str,
) -> int | OrderCreateResult | OrderCreateFailure:
    today = _server_today(db)
    verification = db.scalar(
        select(IdentityVerification).where(
            IdentityVerification.customer_id == customer_id,
            IdentityVerification.status == "approved",
        )
    )
    if verification is None or not identity_date_valid(verification.document_type, verification.expires_on, today):
        failure = _failure("identity_expired") if _customer_has_unusable_identity(db, customer_id, today) else _failure("identity_required")
        return _prefer_committed_order(db, customer_id, idempotency_key, request_hash, failure)
    if not _document_bytes_remain(db, verification.id):
        return _prefer_committed_order(
            db,
            customer_id,
            idempotency_key,
            request_hash,
            _failure("identity_unavailable"),
        )
    return verification.id


def _prefer_committed_order(
    db: Session,
    customer_id: int,
    idempotency_key: str,
    request_hash: str,
    failure: OrderCreateFailure,
) -> OrderCreateResult | OrderCreateFailure:
    _before_blocked_identity_recheck()
    existing = _order_for_key(db, customer_id, idempotency_key, lock=True)
    if existing is None:
        return failure
    return _existing_decision(existing, request_hash)


def _before_blocked_identity_recheck() -> None:
    """No-op seam immediately before the post-failure idempotency recheck."""


def _customer_has_unusable_identity(db: Session, customer_id: int, today: date) -> bool:
    rows = db.scalars(select(IdentityVerification).where(IdentityVerification.customer_id == customer_id)).all()
    for row in rows:
        if row.status == "expired" or identity_expired_by_date(row.document_type, row.expires_on, today):
            return True
        if row.status == "approved" and not identity_date_valid(row.document_type, row.expires_on, today):
            return True
    return False


def _document_bytes_remain(db: Session, verification_id: int) -> bool:
    found = db.scalar(
        select(IdentityDocument.id)
        .where(
            IdentityDocument.verification_id == verification_id,
            IdentityDocument.bytes_removed_at.is_(None),
        )
        .limit(1)
    )
    return found is not None


def _insert_order(
    db: Session,
    *,
    employee_id: int,
    customer_id: int,
    idempotency_key: str,
    validated: ValidatedOrderRequest,
    verification_id: int | None,
) -> int | None:
    status = "draft" if validated.submission_intent == SUBMISSION_DRAFT else "new"
    statement = (
        pg_insert(ServiceOrder)
        .values(
            ref=secrets.token_hex(16),
            customer_id=customer_id,
            entered_by_employee_id=employee_id,
            channel="staff",
            service_code=validated.service_code,
            status=status,
            identity_verification_id=verification_id,
            customer_notes="" if validated.customer_notes is None else validated.customer_notes,
            version=1,
            idempotency_key=idempotency_key,
            request_hash=validated.request_hash,
        )
        .on_conflict_do_nothing(constraint="uq_order_idempotency")
        .returning(ServiceOrder.id)
    )
    return db.execute(statement).scalar()


def _insert_children(db: Session, order: ServiceOrder, employee_id: int, validated: ValidatedOrderRequest) -> None:
    for position, item in enumerate(validated.items, start=1):
        db.add(
            OrderItem(
                service_order_id=order.id,
                position=position,
                product_name=item.product_name,
                product_url=item.product_url,
                quantity=item.quantity,
                weight_kg=item.weight_kg,
                origin_country=item.origin_country,
                specification=item.specification,
                supplier_country=item.supplier_country,
                supplier_address=item.supplier_address,
                supplier_phone=item.supplier_phone,
                checklist=item.checklist,
                bid_amount=item.bid_amount,
            )
        )
    db.add(
        OrderStatusEvent(
            service_order_id=order.id,
            from_status=None,
            to_status=order.status,
            reason=None,
            actor_type="employee",
            actor_id=employee_id,
            version=order.version,
        )
    )


def _existing_decision(order: ServiceOrder, request_hash: str) -> OrderCreateResult | OrderCreateFailure:
    if idempotency_outcome(order.request_hash, request_hash) == "conflict":
        return _failure("idempotency_conflict")
    return _snapshot(order, created=False)


def _snapshot(order: ServiceOrder, *, created: bool) -> OrderCreateResult:
    return OrderCreateResult(
        order_id=order.id,
        created=created,
        customer_id=order.customer_id,
        status=order.status,
        request_hash=order.request_hash,
        identity_verification_id=order.identity_verification_id,
        ref=order.ref,
        version=order.version,
        channel=order.channel,
    )


def _locked_employee(db: Session, employee_id: int) -> Employee | OrderCreateFailure:
    employee = db.scalar(select(Employee).where(Employee.id == employee_id).with_for_update())
    if employee is None or not employee.is_active:
        return _failure("unauthenticated")
    if _CREATE_PERMISSION not in employee_permission_codes(db, employee.id):
        return _failure("forbidden")
    return employee


def _order_for_key(db: Session, customer_id: int, idempotency_key: str, *, lock: bool) -> ServiceOrder | None:
    statement = select(ServiceOrder).where(
        ServiceOrder.customer_id == customer_id,
        ServiceOrder.idempotency_key == idempotency_key,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _server_today(db: Session) -> date:
    today = _as_date(db.scalar(select(func.current_date())))
    if today is None:
        raise RuntimeError("database current_date is unavailable")
    return today


def _as_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value

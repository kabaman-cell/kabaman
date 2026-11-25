"""Stage 2 database tests. They use only the guarded phase 3 test database."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select, text

from api.models import (
    AuditLog,
    Customer,
    Employee,
    EmployeeRole,
    IdentityDocument,
    IdentityVerification,
    NotificationOutbox,
    Order,
    OrderItem,
    OrderStatusEvent,
    Role,
    ServiceOrder,
    ServiceType,
)
from api.order_creation import (
    OrderCreateFailure,
    OrderCreateResult,
    create_staff_order,
)
from api.order_validation import validate_order_request
from api.security import get_guarded_engine, session_scope

pytestmark = pytest.mark.filterwarnings("ignore:.*:DeprecationWarning")


@pytest.fixture(scope="module", autouse=True)
def guarded_phase3_database():
    engine = get_guarded_engine()
    with engine.connect() as connection:
        database, host, port = connection.execute(
            text("SELECT current_database(), host(inet_server_addr()), inet_server_port()")
        ).one()
    assert database == "kabaman_phase3_orders_test"
    assert host == "127.0.0.1"
    assert int(port) == 5432
    with session_scope() as db:
        if db.scalar(select(ServiceType.code).where(ServiceType.code == "sourcing")) is None:
            pytest.fail("sourcing is not present on the phase 3 test database")
        if db.scalar(select(Role.id).where(Role.name == "order_clerk")) is None:
            pytest.fail("order_clerk is not present on the phase 3 test database")
    yield


class World:
    def __init__(self):
        self.customer_ids: list[int] = []
        self.employee_ids: list[int] = []
        self.verification_ids: list[int] = []

    def close(self) -> None:
        if not self.customer_ids and not self.employee_ids and not self.verification_ids:
            return
        with session_scope() as db:
            order_ids = []
            if self.customer_ids:
                order_ids = list(
                    db.scalars(select(ServiceOrder.id).where(ServiceOrder.customer_id.in_(self.customer_ids)))
                )
            if order_ids:
                db.execute(delete(OrderItem).where(OrderItem.service_order_id.in_(order_ids)))
                db.execute(delete(OrderStatusEvent).where(OrderStatusEvent.service_order_id.in_(order_ids)))
                db.execute(delete(NotificationOutbox).where(NotificationOutbox.service_order_id.in_(order_ids)))
                db.execute(delete(ServiceOrder).where(ServiceOrder.id.in_(order_ids)))
            if self.verification_ids:
                db.execute(delete(IdentityDocument).where(IdentityDocument.verification_id.in_(self.verification_ids)))
                db.execute(
                    delete(AuditLog).where(
                        AuditLog.object_type == "identity_verification",
                        AuditLog.object_id.in_([str(value) for value in self.verification_ids]),
                    )
                )
                db.execute(delete(IdentityVerification).where(IdentityVerification.id.in_(self.verification_ids)))
            if self.employee_ids:
                db.execute(delete(EmployeeRole).where(EmployeeRole.employee_id.in_(self.employee_ids)))
                db.execute(delete(Employee).where(Employee.id.in_(self.employee_ids)))
            if self.customer_ids:
                db.execute(delete(Customer).where(Customer.id.in_(self.customer_ids)))

    def employee(self, *, active: bool = True, grant: bool = True) -> int:
        with session_scope() as db:
            role_id = db.scalar(select(Role.id).where(Role.name == "order_clerk"))
            row = Employee(
                email="stage2-employee-%s@example.com" % uuid.uuid4().hex,
                name="Stage Two Clerk",
                password_hash="not-a-login-secret",
                is_active=active,
            )
            db.add(row)
            db.flush()
            if grant:
                db.add(EmployeeRole(employee_id=row.id, role_id=role_id))
            employee_id = row.id
        self.employee_ids.append(employee_id)
        return employee_id

    def customer(self) -> int:
        with session_scope() as db:
            row = Customer(
                email="stage2-customer-%s@example.com" % uuid.uuid4().hex,
                name="Stage Two Customer",
                phone="",
                password_hash="not-a-login-secret",
            )
            db.add(row)
            db.flush()
            customer_id = row.id
        self.customer_ids.append(customer_id)
        return customer_id

    def identity(
        self,
        *,
        customer_id: int,
        reviewer_id: int,
        document_type: str,
        expires_on,
        remove_bytes: bool = False,
    ) -> int:
        moment = datetime.now(timezone.utc)
        with session_scope() as db:
            verification = IdentityVerification(
                customer_id=customer_id,
                document_type=document_type,
                status="approved",
                expires_on=expires_on,
                reviewed_by_employee_id=reviewer_id,
                reviewed_at=moment,
            )
            db.add(verification)
            db.flush()
            db.add(
                IdentityDocument(
                    verification_id=verification.id,
                    page_kind="front",
                    page_sequence=1,
                    storage_key="stage2/%s" % uuid.uuid4().hex,
                    sha256="ab" * 32,
                    content_type="image/jpeg",
                    byte_size=4,
                    key_version=1,
                    wrapped_dek=b"k" * 32,
                    wrap_nonce=b"n" * 12,
                    wrap_tag=b"t" * 16,
                    file_nonce=b"n" * 12,
                    file_tag=b"t" * 16,
                    created_at=moment,
                    retain_bytes_until=moment,
                    bytes_removed_at=moment if remove_bytes else None,
                )
            )
            verification_id = verification.id
        self.verification_ids.append(verification_id)
        return verification_id


@pytest.fixture
def world():
    value = World()
    try:
        yield value
    finally:
        value.close()


def server_today():
    with session_scope() as db:
        value = db.scalar(select(func.current_date()))
    if isinstance(value, datetime):
        return value.date()
    return value


def lamp(name: str = "Lamp"):
    return {"product_name": name, "product_url": "https://example.com/%s" % name.lower()}


def create(employee_id, customer_id, key, *, name="Lamp", submit=True):
    return create_staff_order(
        employee_id=employee_id,
        customer_id=customer_id,
        idempotency_key=key,
        service_code="sourcing",
        submit=submit,
        items=[] if name is None else [lamp(name)],
        customer_notes=None,
    )


def verification_status(verification_id: int) -> str:
    with session_scope() as db:
        return db.scalar(select(IdentityVerification.status).where(IdentityVerification.id == verification_id))


def order_count(customer_id: int, key: str | None = None) -> int:
    with session_scope() as db:
        statement = select(func.count()).select_from(ServiceOrder).where(ServiceOrder.customer_id == customer_id)
        if key is not None:
            statement = statement.where(ServiceOrder.idempotency_key == key)
        return db.scalar(statement)


def child_counts(order_id: int) -> tuple[int, int, int]:
    with session_scope() as db:
        items = db.scalar(select(func.count()).select_from(OrderItem).where(OrderItem.service_order_id == order_id))
        events = db.scalar(
            select(func.count()).select_from(OrderStatusEvent).where(OrderStatusEvent.service_order_id == order_id)
        )
        notices = db.scalar(
            select(func.count()).select_from(NotificationOutbox).where(NotificationOutbox.service_order_id == order_id)
        )
        return items, events, notices


def stored_verification(order_id: int) -> int | None:
    with session_scope() as db:
        return db.scalar(select(ServiceOrder.identity_verification_id).where(ServiceOrder.id == order_id))


def test_expiry_is_committed_and_survives_the_order_rollback(world: World):
    today = server_today()
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="passport",
        expires_on=today - timedelta(days=1),
    )
    legacy_before = _legacy_order_count()
    result = create(employee_id, customer_id, "expire-%s" % uuid.uuid4().hex)
    assert isinstance(result, OrderCreateFailure)
    assert result.code == "identity_expired"
    assert result.status == 403
    assert verification_status(verification_id) == "expired"
    assert order_count(customer_id) == 0
    with session_scope() as db:
        audit_count = db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.object_type == "identity_verification",
                AuditLog.object_id == str(verification_id),
                AuditLog.action == "identity_expired",
            )
        )
    assert audit_count == 1
    assert _legacy_order_count() == legacy_before


@pytest.mark.parametrize("document_type", ["passport", "driving_license"])
def test_expired_passport_and_license_cannot_authorize_a_new_order(world: World, document_type: str):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type=document_type,
        expires_on=server_today() - timedelta(days=1),
    )
    result = create(employee_id, customer_id, "past-%s" % uuid.uuid4().hex)
    assert isinstance(result, OrderCreateFailure)
    assert result.code == "identity_expired"
    assert verification_status(verification_id) == "expired"
    assert order_count(customer_id) == 0


def test_national_id_does_not_expire_by_date_and_can_authorize(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    first = create(employee_id, customer_id, "nid-a-%s" % uuid.uuid4().hex)
    second = create(employee_id, customer_id, "nid-b-%s" % uuid.uuid4().hex)
    assert isinstance(first, OrderCreateResult)
    assert isinstance(second, OrderCreateResult)
    assert first.created is True
    assert second.created is True
    assert first.order_id != second.order_id
    assert verification_status(verification_id) == "approved"
    assert stored_verification(first.order_id) == verification_id


def test_document_in_date_today_can_authorize(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="driving_license",
        expires_on=server_today(),
    )
    result = create(employee_id, customer_id, "today-%s" % uuid.uuid4().hex)
    assert isinstance(result, OrderCreateResult)
    assert result.created is True
    assert result.channel == "staff"
    assert result.status == "new"
    assert verification_status(verification_id) == "approved"
    assert child_counts(result.order_id) == (1, 1, 0)


def test_missing_document_bytes_block_a_new_order(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="passport",
        expires_on=server_today(),
        remove_bytes=True,
    )
    result = create(employee_id, customer_id, "bytes-%s" % uuid.uuid4().hex)
    assert isinstance(result, OrderCreateFailure)
    assert result.code == "identity_unavailable"
    assert result.status == 403
    assert verification_status(verification_id) == "approved"
    assert order_count(customer_id) == 0


def test_matching_replay_after_expiry_returns_the_original_order(world: World):
    today = server_today()
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="passport",
        expires_on=today,
    )
    key = "replay-expire-%s" % uuid.uuid4().hex
    created = create(employee_id, customer_id, key)
    assert isinstance(created, OrderCreateResult)
    with session_scope() as db:
        row = db.get(IdentityVerification, verification_id)
        row.expires_on = today - timedelta(days=1)
    early_replay = create(employee_id, customer_id, key)
    assert isinstance(early_replay, OrderCreateResult)
    assert early_replay.order_id == created.order_id
    assert early_replay.created is False
    assert verification_status(verification_id) == "approved"
    blocked = create(employee_id, customer_id, "other-%s" % uuid.uuid4().hex)
    assert isinstance(blocked, OrderCreateFailure)
    assert blocked.code == "identity_expired"
    assert verification_status(verification_id) == "expired"
    replay = create(employee_id, customer_id, key)
    assert isinstance(replay, OrderCreateResult)
    assert replay.order_id == created.order_id
    assert replay.created is False
    assert replay.identity_verification_id == verification_id
    assert stored_verification(created.order_id) == verification_id
    assert child_counts(created.order_id) == (1, 1, 0)
    assert order_count(customer_id) == 1


def test_matching_replay_after_byte_removal_returns_the_original_order(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    key = "replay-bytes-%s" % uuid.uuid4().hex
    created = create(employee_id, customer_id, key)
    assert isinstance(created, OrderCreateResult)
    moment = datetime.now(timezone.utc)
    with session_scope() as db:
        document = db.scalar(select(IdentityDocument).where(IdentityDocument.verification_id == verification_id))
        document.retain_bytes_until = moment
        document.bytes_removed_at = moment
    replay = create(employee_id, customer_id, key)
    assert isinstance(replay, OrderCreateResult)
    assert replay.order_id == created.order_id
    assert replay.created is False
    assert stored_verification(created.order_id) == verification_id
    assert child_counts(created.order_id) == (1, 1, 0)
    blocked = create(employee_id, customer_id, "fresh-%s" % uuid.uuid4().hex)
    assert isinstance(blocked, OrderCreateFailure)
    assert blocked.code == "identity_unavailable"
    assert verification_status(verification_id) == "approved"


def test_same_key_with_a_different_payload_returns_409_without_the_order(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    key = "conflict-%s" % uuid.uuid4().hex
    created = create(employee_id, customer_id, key, name="Lamp")
    conflict = create(employee_id, customer_id, key, name="Chair")
    assert isinstance(created, OrderCreateResult)
    assert isinstance(conflict, OrderCreateFailure)
    assert conflict.status == 409
    assert conflict.code == "idempotency_conflict"
    assert conflict.error == "This idempotency key was already used with a different request."
    assert [field for field in conflict.__dataclass_fields__] == ["status", "code", "error"]
    assert order_count(customer_id, key) == 1
    with session_scope() as db:
        names = list(db.scalars(select(OrderItem.product_name).where(OrderItem.service_order_id == created.order_id)))
    assert names == ["Lamp"]
    assert child_counts(created.order_id) == (1, 1, 0)


def test_authorization_is_required_before_an_idempotent_lookup(world: World):
    clerk_id = world.employee()
    outsider_id = world.employee(grant=False)
    inactive_id = world.employee(active=False, grant=True)
    customer_id = world.customer()
    world.identity(
        customer_id=customer_id,
        reviewer_id=clerk_id,
        document_type="national_id",
        expires_on=None,
    )
    key = "auth-%s" % uuid.uuid4().hex
    created = create(clerk_id, customer_id, key)
    assert isinstance(created, OrderCreateResult)
    forbidden = create(outsider_id, customer_id, key)
    unauthenticated = create(inactive_id, customer_id, key)
    missing = create(clerk_id, 9_000_000_000_000, key)
    assert isinstance(forbidden, OrderCreateFailure)
    assert forbidden.status == 403
    assert forbidden.code == "forbidden"
    assert isinstance(unauthenticated, OrderCreateFailure)
    assert unauthenticated.status == 401
    assert isinstance(missing, OrderCreateFailure)
    assert missing.code == "not_found"
    assert order_count(customer_id, key) == 1
    assert not hasattr(forbidden, "order_id")


def test_same_key_for_another_customer_does_not_return_the_first_order(world: World):
    employee_id = world.employee()
    first_customer = world.customer()
    second_customer = world.customer()
    world.identity(
        customer_id=first_customer,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    world.identity(
        customer_id=second_customer,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    key = "shared-key-%s" % uuid.uuid4().hex
    first = create(employee_id, first_customer, key)
    second = create(employee_id, second_customer, key)
    assert isinstance(first, OrderCreateResult)
    assert isinstance(second, OrderCreateResult)
    assert first.order_id != second.order_id
    assert second.customer_id == second_customer
    assert stored_verification(first.order_id) != stored_verification(second.order_id)


def test_validation_failure_does_not_consult_identity(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    result = create(employee_id, customer_id, "invalid-%s" % uuid.uuid4().hex, name=" ")
    assert isinstance(result, OrderCreateFailure)
    assert result.code == "product_name_required"
    assert result.status == 422
    assert order_count(customer_id) == 0


def test_draft_does_not_require_identity_or_expire_a_past_document(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="passport",
        expires_on=server_today() - timedelta(days=1),
    )
    result = create(employee_id, customer_id, "draft-%s" % uuid.uuid4().hex, submit=False)
    assert isinstance(result, OrderCreateResult)
    assert result.created is True
    assert result.status == "draft"
    assert result.identity_verification_id is None
    assert verification_status(verification_id) == "approved"


def test_concurrent_identical_requests_create_one_order(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    key = "concurrent-same-%s" % uuid.uuid4().hex
    results = _together(
        lambda: create(employee_id, customer_id, key, name="Lamp"),
        lambda: create(employee_id, customer_id, key, name="Lamp"),
    )
    assert all(isinstance(result, OrderCreateResult) for result in results)
    assert {result.order_id for result in results} == {results[0].order_id}
    assert sum(result.created for result in results) == 1
    assert order_count(customer_id, key) == 1
    assert child_counts(results[0].order_id) == (1, 1, 0)


def test_concurrent_different_payloads_create_one_order_and_one_conflict(world: World):
    employee_id = world.employee()
    customer_id = world.customer()
    world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="national_id",
        expires_on=None,
    )
    key = "concurrent-diff-%s" % uuid.uuid4().hex
    results = _together(
        lambda: create(employee_id, customer_id, key, name="Lamp"),
        lambda: create(employee_id, customer_id, key, name="Chair"),
    )
    success = [result for result in results if isinstance(result, OrderCreateResult)]
    failure = [result for result in results if isinstance(result, OrderCreateFailure)]
    assert len(success) == 1
    assert len(failure) == 1
    assert failure[0].status == 409
    assert failure[0].code == "idempotency_conflict"
    assert not hasattr(failure[0], "order_id")
    assert order_count(customer_id, key) == 1
    assert child_counts(success[0].order_id) == (1, 1, 0)


def test_order_committed_after_lookup_is_replayed_when_identity_is_expired(world: World, monkeypatch):
    employee_id = world.employee()
    customer_id = world.customer()
    verification_id = world.identity(
        customer_id=customer_id,
        reviewer_id=employee_id,
        document_type="passport",
        expires_on=server_today() - timedelta(days=1),
    )
    key = "late-commit-%s" % uuid.uuid4().hex
    items = [lamp("Lamp")]
    validated = validate_order_request(
        customer_id=customer_id,
        service_code="sourcing",
        channel="staff",
        submit=True,
        items=items,
        customer_notes=None,
    )

    def commit_the_order() -> None:
        with session_scope() as db:
            db.add(
                ServiceOrder(
                    ref="late%s" % uuid.uuid4().hex[:16],
                    customer_id=customer_id,
                    entered_by_employee_id=employee_id,
                    channel="staff",
                    service_code="sourcing",
                    status="new",
                    identity_verification_id=verification_id,
                    customer_notes="",
                    version=1,
                    idempotency_key=key,
                    request_hash=validated.request_hash,
                )
            )

    monkeypatch.setattr("api.order_creation._before_order_transaction", commit_the_order)
    result = create_staff_order(
        employee_id=employee_id,
        customer_id=customer_id,
        idempotency_key=key,
        service_code="sourcing",
        submit=True,
        items=items,
        customer_notes=None,
    )
    assert isinstance(result, OrderCreateResult)
    assert result.created is False
    assert result.identity_verification_id == verification_id
    assert result.request_hash == validated.request_hash
    assert verification_status(verification_id) == "expired"
    assert order_count(customer_id, key) == 1
    assert child_counts(result.order_id) == (0, 0, 0)


def _together(first, second):
    barrier = threading.Barrier(2)
    results = [None, None]
    errors = []

    def run(index, function):
        try:
            barrier.wait(10)
            results[index] = function()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=(0, first)),
        threading.Thread(target=run, args=(1, second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
        if thread.is_alive():
            pytest.fail("order creation did not finish")
    if errors:
        raise errors[0]
    return results


def _legacy_order_count() -> int:
    with session_scope() as db:
        return db.scalar(select(func.count()).select_from(Order))

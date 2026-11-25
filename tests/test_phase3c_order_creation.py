"""Pure Stage 2 decisions. Importing this module does not open a database."""

from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta
from types import SimpleNamespace

from api.order_creation import (
    OrderCreateFailure,
    _prefer_committed_order,
    identity_date_valid,
    identity_expired_by_date,
    idempotency_outcome,
)

TODAY = date(2026, 11, 25)


def test_national_id_does_not_expire_by_date():
    past = TODAY - timedelta(days=400)
    assert identity_date_valid("national_id", None, TODAY) is True
    assert identity_date_valid("national_id", past, TODAY) is True
    assert identity_expired_by_date("national_id", past, TODAY) is False
    assert identity_expired_by_date("national_id", None, TODAY) is False


def test_passport_and_driving_license_expire_before_today():
    yesterday = TODAY - timedelta(days=1)
    for document_type in ("passport", "driving_license"):
        assert identity_date_valid(document_type, TODAY, TODAY) is True
        assert identity_date_valid(document_type, yesterday, TODAY) is False
        assert identity_date_valid(document_type, None, TODAY) is False
        assert identity_expired_by_date(document_type, yesterday, TODAY) is True
        assert identity_expired_by_date(document_type, TODAY, TODAY) is False


def test_idempotency_outcome_distinguishes_replay_and_conflict():
    assert idempotency_outcome(None, "a" * 64) == "absent"
    assert idempotency_outcome("a" * 64, "a" * 64) == "replay"
    assert idempotency_outcome("a" * 64, "b" * 64) == "conflict"


def test_conflict_failure_has_no_order_body():
    failure = OrderCreateFailure(
        409,
        "idempotency_conflict",
        "This idempotency key was already used with a different request.",
    )
    assert [field.name for field in fields(failure)] == ["status", "code", "error"]
    assert not hasattr(failure, "order_id")


class _Orders:
    def __init__(self, order):
        self.order = order

    def scalar(self, _statement):
        return self.order


def _order(request_hash: str):
    return SimpleNamespace(
        id=41,
        request_hash=request_hash,
        customer_id=7,
        status="new",
        identity_verification_id=11,
        ref="opaque",
        version=1,
        channel="staff",
    )


def test_identity_failure_rechecks_and_returns_a_matching_order():
    failure = OrderCreateFailure(403, "identity_expired", "This identity document has expired.")
    result = _prefer_committed_order(_Orders(_order("a" * 64)), 7, "key", "a" * 64, failure)
    assert result.order_id == 41
    assert result.created is False
    assert result.identity_verification_id == 11


def test_identity_failure_recheck_conflicts_without_an_order_body():
    failure = OrderCreateFailure(403, "identity_unavailable", "Submit a new identity document before ordering.")
    result = _prefer_committed_order(_Orders(_order("a" * 64)), 7, "key", "b" * 64, failure)
    assert isinstance(result, OrderCreateFailure)
    assert result.status == 409
    assert result.code == "idempotency_conflict"
    assert not hasattr(result, "order_id")


def test_identity_failure_stands_when_no_order_was_committed():
    failure = OrderCreateFailure(403, "identity_expired", "This identity document has expired.")
    result = _prefer_committed_order(_Orders(None), 7, "key", "a" * 64, failure)
    assert result is failure

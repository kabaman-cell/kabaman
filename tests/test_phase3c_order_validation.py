"""Isolated Phase 3C stage 1 checks. These tests do not open a database."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from api.models import MAX_SERVICE_ORDER_ITEMS
from api.order_validation import (
    ORDER_MESSAGES,
    OrderValidationFailure,
    ValidatedOrderRequest,
    canonical_request_document,
    canonical_request_hash,
    validate_order_request,
)

CUSTOMER_ID = 17


def sourcing(**overrides):
    item = {"product_name": "Lamp", "product_url": "https://example.com/lamp"}
    item.update(overrides)
    return item


def importation(**overrides):
    item = {
        "product_name": "Bolt",
        "product_url": "https://example.com/bolt",
        "quantity": 250,
        "weight_kg": Decimal("1.000"),
        "origin_country": "CN",
        "specification": "M8 steel",
    }
    item.update(overrides)
    return item


def inspection(**overrides):
    item = {
        "product_name": "Press",
        "supplier_country": "DZ",
        "supplier_address": "1 Industrial Road",
        "supplier_phone": "+213555010101",
        "checklist": "welds, guards, serial",
    }
    item.update(overrides)
    return item


def auction(**overrides):
    item = {
        "product_name": "Lathe",
        "specification": "1500 mm bed",
        "bid_amount": Decimal("10.50"),
    }
    item.update(overrides)
    return item


def validate(service_code, items, **kwargs):
    values = {
        "customer_id": CUSTOMER_ID,
        "service_code": service_code,
        "channel": "staff",
        "submit": True,
        "items": items,
        "customer_notes": None,
    }
    values.update(kwargs)
    return validate_order_request(**values)


def assert_code(result, code):
    assert isinstance(result, OrderValidationFailure)
    assert result.code == code
    assert result.error == ORDER_MESSAGES[code]


def test_each_service_accepts_its_minimum_fields():
    sourcing_order = validate("sourcing", [sourcing()])
    importation_order = validate("importation", [importation()])
    inspection_order = validate("inspection", [inspection()])
    auction_order = validate("auction", [auction()])
    assert isinstance(sourcing_order, ValidatedOrderRequest)
    assert isinstance(importation_order, ValidatedOrderRequest)
    assert isinstance(inspection_order, ValidatedOrderRequest)
    assert isinstance(auction_order, ValidatedOrderRequest)
    assert sourcing_order.submission_intent == "submit"
    assert importation_order.items[0].quantity == 250
    assert inspection_order.items[0].product_url is None
    assert auction_order.items[0].bid_amount == Decimal("10.50")


@pytest.mark.parametrize(
    ("service_code", "item", "code"),
    [
        ("sourcing", sourcing(product_name="  "), "product_name_required"),
        ("sourcing", sourcing(product_url=None), "product_url_required"),
        ("sourcing", sourcing(product_url=""), "product_url_required"),
        ("sourcing", sourcing(product_url="ftp://example.com/lamp"), "product_url_invalid"),
        ("sourcing", sourcing(product_url="http://"), "product_url_invalid"),
        ("sourcing", sourcing(product_url="https://bad host/lamp"), "product_url_invalid"),
        ("importation", importation(product_url=None), "product_url_required"),
        ("importation", importation(quantity=None), "quantity_required"),
        ("importation", importation(weight_kg=None), "weight_required"),
        ("importation", importation(origin_country=" "), "origin_country_required"),
        ("importation", importation(specification=""), "specification_required"),
        ("inspection", inspection(supplier_country=""), "supplier_country_required"),
        ("inspection", inspection(supplier_address=None), "supplier_address_required"),
        ("inspection", inspection(supplier_phone=""), "supplier_phone_required"),
        ("inspection", inspection(checklist=" "), "checklist_required"),
        ("auction", auction(specification=None), "specification_required"),
        ("auction", auction(bid_amount=None), "bid_required"),
    ],
)
def test_required_fields(service_code, item, code):
    assert_code(validate(service_code, [item]), code)


def test_optional_fields_are_validated_only_when_present():
    accepted = validate(
        "sourcing",
        [sourcing(
            quantity=2,
            weight_kg=Decimal("500.000"),
            origin_country="TR",
            specification="brass",
            supplier_country="TR",
            supplier_address="Port warehouse",
            supplier_phone="+905550000000",
            checklist="visual",
            bid_amount=Decimal("3.25"),
        )],
    )
    assert isinstance(accepted, ValidatedOrderRequest)
    assert accepted.items[0].weight_kg == Decimal("500.000")
    assert_code(validate("sourcing", [sourcing(quantity=0)]), "quantity_invalid")
    assert_code(validate("inspection", [inspection(product_url="notaurl")]), "product_url_invalid")
    assert_code(validate("auction", [auction(supplier_phone=" ")]), "supplier_phone_required")
    assert_code(validate("sourcing", [sourcing(bid_amount=Decimal("0"))]), "bid_invalid")


def test_http_and_https_urls_are_accepted():
    http_order = validate("sourcing", [sourcing(product_url="http://example.com/a")])
    https_order = validate("sourcing", [sourcing(product_url="https://example.com/b")])
    assert isinstance(http_order, ValidatedOrderRequest)
    assert isinstance(https_order, ValidatedOrderRequest)
    assert http_order.items[0].product_url == "http://example.com/a"


def test_first_failing_field_is_the_only_result():
    result = validate(
        "importation",
        [importation(product_name="", quantity=None, weight_kg=None)],
    )
    assert_code(result, "product_name_required")


def test_unknown_service_is_rejected():
    assert_code(validate("shipping", [sourcing()]), "service_unknown")


def test_submit_requires_an_item_and_a_draft_may_be_empty():
    assert_code(validate("sourcing", [], submit=True), "items_required")
    draft = validate("importation", [], submit=False)
    assert isinstance(draft, ValidatedOrderRequest)
    assert draft.submission_intent == "draft"
    assert draft.items == ()


def test_twenty_lines_are_accepted_and_twenty_one_are_rejected():
    accepted = validate("sourcing", [sourcing(product_name="Line %d" % index) for index in range(MAX_SERVICE_ORDER_ITEMS)])
    assert isinstance(accepted, ValidatedOrderRequest)
    assert len(accepted.items) == 20
    rejected = validate("sourcing", [sourcing() for _ in range(MAX_SERVICE_ORDER_ITEMS + 1)])
    assert_code(rejected, "items_above_maximum")


def test_importation_quantity_boundary_is_an_order_total():
    assert_code(validate("importation", [importation(quantity=249)]), "quantity_below_minimum")
    one_line = validate("importation", [importation(quantity=250)])
    two_lines = validate(
        "importation",
        [importation(quantity=100, weight_kg=Decimal("0.500")), importation(quantity=150, weight_kg=Decimal("0.500"))],
    )
    assert isinstance(one_line, ValidatedOrderRequest)
    assert isinstance(two_lines, ValidatedOrderRequest)
    assert_code(
        validate(
            "importation",
            [importation(quantity=100), importation(quantity=149)],
        ),
        "quantity_below_minimum",
    )


def test_importation_weight_boundary_is_an_order_total():
    assert isinstance(validate("importation", [importation(weight_kg=Decimal("100.000"))]), ValidatedOrderRequest)
    assert_code(validate("importation", [importation(weight_kg=Decimal("100.001"))]), "weight_above_maximum")
    accepted = validate(
        "importation",
        [
            importation(quantity=125, weight_kg=Decimal("99.999")),
            importation(quantity=125, weight_kg=Decimal("0.001")),
        ],
    )
    assert isinstance(accepted, ValidatedOrderRequest)
    assert_code(
        validate(
            "importation",
            [
                importation(quantity=125, weight_kg=Decimal("50")),
                importation(quantity=125, weight_kg=Decimal("50.001")),
            ],
        ),
        "weight_above_maximum",
    )


def test_other_services_do_not_use_importation_totals():
    for service_code, item in (
        ("sourcing", sourcing(quantity=1, weight_kg=Decimal("100.001"))),
        ("inspection", inspection(quantity=1, weight_kg=Decimal("250.000"))),
        ("auction", auction(quantity=249, weight_kg=Decimal("100.001"))),
    ):
        assert isinstance(validate(service_code, [item]), ValidatedOrderRequest)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("weight_kg", 1.25, "weight_invalid"),
        ("weight_kg", Decimal(0.1), "weight_invalid"),
        ("weight_kg", Decimal("0"), "weight_invalid"),
        ("weight_kg", Decimal("-1.000"), "weight_invalid"),
        ("weight_kg", Decimal("1.2345"), "weight_invalid"),
        ("weight_kg", Decimal("1.0000"), "weight_invalid"),
        ("bid_amount", 2.5, "bid_invalid"),
        ("bid_amount", Decimal("1.234"), "bid_invalid"),
        ("bid_amount", Decimal("-0.01"), "bid_invalid"),
        ("quantity", 1.0, "quantity_invalid"),
        ("quantity", True, "quantity_invalid"),
        ("quantity", Decimal("2"), "quantity_invalid"),
    ],
)
def test_decimal_precision_and_float_rejection(field, value, code):
    assert_code(validate("sourcing", [sourcing(**{field: value})]), code)
    assert_code(validate("auction", [auction(**{field: value})]), code)


def test_exact_decimals_are_kept():
    order = validate(
        "auction",
        [auction(weight_kg=Decimal("1.230"), bid_amount=Decimal("10.50"))],
    )
    assert isinstance(order, ValidatedOrderRequest)
    assert order.items[0].weight_kg == Decimal("1.230")
    assert order.items[0].bid_amount == Decimal("10.50")
    document = canonical_request_document(
        customer_id=order.customer_id,
        service_code=order.service_code,
        channel=order.channel,
        submission_intent=order.submission_intent,
        items=order.items,
        customer_notes=order.customer_notes,
    )
    assert document["items"][0]["weight_kg"] == "1.230"
    assert document["items"][0]["bid_amount"] == "10.50"


def test_customer_portal_and_whatsapp_draft_are_rejected():
    assert_code(validate("sourcing", [sourcing()], channel="customer_portal"), "channel_rejected")
    assert_code(validate("sourcing", [sourcing()], channel="whatsapp", submit=False), "channel_rejected")


def test_whatsapp_intent_is_submit():
    explicit = validate("sourcing", [sourcing()], channel="whatsapp", submit=True)
    implied = validate("sourcing", [sourcing()], channel="whatsapp", submit=None)
    assert isinstance(explicit, ValidatedOrderRequest)
    assert isinstance(implied, ValidatedOrderRequest)
    assert explicit.submission_intent == "submit"
    assert implied.submission_intent == "submit"
    assert explicit.request_hash == implied.request_hash


def test_draft_and_submit_hash_differ_for_the_same_items():
    draft = validate("sourcing", [sourcing()], submit=False)
    submitted = validate("sourcing", [sourcing()], submit=True)
    assert isinstance(draft, ValidatedOrderRequest)
    assert isinstance(submitted, ValidatedOrderRequest)
    assert draft.submission_intent == "draft"
    assert submitted.submission_intent == "submit"
    assert draft.request_hash != submitted.request_hash


def test_hash_is_stable_and_uses_only_the_canonical_fields():
    notes = "Call before noon"
    first = validate("sourcing", [sourcing(product_url="https://example.com/lamp")], customer_notes=notes)
    second = validate(
        "sourcing",
        [{"product_url": "https://example.com/lamp", "product_name": "Lamp", "idempotency_key": "abc"}],
        customer_notes=notes,
    )
    assert isinstance(first, ValidatedOrderRequest)
    assert isinstance(second, ValidatedOrderRequest)
    assert first.request_hash == second.request_hash
    assert len(first.request_hash) == 64
    assert first.request_hash == first.request_hash.lower()
    document = canonical_request_document(
        customer_id=first.customer_id,
        service_code=first.service_code,
        channel=first.channel,
        submission_intent=first.submission_intent,
        items=first.items,
        customer_notes=first.customer_notes,
    )
    assert set(document) == {
        "customer_id",
        "service_code",
        "channel",
        "submission_intent",
        "items",
        "notes",
    }
    encoded = json.dumps(document)
    assert "idempotency_key" not in encoded
    assert "identity_verification_id" not in encoded
    assert '"status"' not in encoded
    assert '"version"' not in encoded
    assert '"ref"' not in encoded
    again = canonical_request_hash(
        customer_id=first.customer_id,
        service_code=first.service_code,
        channel=first.channel,
        submission_intent=first.submission_intent,
        items=first.items,
        customer_notes=first.customer_notes,
    )
    assert again == first.request_hash


def test_item_order_customer_channel_and_notes_change_the_hash():
    lamp = sourcing()
    chair = sourcing(product_name="Chair", product_url="https://example.com/chair")
    forward = validate("sourcing", [lamp, chair])
    backward = validate("sourcing", [chair, lamp])
    other_customer = validate("sourcing", [lamp, chair], customer_id=18)
    whatsapp = validate("sourcing", [lamp, chair], channel="whatsapp", submit=True)
    noted = validate("sourcing", [lamp, chair], customer_notes="fragile")
    assert isinstance(forward, ValidatedOrderRequest)
    hashes = {
        forward.request_hash,
        backward.request_hash,
        other_customer.request_hash,
        whatsapp.request_hash,
        noted.request_hash,
    }
    assert len(hashes) == 5

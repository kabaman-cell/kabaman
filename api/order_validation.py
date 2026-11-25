"""Service-line validation and canonical request hashing for Phase 3C stage 1.

This module does not open a database connection, register a route, or read
identity, nonce, or outbox state. Importation totals are the approved
service_types seed: 250 pieces and 100.000 kg. Other services have no totals.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from api.models import MAX_SERVICE_ORDER_ITEMS, SERVICE_CODES

SUBMISSION_DRAFT = "draft"
SUBMISSION_SUBMIT = "submit"
SUBMISSION_INTENTS = frozenset({SUBMISSION_DRAFT, SUBMISSION_SUBMIT})

IMPORTATION_MIN_TOTAL_QUANTITY = 250
IMPORTATION_MAX_TOTAL_WEIGHT_KG = Decimal("100.000")
WEIGHT_SCALE = 3
BID_SCALE = 2

_TOTAL_LIMITS: dict[str, tuple[int | None, Decimal | None]] = {
    "sourcing": (None, None),
    "importation": (IMPORTATION_MIN_TOTAL_QUANTITY, IMPORTATION_MAX_TOTAL_WEIGHT_KG),
    "inspection": (None, None),
    "auction": (None, None),
}

_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "sourcing": frozenset({"product_url"}),
    "importation": frozenset({
        "product_url",
        "quantity",
        "weight_kg",
        "origin_country",
        "specification",
    }),
    "inspection": frozenset({
        "supplier_country",
        "supplier_address",
        "supplier_phone",
        "checklist",
    }),
    "auction": frozenset({"specification", "bid_amount"}),
}

_ITEM_FIELDS = (
    "product_name",
    "product_url",
    "quantity",
    "weight_kg",
    "origin_country",
    "specification",
    "supplier_country",
    "supplier_address",
    "supplier_phone",
    "checklist",
    "bid_amount",
)

_TEXT_FIELDS = frozenset({
    "product_name",
    "origin_country",
    "specification",
    "supplier_country",
    "supplier_address",
    "supplier_phone",
    "checklist",
})

_MISSING_CODES = {
    "product_name": "product_name_required",
    "product_url": "product_url_required",
    "quantity": "quantity_required",
    "weight_kg": "weight_required",
    "origin_country": "origin_country_required",
    "specification": "specification_required",
    "supplier_country": "supplier_country_required",
    "supplier_address": "supplier_address_required",
    "supplier_phone": "supplier_phone_required",
    "checklist": "checklist_required",
    "bid_amount": "bid_required",
}

ORDER_MESSAGES = {
    "service_unknown": "That service is not available.",
    "items_required": "Add at least one item.",
    "items_above_maximum": "An order can contain at most 20 product lines.",
    "product_name_required": "Add the product name.",
    "product_url_required": "Paste the product link.",
    "product_url_invalid": "Paste a product link starting with http:// or https://.",
    "quantity_required": "Enter the quantity.",
    "quantity_invalid": "Enter a whole number of at least 1 piece.",
    "quantity_below_minimum": "Enter a total of at least 250 pieces.",
    "weight_required": "Enter the weight.",
    "weight_invalid": "Enter a weight greater than 0 with at most 3 decimal places.",
    "weight_above_maximum": "Enter a total weight of at most 100 kg.",
    "origin_country_required": "Add the origin country.",
    "specification_required": "Add the product specification.",
    "supplier_country_required": "Add the country of the customer's supplier.",
    "supplier_address_required": "Add the address of the customer's supplier.",
    "supplier_phone_required": "Add the phone number of the supplier.",
    "checklist_required": "Add the checklist to inspect.",
    "bid_required": "Enter a bid.",
    "bid_invalid": "Enter a bid greater than 0.",
    "channel_rejected": "That order channel is not available.",
}

class OrderValidationError(ValueError):
    """A caller passed a shape this stage does not validate as an order field."""


@dataclass(frozen=True)
class OrderValidationFailure:
    code: str
    error: str


@dataclass(frozen=True)
class ValidatedOrderItem:
    product_name: str
    product_url: str | None = None
    quantity: int | None = None
    weight_kg: Decimal | None = None
    origin_country: str | None = None
    specification: str | None = None
    supplier_country: str | None = None
    supplier_address: str | None = None
    supplier_phone: str | None = None
    checklist: str | None = None
    bid_amount: Decimal | None = None


@dataclass(frozen=True)
class ValidatedOrderRequest:
    customer_id: int
    service_code: str
    channel: str
    submission_intent: str
    items: tuple[ValidatedOrderItem, ...]
    customer_notes: str | None
    request_hash: str


def resolve_submission_intent(channel: str, submit: bool | None) -> str | OrderValidationFailure:
    """Map a create flag to draft or submit. WhatsApp is always submit."""
    if channel == "whatsapp":
        if submit is False:
            return _fail("channel_rejected")
        if submit is True or submit is None:
            return SUBMISSION_SUBMIT
        return _fail("channel_rejected")
    if channel != "staff" or (submit is not True and submit is not False):
        return _fail("channel_rejected")
    if submit:
        return SUBMISSION_SUBMIT
    return SUBMISSION_DRAFT


def canonical_request_document(
    *,
    customer_id: int,
    service_code: str,
    channel: str,
    submission_intent: str,
    items: Sequence[ValidatedOrderItem],
    customer_notes: str | None,
) -> dict[str, Any]:
    """Build the hashed document. Excluded fields have no key here."""
    if submission_intent not in SUBMISSION_INTENTS:
        raise OrderValidationError("submission intent must be draft or submit")
    return {
        "customer_id": customer_id,
        "service_code": service_code,
        "channel": channel,
        "submission_intent": submission_intent,
        "items": [_item_document(item) for item in items],
        "notes": customer_notes,
    }


def canonical_request_json(
    *,
    customer_id: int,
    service_code: str,
    channel: str,
    submission_intent: str,
    items: Sequence[ValidatedOrderItem],
    customer_notes: str | None,
) -> str:
    document = canonical_request_document(
        customer_id=customer_id,
        service_code=service_code,
        channel=channel,
        submission_intent=submission_intent,
        items=items,
        customer_notes=customer_notes,
    )
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_request_hash(
    *,
    customer_id: int,
    service_code: str,
    channel: str,
    submission_intent: str,
    items: Sequence[ValidatedOrderItem],
    customer_notes: str | None,
) -> str:
    """SHA-256 hex of the canonical JSON. Decimal values stay exact strings."""
    encoded = canonical_request_json(
        customer_id=customer_id,
        service_code=service_code,
        channel=channel,
        submission_intent=submission_intent,
        items=items,
        customer_notes=customer_notes,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_order_request(
    *,
    customer_id: int,
    service_code: str,
    channel: str,
    submit: bool | None,
    items: Sequence[Mapping[str, Any]],
    customer_notes: str | None = None,
) -> ValidatedOrderRequest | OrderValidationFailure:
    """Validate one create body and hash it. The first failure is the only result."""
    if isinstance(customer_id, bool) or not isinstance(customer_id, int) or customer_id < 1:
        raise OrderValidationError("customer_id must be a positive integer")
    if customer_notes is not None and not isinstance(customer_notes, str):
        raise OrderValidationError("customer_notes must be a string or null")
    if not isinstance(items, (list, tuple)):
        raise OrderValidationError("items must be a list")

    intent = resolve_submission_intent(channel, submit)
    if isinstance(intent, OrderValidationFailure):
        return intent
    if service_code not in SERVICE_CODES:
        return _fail("service_unknown")
    if len(items) == 0:
        if intent == SUBMISSION_SUBMIT:
            return _fail("items_required")
    elif len(items) > MAX_SERVICE_ORDER_ITEMS:
        return _fail("items_above_maximum")

    validated_items: list[ValidatedOrderItem] = []
    for raw in items:
        if not isinstance(raw, Mapping):
            raise OrderValidationError("each item must be an object")
        validated = _validate_item(service_code, raw)
        if isinstance(validated, OrderValidationFailure):
            return validated
        validated_items.append(validated)

    minimum_quantity, maximum_weight = _TOTAL_LIMITS[service_code]
    if validated_items and minimum_quantity is not None:
        total_quantity = 0
        for item in validated_items:
            if item.quantity is None:
                return _fail("quantity_required")
            total_quantity += item.quantity
        if total_quantity < minimum_quantity:
            return _fail("quantity_below_minimum")
    if validated_items and maximum_weight is not None:
        total_weight = Decimal("0")
        for item in validated_items:
            if item.weight_kg is None:
                return _fail("weight_required")
            total_weight += item.weight_kg
        if total_weight > maximum_weight:
            return _fail("weight_above_maximum")

    stored = tuple(validated_items)
    return ValidatedOrderRequest(
        customer_id=customer_id,
        service_code=service_code,
        channel=channel,
        submission_intent=intent,
        items=stored,
        customer_notes=customer_notes,
        request_hash=canonical_request_hash(
            customer_id=customer_id,
            service_code=service_code,
            channel=channel,
            submission_intent=intent,
            items=stored,
            customer_notes=customer_notes,
        ),
    )


def _fail(code: str) -> OrderValidationFailure:
    return OrderValidationFailure(code=code, error=ORDER_MESSAGES[code])


def _validate_item(service_code: str, raw: Mapping[str, Any]) -> ValidatedOrderItem | OrderValidationFailure:
    required = _REQUIRED_FIELDS[service_code]
    values: dict[str, Any] = {}
    for field in _ITEM_FIELDS:
        present = field in raw and raw[field] is not None
        if field == "product_name" or field in required:
            parsed = _required_field(field, raw.get(field))
        elif not present:
            parsed = None
        else:
            parsed = _optional_field(field, raw[field])
        if isinstance(parsed, OrderValidationFailure):
            return parsed
        values[field] = parsed
    return ValidatedOrderItem(**values)


def _required_field(field: str, value: Any) -> Any:
    if field in _TEXT_FIELDS:
        if not isinstance(value, str) or value.strip() == "":
            return _fail(_MISSING_CODES[field])
        return value
    if field == "product_url":
        if not isinstance(value, str) or value.strip() == "":
            return _fail("product_url_required")
        if not _http_url(value):
            return _fail("product_url_invalid")
        return value
    if field == "quantity":
        if value is None:
            return _fail("quantity_required")
        if not _whole_quantity(value):
            return _fail("quantity_invalid")
        return value
    if field == "weight_kg":
        if value is None:
            return _fail("weight_required")
        return _positive_decimal(value, WEIGHT_SCALE, "weight_invalid")
    if field == "bid_amount":
        if value is None:
            return _fail("bid_required")
        return _positive_decimal(value, BID_SCALE, "bid_invalid")
    raise OrderValidationError("unknown item field")


def _optional_field(field: str, value: Any) -> Any:
    if field in _TEXT_FIELDS:
        if not isinstance(value, str) or value.strip() == "":
            return _fail(_MISSING_CODES[field])
        return value
    if field == "product_url":
        if not isinstance(value, str) or not _http_url(value):
            return _fail("product_url_invalid")
        return value
    if field == "quantity":
        if not _whole_quantity(value):
            return _fail("quantity_invalid")
        return value
    if field == "weight_kg":
        return _positive_decimal(value, WEIGHT_SCALE, "weight_invalid")
    if field == "bid_amount":
        return _positive_decimal(value, BID_SCALE, "bid_invalid")
    raise OrderValidationError("unknown item field")


def _whole_quantity(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 1


def _positive_decimal(value: Any, scale: int, invalid_code: str) -> Decimal | OrderValidationFailure:
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        return _fail(invalid_code)
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -scale or value <= 0:
        return _fail(invalid_code)
    return value


def _http_url(value: str) -> bool:
    if value.strip() != value or any(character.isspace() for character in value):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and parsed.hostname is not None and parsed.hostname != ""


def _item_document(item: ValidatedOrderItem) -> dict[str, Any]:
    return {
        "product_name": item.product_name,
        "product_url": item.product_url,
        "quantity": item.quantity,
        "weight_kg": None if item.weight_kg is None else format(item.weight_kg, "f"),
        "origin_country": item.origin_country,
        "specification": item.specification,
        "supplier_country": item.supplier_country,
        "supplier_address": item.supplier_address,
        "supplier_phone": item.supplier_phone,
        "checklist": item.checklist,
        "bid_amount": None if item.bid_amount is None else format(item.bid_amount, "f"),
    }

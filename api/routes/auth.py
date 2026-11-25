"""Customer registration, login, and logout."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.models import Customer, Session
from api.security import (
    COOKIE_NAME,
    CUSTOMER_PASSWORD_MIN,
    EMAIL_PATTERN,
    PASSWORD_MAX,
    attach_session_cookie,
    clear_session_cookie,
    direct_client_ip,
    error_response,
    get_throttle,
    hash_password,
    hash_token,
    logger,
    new_session_token,
    origin_allowed,
    session_expiry,
    session_scope,
    verify_password,
)

REGISTER_FIELDS = frozenset({"email", "password", "name", "phone"})
LOGIN_FIELDS = frozenset({"email", "password"})
NAME_MAX = 100
PHONE_MAX = 40


def _json_object(raw: bytes) -> dict | None:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _bad_shape(data: dict, allowed: frozenset[str]) -> bool:
    for key, value in data.items():
        if key not in allowed or not isinstance(value, str):
            return True
    return False


def _gate(request: Request) -> JSONResponse | str:
    ip = direct_client_ip(request)
    if ip is None:
        return error_response(403, "client_address_required")
    if not origin_allowed(request):
        return error_response(403, "origin_rejected")
    if get_throttle().blocked(ip):
        return error_response(429, "too_many_requests")
    return ip


def _registration_code(data: dict) -> str | None:
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    phone = data.get("phone", "")
    if not isinstance(email, str) or email.strip() == "" or EMAIL_PATTERN.fullmatch(email.strip().lower()) is None:
        return "invalid_email"
    if not isinstance(password, str) or len(password) < CUSTOMER_PASSWORD_MIN:
        return "password_too_short"
    if len(password) > PASSWORD_MAX:
        return "password_too_long"
    if not isinstance(name, str) or name.strip() == "":
        return "name_required"
    if len(name.strip()) > NAME_MAX:
        return "name_too_long"
    if len(phone.strip()) > PHONE_MAX:
        return "phone_too_long"
    return None


def _customer_body(customer: Customer) -> dict:
    return {
        "role": "customer",
        "customer": {
            "id": int(customer.id),
            "email": customer.email,
            "name": customer.name,
            "phone": customer.phone,
        },
    }


def _start_customer_session(db, customer: Customer) -> str:
    token = new_session_token()
    row = Session(
        token_hash=hash_token(token),
        principal_type="customer",
        customer_id=customer.id,
        employee_id=None,
        expires_at=session_expiry(),
    )
    db.add(row)
    db.flush()
    db.execute(
        update(Session)
        .where(
            Session.principal_type == "customer",
            Session.customer_id == customer.id,
            Session.id != row.id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    return token


async def register(request: Request) -> Response:
    gate = _gate(request)
    if isinstance(gate, JSONResponse):
        return gate
    ip = gate
    data = _json_object(await request.body())
    if data is None or _bad_shape(data, REGISTER_FIELDS):
        get_throttle().record_failure(ip)
        return error_response(400, "invalid_request")
    code = _registration_code(data)
    if code == "password_too_long":
        get_throttle().record_failure(ip)
        return error_response(400, code)
    if code is not None:
        get_throttle().record_failure(ip)
        return error_response(400, code)
    email = str(data["email"]).strip().lower()
    name = str(data["name"]).strip()
    phone = str(data.get("phone", "")).strip()
    password = str(data["password"])
    with session_scope() as db:
        existing = db.scalar(select(Customer).where(Customer.email == email))
        if existing is not None:
            get_throttle().record_failure(ip)
            return error_response(409, "email_taken")
        customer = Customer(
            email=email,
            name=name,
            phone=phone,
            password_hash=hash_password(password),
        )
        db.add(customer)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            get_throttle().record_failure(ip)
            return error_response(409, "email_taken")
        token = _start_customer_session(db, customer)
        payload = _customer_body(customer)
    logger.info("register")
    response = JSONResponse(status_code=201, content=payload)
    attach_session_cookie(response, request, token)
    return response


def _login_failure(ip: str) -> JSONResponse:
    get_throttle().record_failure(ip)
    logger.info("customer_login_failed")
    return error_response(401, "invalid_credentials")


async def login(request: Request) -> Response:
    gate = _gate(request)
    if isinstance(gate, JSONResponse):
        return gate
    ip = gate
    data = _json_object(await request.body())
    if data is None or _bad_shape(data, LOGIN_FIELDS):
        return error_response(400, "invalid_request")
    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str) or len(password) > PASSWORD_MAX:
        return _login_failure(ip)
    with session_scope() as db:
        customer = db.scalar(select(Customer).where(Customer.email == email.strip().lower()))
        if customer is None or not verify_password(password, customer.password_hash):
            failed = True
            payload = None
            token = None
        else:
            failed = False
            token = _start_customer_session(db, customer)
            payload = _customer_body(customer)
    if failed:
        return _login_failure(ip)
    logger.info("customer_login")
    response = JSONResponse(status_code=200, content=payload)
    attach_session_cookie(response, request, token)
    return response


async def logout(request: Request) -> Response:
    if not origin_allowed(request):
        return error_response(403, "origin_rejected")
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return Response(status_code=204)
    with session_scope() as db:
        row = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
        usable = False
        if row is not None and row.revoked_at is None:
            expires = row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > datetime.now(timezone.utc):
                row.revoked_at = datetime.now(timezone.utc)
                usable = True
    logger.info("logout")
    if not usable:
        return Response(status_code=204)
    response = Response(status_code=200)
    clear_session_cookie(response, request)
    return response

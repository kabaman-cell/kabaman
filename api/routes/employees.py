"""Employee login. Inactive employees are indistinguishable from a bad password."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.models import Employee, Session
from api.routes.auth import LOGIN_FIELDS, _bad_shape, _gate, _json_object
from api.security import (
    PASSWORD_MAX,
    attach_session_cookie,
    error_response,
    get_throttle,
    hash_token,
    logger,
    new_session_token,
    session_expiry,
    session_scope,
    verify_password,
)


def _employee_body(employee: Employee) -> dict:
    return {
        "role": "employee",
        "employee": {
            "id": int(employee.id),
            "email": employee.email,
            "name": employee.name,
        },
    }


def _failure(ip: str) -> JSONResponse:
    get_throttle().record_failure(ip)
    logger.info("employee_login_failed")
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
        return _failure(ip)
    with session_scope() as db:
        employee = db.scalar(select(Employee).where(Employee.email == email.strip().lower()))
        if (
            employee is None
            or not employee.is_active
            or not verify_password(password, employee.password_hash)
        ):
            failed = True
            payload = None
            token = None
        else:
            failed = False
            token = new_session_token()
            row = Session(
                token_hash=hash_token(token),
                principal_type="employee",
                customer_id=None,
                employee_id=employee.id,
                expires_at=session_expiry(),
            )
            db.add(row)
            db.flush()
            db.execute(
                update(Session)
                .where(
                    Session.principal_type == "employee",
                    Session.employee_id == employee.id,
                    Session.id != row.id,
                    Session.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            payload = _employee_body(employee)
    if failed:
        return _failure(ip)
    logger.info("employee_login")
    response = JSONResponse(status_code=200, content=payload)
    attach_session_cookie(response, request, token)
    return response

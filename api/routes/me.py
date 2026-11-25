"""Current principal. An unusable cookie is anonymous, not an error."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from api.deps import AuthFailure, CustomerPrincipal, EmployeePrincipal, resolve_principal
from api.security import error_response, session_scope


async def current(request: Request) -> JSONResponse:
    with session_scope() as db:
        principal = resolve_principal(db, request)
        if principal is None:
            return JSONResponse(status_code=200, content={"role": ""})
        if isinstance(principal, AuthFailure):
            return error_response(principal.status, principal.code)
        if isinstance(principal, CustomerPrincipal):
            customer = principal.customer
            return JSONResponse(
                status_code=200,
                content={
                    "role": "customer",
                    "customer": {
                        "id": int(customer.id),
                        "email": customer.email,
                        "name": customer.name,
                        "phone": customer.phone,
                    },
                },
            )
        if isinstance(principal, EmployeePrincipal):
            employee = principal.employee
            return JSONResponse(
                status_code=200,
                content={
                    "role": "employee",
                    "employee": {
                        "id": int(employee.id),
                        "email": employee.email,
                        "name": employee.name,
                    },
                },
            )
    return JSONResponse(status_code=200, content={"role": ""})

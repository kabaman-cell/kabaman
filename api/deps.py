"""Principal dependencies for later employee routes. Sessions are not interchangeable."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from starlette.requests import Request

from api.models import Customer, Employee, EmployeeRole, Permission, Role, RolePermission, Session
from api.security import COOKIE_NAME, hash_token


@dataclass(frozen=True)
class AuthFailure:
    status: int
    code: str


@dataclass(frozen=True)
class CustomerPrincipal:
    customer: Customer


@dataclass(frozen=True)
class EmployeePrincipal:
    employee: Employee
    permissions: frozenset[str]


def _usable_session(db: DbSession, request: Request) -> Session | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    row = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    return row


def employee_permission_codes(db: DbSession, employee_id: int) -> frozenset[str]:
    codes = db.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(EmployeeRole, EmployeeRole.role_id == Role.id)
        .where(EmployeeRole.employee_id == employee_id)
    )
    return frozenset(codes)


def resolve_principal(db: DbSession, request: Request) -> CustomerPrincipal | EmployeePrincipal | AuthFailure | None:
    """Return a principal, an inactive-employee failure, or None when the cookie is unusable."""
    row = _usable_session(db, request)
    if row is None:
        return None
    if row.principal_type == "customer":
        customer = db.get(Customer, row.customer_id)
        if customer is None:
            return None
        return CustomerPrincipal(customer)
    if row.principal_type == "employee":
        employee = db.get(Employee, row.employee_id)
        if employee is None:
            return None
        db.refresh(employee)
        if not employee.is_active:
            return AuthFailure(401, "invalid_credentials")
        return EmployeePrincipal(employee, employee_permission_codes(db, employee.id))
    return None


def require_customer(db: DbSession, request: Request) -> CustomerPrincipal | AuthFailure:
    principal = resolve_principal(db, request)
    if isinstance(principal, CustomerPrincipal):
        return principal
    if isinstance(principal, AuthFailure):
        return principal
    if isinstance(principal, EmployeePrincipal):
        return AuthFailure(403, "forbidden")
    return AuthFailure(401, "unauthenticated")


def require_employee(db: DbSession, request: Request) -> EmployeePrincipal | AuthFailure:
    principal = resolve_principal(db, request)
    if isinstance(principal, EmployeePrincipal):
        return principal
    if isinstance(principal, AuthFailure):
        return principal
    if isinstance(principal, CustomerPrincipal):
        return AuthFailure(403, "forbidden")
    return AuthFailure(401, "unauthenticated")


def require_permission(db: DbSession, request: Request, code: str) -> EmployeePrincipal | AuthFailure:
    principal = require_employee(db, request)
    if isinstance(principal, AuthFailure):
        return principal
    if code not in principal.permissions:
        return AuthFailure(403, "forbidden")
    return principal

"""Create the first employee. The password is read from a hidden prompt."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from api.models import Employee, EmployeeRole, Role
from api.security import (
    BOOTSTRAP_PASSWORD_MIN,
    BOOTSTRAP_PASSWORD_TOO_SHORT,
    BOOTSTRAP_PROMPT,
    EMAIL_PATTERN,
    MESSAGES,
    PASSWORD_MAX,
    hash_password,
    logger,
    session_scope,
)

ROLE_NAMES = ("order_reviewer", "site_editor", "operator")


def _rejected_password_source(argv: list[str]) -> bool:
    if os.environ.get("KABAMAN_EMPLOYEE_PASSWORD") is not None:
        return True
    for arg in argv:
        if arg in {"-p", "--password"} or arg.startswith("--password=") or arg.startswith("-p="):
            return True
    return False


def main(argv: list[str] | None = None, password_reader: Callable[[], str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if _rejected_password_source(args):
        logger.info("bootstrap_password_rejected")
        print(BOOTSTRAP_PROMPT, file=sys.stderr)
        return 1
    positionals = [arg for arg in args if not arg.startswith("-")]
    if len(positionals) != 2:
        print("Email and name are required.", file=sys.stderr)
        return 1
    email = positionals[0].strip().lower()
    name = positionals[1].strip()
    if EMAIL_PATTERN.fullmatch(email) is None:
        print(MESSAGES["invalid_email"], file=sys.stderr)
        return 1
    if name == "":
        print(MESSAGES["name_required"], file=sys.stderr)
        return 1
    reader = password_reader
    if reader is None:
        if not sys.stdin.isatty():
            logger.info("bootstrap_password_rejected")
            print(BOOTSTRAP_PROMPT, file=sys.stderr)
            return 1
        reader = lambda: getpass("Password: ")
    password = reader()
    if len(password) < BOOTSTRAP_PASSWORD_MIN:
        logger.info("bootstrap_password_rejected")
        print(BOOTSTRAP_PASSWORD_TOO_SHORT, file=sys.stderr)
        return 1
    if len(password) > PASSWORD_MAX:
        logger.info("bootstrap_password_rejected")
        print(MESSAGES["password_too_long"], file=sys.stderr)
        return 1
    password_hash = hash_password(password)
    try:
        with session_scope() as db:
            employee = Employee(email=email, name=name, password_hash=password_hash, is_active=True)
            db.add(employee)
            db.flush()
            roles = db.scalars(select(Role).where(Role.name.in_(ROLE_NAMES))).all()
            found = {role.name for role in roles}
            if found != set(ROLE_NAMES):
                raise RuntimeError("Refusing to assign employee roles.")
            for role in roles:
                db.add(EmployeeRole(employee_id=employee.id, role_id=role.id))
    except DBAPIError:
        print("Employee could not be created.", file=sys.stderr)
        return 1
    print("Employee created.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

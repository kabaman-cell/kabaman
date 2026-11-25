# Phase 1C technical specification

This document specifies Phase 1C. It does not authorize implementation. A separate review and an explicit approval are required before any implementation begins.

Phase 1C adds customer registration, customer login, customer logout, `GET /api/me`, employee login, sessions, and the first-employee command. It uses the Phase 1A FastAPI application and the committed Phase 1B schema, revision `0001_phase1`. It adds no migration and no orders, documents, site settings, WhatsApp desk, audit writer, or storefront wiring.

Stated checkout: branch `phase-1b-test`, HEAD `916a99c`. Phase 1A is 7/7, Phase 1B is 15/15, and the full suite is 22/22. PR #4 stays open and unmerged.

Labels:

- **Approved.** A decision of the Phase 1 execution plan or a later decision applied here.
- **Current behavior.** What `server.py` or `js/api.js` does today, where Phase 1C keeps that behavior.
- **Limitation.** A boundary recorded in section 17.

The document contains one endpoint table, one schema table, one HTTP status table, one error catalog, one file matrix, and one test matrix.

## 1. Purpose and architecture boundaries

**Approved.** Customers and employees are different principals. A customer is not an employee. The shared admin password does not become a row. There is no employee self-signup, customer-delete route, or employee-delete route. Social buttons do not create users. Supabase is not imported.

**Approved.** Uvicorn stays on loopback. Public deployment is prohibited, and there is no public bind. `server.py` stays in git and is not the public process. Storefront files are not edited. The Phase 1A health response and disabled documentation stay unchanged. The `operator` role is not renamed, and its grants remain the list in section 4.

**Approved.** `api/audit.py`, `api/storage.py`, order routes, and `auth_rate_limits` are outside this phase.

## 2. Security and password handling

**Approved.** Passwords are stored only as hashes. The algorithm is `hashlib.pbkdf2_hmac` with SHA-256 and 200,000 rounds. No second password library is added.

**Current behavior.** `server.py` writes `pbkdf2_sha256$<rounds>$<salt>$<hex digest>`. The salt is `secrets.token_hex(16)`. The digest is PBKDF2-HMAC-SHA256 of the UTF-8 password with that UTF-8 salt. Verification uses `hmac.compare_digest`. Phase 1C keeps that stored form.

**Approved.** These are the only password lengths. A password longer than the maximum is rejected before PBKDF2 runs.

- Customer registration minimum: 8 characters.
- Employee bootstrap minimum: 12 characters.
- Maximum for customer registration, customer login, employee login, and the bootstrap prompt: 128 characters.

## 3. Customer registration, login, and logout

**Approved.** Email is trimmed, stored lowercase, and must match `[^@\s]+@[^@\s]+\.[^@\s]+`. Name, phone, and password outcomes are sections 2 and 10. Register and customer login each create one customer session and set the cookie. A duplicate email leaves the existing password hash unchanged. Revocation, expiry, and logout are section 5. Response bodies are section 9. Routes are section 8.

## 4. Employee authentication and authorization

**Approved.** Employee login loads the `employees` row and compares email in lowercase. `is_active` must be true. Every later use of an employee session reads `is_active` again. Inactive login and a later request on an inactive employee both return `invalid_credentials` from section 10, so unknown email, a wrong password, an over-maximum password, and an inactive employee are indistinguishable at login. The handler stops. An existing unexpired, unrevoked session loses access on the next read after `is_active` becomes false.

**Approved.** A customer cookie cannot satisfy an employee dependency. An employee cookie cannot satisfy a customer dependency. `principal_type` is `customer` with only `customer_id`, or `employee` with only `employee_id`.

**Approved.** This phase does not add order, document, site, or desk routes. `api/deps.py` supplies the permission dependency those later routes will call. A missing permission returns `forbidden` from section 10. The seeded grants stay unchanged:

- `order_reviewer`: `orders.read_all`, `orders.update_status`, `orders.reply`, `documents.read`
- `site_editor`: `site.write`
- `operator`: `orders.delete`, `whatsapp.read`, `whatsapp.write`, `audit.read`

## 5. Session lifecycle and cookie policy

**Approved.**

- Cookie name: `kabaman_session`. Attributes: `HttpOnly`, `SameSite=Lax`, `Path=/`.
- Lifetime: 14 days from creation, both on the cookie and in `sessions.expires_at`.
- The cookie value is `secrets.token_urlsafe(32)`. PostgreSQL stores only the hex SHA-256 of that value in `sessions.token_hash`. Lookup hashes the presented cookie. A copied `token_hash` is not a usable cookie.
- Logout sets `revoked_at` on the current session only. A new login revokes older sessions for that same principal. A revoked or expired cookie does not authenticate.
- `Secure` is set when the received request scheme is `https`. On loopback without TLS, `Secure` is omitted. A public host would have to set `Secure`.

**Approved.** Scheme, host, and port come from the request URL as the application receives it. `X-Forwarded-*` and every other forwarded header are ignored. Sections 6 and 11 use this rule.

## 6. CSRF and Origin validation

**Approved.** Register, customer login, employee login, and logout are state-changing. The check passes when `Origin` is present and its scheme, host, and port exactly match the section 5 request URL, or when `Origin` is absent and `Sec-Fetch-Site` is `same-origin`. Any other case returns `origin_rejected` from section 10. `GET /api/health` and `GET /api/me` are not state-changing.

## 7. Employee bootstrap command

**Approved.** Run `python -m api.bootstrap_employee`. Email and name may be arguments. They are chosen at execution and are not written in this specification. The password is read with `getpass`, or the same hidden behavior. It is not an argument, an environment variable, or a file. The command refuses `-p`, `--password`, and `KABAMAN_EMPLOYEE_PASSWORD`. Length is section 2. A short password is the CLI-only result `bootstrap_password_too_short` in section 10. That result is not an HTTP status and not an `ErrorBody`. An over-maximum password uses the `password_too_long` sentence there. Any other rejected password source uses the hidden-prompt sentence there. Refusal text never contains the entered password. The command never prints, logs, or writes the password. Only the section 2 hash is stored. It does not read `admin.config.json`.

The new employee receives `order_reviewer`, `site_editor`, and `operator`. Grants remain the section 4 list. If stdin is not a terminal and the prompt has not been replaced, the command fails with no other password source. Its database guard is section 13.

## 8. API endpoint contracts

| Method | Path | Authority |
| --- | --- | --- |
| `GET` | `/api/health` | Public. Body is only `{"ok": true}`. |
| `POST` | `/api/register` | Section 3. |
| `POST` | `/api/login` | Section 3. |
| `POST` | `/api/logout` | Section 5. |
| `POST` | `/api/employee/login` | Section 4. |
| `GET` | `/api/me` | Section 9. |
| `POST` | `/api/admin/login` | Not implemented. |
| `PATCH` | `/api/me` | Not in this phase. |

## 9. Request and response schemas

**Approved.** Pydantic models live in `api/schemas.py`. No response includes a field that is absent from this table. `ErrorBody` is defined only by its row.

| Schema | Fields |
| --- | --- |
| `CustomerRegister` | `email: str`, `password: str`, `name: str`, `phone: str = ""` |
| `CustomerLogin` | `email: str`, `password: str` |
| `EmployeeLogin` | `email: str`, `password: str` |
| `CustomerProfile` | `id: int`, `email: str`, `name: str`, `phone: str` |
| `EmployeeProfile` | `id: int`, `email: str`, `name: str` |
| `CustomerAuthResponse` | `role: "customer"`, `customer: CustomerProfile` |
| `EmployeeAuthResponse` | `role: "employee"`, `employee: EmployeeProfile` |
| `AnonymousMe` | `role: ""` |
| `ErrorBody` | Required `code: str` and required `error: str`, and no other field. `code` and `error` are one section 10 pair. They contain no password, token, hash, cookie, submitted value, address, header, SQL, path, or stack trace. |

**Approved.** Register and customer login return `CustomerAuthResponse`. The customer object is present only for a customer session. Employee login returns `EmployeeAuthResponse`. `GET /api/me` returns `AnonymousMe`, `CustomerAuthResponse`, or `EmployeeAuthResponse` according to the session. Unknown fields return `invalid_request` from section 10. A validation error does not echo the submitted password. The raw token is carried only by the section 5 cookie.

**Current behavior.** `js/api.js` reads `role`. The current client treats an empty role as signed out.

## 10. HTTP status codes and error catalog

**Approved.** Values are trimmed before their length is measured. Length is the number of Unicode code points. Omitted or blank phone is stored as `''`. Name and phone limits are `name_too_long` and `phone_too_long` below. A value over either limit is rejected and creates no customer row. Accepted name and phone are stored as the trimmed values.

When several registration inputs fail, the earliest registration order below is the only pair returned. When several login inputs fail, the earliest login order is the only pair returned. Registration and login pairs are selected only after section 11 allows authentication. A result in the status table that has no catalog code has no `ErrorBody`. `too_many_requests` includes no retry time, remaining count, or client address. `bootstrap_password_too_short` is a CLI-only result. It is not an `ErrorBody` code, it has no HTTP status, and its sentence is not the HTTP `password_too_short` sentence. The hidden-prompt sentence is also command text, not HTTP.

| Result | Status |
| --- | --- |
| `invalid_request`, `invalid_email`, `password_too_short`, `password_too_long`, `name_required`, `name_too_long`, `phone_too_long` | 400 |
| `email_taken` | 409 |
| `invalid_credentials`, `unauthenticated` | 401 |
| `GET /api/me` with no usable session, as `AnonymousMe` | 200 |
| `forbidden`, `origin_rejected`, `client_address_required` | 403 |
| `too_many_requests` | 429 |
| Register success | 201 |
| Login success | 200 |
| Logout with a usable cookie | 200 |
| Logout with no usable cookie | 204 |
| `POST /api/admin/login` | 404 |

| Code | When it applies | `error` |
| --- | --- | --- |
| `invalid_request` | Registration order 1, or login order 1: the body is not a JSON object, a field has the wrong JSON type, or an unknown field is present | The request is invalid. |
| `invalid_email` | Registration order 2: email is missing, blank, or fails section 3 | Enter a valid email. |
| `password_too_short` | Registration order 3: the password is missing or below the section 2 customer minimum | Use a password of at least 8 characters. |
| `password_too_long` | Registration order 4, or a bootstrap password above the section 2 maximum | Use a password of at most 128 characters. |
| `name_required` | Registration order 5: name is missing or blank | Add your name. |
| `name_too_long` | Registration order 6: trimmed name is longer than 100 characters, the current `server.py` maximum | Use a name of at most 100 characters. |
| `phone_too_long` | Registration order 7: trimmed phone is longer than 40 characters, the current `server.py` maximum | Use a phone number of at most 40 characters. |
| `email_taken` | Registration order 8: the email is already registered | An account with that email already exists. |
| `invalid_credentials` | Login order 2: unknown email, wrong password, password above the section 2 maximum, or inactive employee. Also the next read of an employee session whose `is_active` is false | Email or password is incorrect. |
| `unauthenticated` | A route requires a principal, the session is missing or unusable, and the route is not `GET /api/me` | Sign in to continue. |
| `forbidden` | The employee lacks the required permission | You do not have permission to do that. |
| `origin_rejected` | The section 6 check failed | The request origin is not allowed. |
| `client_address_required` | A section 11 route has no direct client IP | A direct client address is required. |
| `too_many_requests` | The section 11 block applies | Too many attempts. Try again later. |
| `bootstrap_password_too_short` | CLI only, not an HTTP status and not an `ErrorBody`: the bootstrap password is below the section 2 bootstrap minimum | Use a password of at least 12 characters. |
| Bootstrap prompt | The bootstrap password was not read from the hidden prompt | Enter the password at the hidden prompt. |

## 11. IP-based throttling

**Approved.** This policy is temporary in-process protection. It is not a production-grade rate limit. It resets when the process restarts, and each process has its own counters. `auth_rate_limits` and Redis are not added. Tests inject a clock and do not sleep. Tests and docstrings state the section 17 limitation.

The policy applies to `POST /api/register`, `POST /api/login`, and `POST /api/employee/login`. It does not apply to logout, `GET /api/me`, or `GET /api/health`.

On those three routes the checks run in this order: direct client address, the section 6 origin check, this throttle, then authentication. The throttle key is that direct client IP. Section 5 forbids substituting a forwarded header.

- A missing direct client address returns `client_address_required`. It does not authenticate and records no failure.
- Counted failures already inside the rolling 15-minute window are checked before authentication. A window that already holds 0, 1, 2, 3, or 4 counted failures does not block. That request runs authentication. If it is a counted failure, it is recorded and returns its own 400, 409, or 401. The fifth recorded failure is allowed: it is not a block, and the window then holds exactly five counted failures.
- The next request is blocked only because five counted failures are already recorded. That request is the sixth. It does not authenticate, does not record a sixth failure, starts a 15-minute block for that IP on these three routes, and returns `too_many_requests`. The recorded count stays 5. The throttle test in section 15 verifies this sequence.
- During the block, further requests to those routes return `too_many_requests` again. They do not authenticate, record another failure, or extend the block.
- When the block ends, that IP's failure list is empty.
- `origin_rejected` and `client_address_required` do not count as failures.
- Counted failures are a registration response of 400 or 409, and a customer or employee login response of 401. A login response of `invalid_request` does not count.
- A success does not clear failures still inside the 15-minute window.

## 12. Logging and sensitive-data protection

**Approved.** Logs omit request bodies, cookies, the `Authorization` header, passwords, raw tokens, and token hashes. The section 7 command follows the same rule. Uvicorn access logs stay off. This phase does not add `api/audit.py`. Login audit rows are Phase 1H. The captured cases are register, both logins, logout, a rejected bootstrap password, and a failed login.

## 13. Database isolation and safety guards

**Approved.** This specification does not create the database. Before any socket, all of the following hold:

- `DATABASE_URL` parses.
- The database name is exactly `kabaman_phase1c_test`. `kabaman_os` and `kabaman_phase1b_test` are refused.
- The host is `127.0.0.1`, `localhost`, or `::1`, and the port is explicitly `5432`.
- The first SQL reads `current_database()`, `host(inet_server_addr())`, and `inet_server_port()`.
- Work continues only when that database name is `kabaman_phase1c_test`, the server address is `127.0.0.1` or `::1`, and the port is `5432`. Any other result closes the connection and does not open another database.

Phase 1C tests may create and drop the schema only inside `kabaman_phase1c_test`, using revision `0001_phase1`. They add no migration. They do not run `DROP`, `ALTER`, or `TRUNCATE` against `kabaman_phase1b_test`, and they do not import the Phase 1B database fixture. The Phase 1A and Phase 1B tests stay unchanged.

## 14. File change matrix

| File | Action | Responsibility |
| --- | --- | --- |
| `api/security.py` | Create | Sections 2, 5, 6, and 11 |
| `api/deps.py` | Create | Section 4 |
| `api/schemas.py` | Create | Section 9 |
| `api/routes/auth.py` | Create | Section 3 |
| `api/routes/employees.py` | Create | Section 4 |
| `api/routes/me.py` | Create | `GET /api/me` |
| `api/bootstrap_employee.py` | Create | Section 7 |
| `api/main.py` | Modify | Register the three routers. Leave the section 1 health response and disabled docs unchanged. |
| `tests/test_auth.py` | Create | Section 15 |
| `api/models.py` | Do not modify | Phase 1B schema |
| `alembic/versions/0001_phase1.py` | Do not modify | Revision `0001_phase1` |
| `tests/test_phase1b.py`, `tests/conftest.py` | Do not modify | Existing suite |
| `tests/test_phase1a.py` | Modify only `test_health_is_the_only_route` | Keep `GET /api/health` returning `{"ok": true}`. Remove only the assertion that this is the sole route. |
| `server.py` and storefront files | Do not modify | Section 1 |

## 15. Test matrix

Every Phase 1C test uses section 13. A row passes when the cited behavior holds, including the captured-log rule in section 12 for authentication tests.

| Test | Behavior under test |
| --- | --- |
| Database guard | Section 13 |
| Register success | Sections 2, 3, 5, and 9 |
| Register validation | Section 10 registration orders 2 through 7 |
| Duplicate email | Section 3 duplicate-email rule and section 10 `email_taken` |
| Customer login | Sections 5 and 10 |
| Bad customer login | Section 10 `invalid_credentials` |
| Logout | Section 5 |
| Logout without a usable cookie | Section 10 |
| Expired cookie | Section 5 |
| Revoked cookie | Section 5 |
| Copied hash | Section 5 |
| Session swap | Section 4 |
| Employee login | Sections 4 and 9 |
| Inactive login | Section 4 |
| Deactivated session | Section 4 |
| Admin login absent | Section 8 and section 10 |
| Current principal | Section 9 |
| Origin | Section 6 |
| Bootstrap | Section 7 |
| Throttle | Section 11. Counted failures 1 through 5 return their own failure status and are recorded. The next request returns `too_many_requests`, does not authenticate, and does not record a sixth failure. |
| Logs | Section 12 |
| Schema unchanged | Section 14 migration row |
| Regression | The existing 22 tests pass with the authorized `test_health_is_the_only_route` adjustment. `GET /api/health` still returns `{"ok": true}` while the five Phase 1C routes may be registered. No diff in the section 14 rows marked "Do not modify". |

## 16. Acceptance criteria

Phase 1C is accepted only when all three of the following hold: every Phase 1C test in section 15 passes, the existing 22 tests still pass with the authorized adjustment to `test_health_is_the_only_route`, and every section 14 row marked "Do not modify" is unchanged.

## 17. Risks and limitations

**Limitation.**

- The section 11 throttle is per process, is not shared across workers, and is not a public-launch control. Public deployment still waits on `auth_rate_limits`.
- Public hostname and TLS are outside Phase 1C. They keep public deployment prohibited. They do not block loopback Phase 1C, and this document does not decide them.
- Login audit rows and audit retention remain Phase 1H and the legal review. This phase adds no retention column.
- A password already stored by `server.py` that exceeds the section 2 maximum cannot pass the new check. The stored PBKDF2 format is unchanged.

No Phase 1C decision remains open.

## 18. Safe implementation sequence

This sequence stays blocked until the approval required at the start of this document.

1. Create the section 13 database. This document does not create it.
2. Add the section 14 files in the order that matrix lists them.
3. Add the section 15 tests.
4. Re-run the existing 22 tests on their current database, then run the Phase 1C tests on the section 13 database.
5. Stop. Do not start Phase 1D or merge PR #4.

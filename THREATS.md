# LedgerLine Threat Model and Security Review

**Review date:** 2026-11-07  
**System boundary:** Internal demonstration ledger API and browser client. No bank, UPI, card, NEFT, RTGS, or payment-provider settlement is in scope.

## 1. System assets and trust boundaries

Assets include user credentials and bearer tokens, account ownership and status,
integer-paise balances, journal transactions and entries, idempotency records,
audit events, signing/database secrets, and migration history.

The browser is an untrusted client. FastAPI is the authorization and business
logic boundary. PostgreSQL constraints, triggers, and privileges are the
persistence integrity boundary. Local Docker Compose is a development
deployment, not a production network design. Alembic uses a separate privileged
database URL; API requests use the restricted runtime role.

LedgerLine deposits are internally balanced against a clearing ledger account,
but are not backed by external funding. Ledger balances must not be represented
or used as real funds.

## 2. Actors and attacker capabilities

- Anonymous internet or local-network users can submit public authentication
  requests and unauthenticated API requests.
- Authenticated account holders can manipulate their own requests and attempt
  to access other users' resources or replay operations.
- Administrators can perform explicitly authorized account and reversal
  operations; a compromised administrator can misuse those permissions.
- Auditors have read-only product permissions.
- A host or database administrator can alter the local database and its
  controls. Database superusers are outside the protection boundary of
  application-level immutability triggers.

## 3. Attack surface

FastAPI authentication, account, transaction, statement, and audit endpoints;
JWT handling; request schemas; SQLAlchemy repositories and services; Alembic
migrations and PostgreSQL triggers; Compose networking and database roles;
frontend bearer-token handling, role-aware routes, and idempotent retry
workflow.

## 4. Threat register

| ID | Asset | Threat | Attack scenario | Impact | Severity | Mitigation | Test reference | Status |
|---|---|---|---|---|---|---|---|---|
| T-01 | User accounts | Credential or token compromise | Attacker guesses credentials or submits malformed, expired, or tampered JWTs. | Account takeover or unauthorized API access. | High | Argon2 password hashes; JWT signature, algorithm, required-claim, expiry, and disabled-user checks; authentication outcomes recorded without credentials. | `backend/tests/test_auth.py` | Implemented and tested; Phase 2 added malformed, tampered, wrong-algorithm, missing-claim, expired, and disabled-user-token checks. |
| T-02 | Account and statement data | Cross-user IDOR | Account holder substitutes another user's account UUID in details, statements, transactions, or mutation requests. | Unauthorized disclosure or action. | High | Backend ownership checks and role-scoped queries. | `backend/tests/test_accounts_postgres.py`; `backend/tests/test_transactions_postgres.py` | Implemented and tested in final PostgreSQL backend run. |
| T-03 | User roles and account ownership | Mass assignment / privilege escalation | User supplies privileged role or owner/balance fields at public registration or account creation. | Unauthorized administration or balance changes. | High | Explicit schemas; public signup assigns account-holder role; account APIs reject writable fields. | `backend/tests/test_auth.py`; `backend/tests/test_accounts_postgres.py` | Implemented and tested in final backend run. |
| T-04 | Database queries | SQL injection | Attacker submits SQL metacharacters in API input. | Data disclosure or modification. | High | SQLAlchemy parameterized queries and typed request validation. | API validation tests in `backend/tests/` | No injection finding identified by code review; no dedicated adversarial injection test result recorded. |
| T-05 | Balances and journals | Invalid amount / overflow | Attacker submits zero, negative, or out-of-range paise values. | Invalid balance or accounting state. | High | Positive bounded integer schemas; database balance checks. | `backend/tests/test_transactions_postgres.py` | Implemented and tested in final PostgreSQL backend run. |
| T-06 | Posted transactions | Partial financial posting | Failure occurs between balance update, journal/entry writes, idempotency record, or success audit. | Unbalanced ledger or lost/duplicate value. | Critical | Posting and success audit share a database transaction; database constraints/triggers protect journal integrity. | Rollback and ledger-invariant tests in `backend/tests/test_transactions_postgres.py` | Implemented and tested in final PostgreSQL backend run. |
| T-07 | Account balances | Concurrent overspend | Concurrent withdrawals or transfers race on the same balance. | Negative or overstated balances. | Critical | Deterministic account-row locking and PostgreSQL transactions. | Concurrent withdrawal/transfer tests in `backend/tests/test_transactions_postgres.py` | Implemented and tested in final PostgreSQL backend run. |
| T-08 | Idempotency records | Replay / duplicate posting | A client retries or concurrently submits the same key, or reuses it with a changed payload. | Duplicate posting or a misleading result. | High | User-scoped idempotency, request hash, advisory transaction lock, and unique constraints. | Idempotency replay/concurrency tests in `backend/tests/test_transactions_postgres.py`; frontend `sessionStorage` retry tests | Implemented and tested in final backend and frontend runs. |
| T-09 | Posted journals | Unauthorized or duplicate reversal | Account holder reverses a transaction or administrator retries a reversal. | Unauthorized or repeated compensating entries. | High | Admin-only reversal, reversal linkage, idempotency, immutable original entries. | Reversal tests in `backend/tests/test_transactions_postgres.py` | Implemented and tested in final PostgreSQL backend run. |
| T-10 | Ledger and balances | Direct database tampering | Runtime API credentials attempt DDL, role changes, ownership edits, or direct balance edits. | Bypass of application authorization and accounting controls. | Critical | Runtime has column-limited writes, no migration-history/DDL/role-creation privileges, and database consistency triggers. Role is a trusted backend identity, not an end-user identity. | Live PostgreSQL direct-SQL probes; `test_runtime_cannot_mutate_protected_records_or_ddl`; trigger SQLSTATE assertion | Restrictive grants verified. Direct account-owner assignment on INSERT remains a documented residual trust boundary. |
| T-11 | Audit history | Missing or mutable audit records | Account changes, login attempts, or protected operations are not attributable or are altered. | Reduced accountability or hidden security/administrative action. | Medium | Actor/action/outcome events cover auth outcomes, account creation/status changes, role/auth denials, and service-level financial attempts; database trigger blocks normal audit-record mutation. Anonymous events omit credentials and submitted email. | `backend/tests/test_auth.py`; `backend/tests/test_accounts_postgres.py`; `backend/tests/test_transactions_postgres.py` | Implemented and covered by PostgreSQL/SQLite regression tests. |
| T-12 | Logs and errors | Secret or credential leakage | Passwords, JWTs, or database credentials appear in logs or responses. | Credential theft. | High | Secret settings; API schemas exclude password hashes; logging avoids credential values. | `backend/tests/test_auth.py`; logging/config review | No leakage finding identified; dedicated log-capture test not recorded. |
| T-13 | API availability | Brute force / resource exhaustion | Attacker repeatedly invokes login or expensive list/query endpoints. | Degraded or unavailable service. | Medium | Request limits and pagination caps bound some query sizes. | No rate-limit test identified. | Residual risk: application-level login throttling/rate limiting is not implemented. |
| T-14 | Browser session | Token theft / XSS | Malicious script reads a bearer token or attacker uses a compromised browser session. | Authenticated actions as the victim. | High | Access token is held in memory, not localStorage; frontend guards are not treated as backend authorization. | Frontend auth tests; no dedicated XSS suite identified. | Residual risk: bearer tokens remain accessible to same-origin script; no HttpOnly-cookie or refresh endpoint exists. |
| T-15 | Financial operation | Ambiguous retry / double submit | Network timeout causes a client to retry with a newly generated key or altered payload. | Duplicate or uncertain posting. | High | Confirmation before submission; unchanged ambiguous retries retain the original key and payload; double-submit guard. | `frontend/src/pages/MoneyActionPage.test.tsx`; idempotency utility tests | Implemented; frontend suite passed 16 tests in review. |
| T-16 | Service cross-origin boundary | CORS / CSRF | Attacker-hosted page attempts cross-origin API calls. | Unauthorized actions or data exposure. | Medium | Explicit configured CORS origins; bearer authentication; credentialed CORS disabled. | `backend/tests/test_health.py` | Implemented; health/CORS tests passed in the 56-test backend run. |
| T-17 | Database network and roles | Exposed superuser database | A reachable host interface exposes PostgreSQL; compromised/guessed bootstrap credentials permit trigger or role changes. | Full database compromise and integrity-control bypass. | Medium | Compose binds port 5433 to loopback; app uses a separate non-superuser role; bootstrap role is reserved for migrations. | `docker compose config --quiet`; live `rolsuper` and privilege verification | Implemented and verified on the local Compose database; external firewall/network policy remains unassessed. |
| T-18 | Account availability | Frozen/closed state bypass | User attempts an operation on a frozen/closed account or admin reactivates a closed account. | Unauthorized account activity. | High | Service validates active state; closed accounts cannot be reactivated. | Account/transaction status tests in `backend/tests/` | Implemented and tested in final PostgreSQL backend run. |
| T-19 | Ledger meaning | Unbacked internal deposits | Account holder posts an internal deposit without external funding evidence. | Internal balance may be mistaken for real or redeemable funds. | Medium | Product disclosure states transactions are internal and do not move real money; INR clearing entries preserve internal double-entry balance. | Product-copy/frontend tests | Residual product boundary: no funding authorization or settlement exists; misrepresenting these balances as real funds would create severe risk. |
| T-20 | Browser and deployment configuration | Unsafe frontend data/configuration | Attacker or operator exposes a secret through `VITE_*`, browser storage, or permissive hosting configuration. | Secret disclosure or client compromise. | Medium | No frontend secrets; `.env` is ignored; frontend docs describe bearer limitations and deployment CORS. | Frontend tests/build and `npm audit` | Frontend tests/typecheck/lint passed in review; deployment-specific hosting configuration was not assessed. |
| T-21 | Access-token lifetime | JWT without expiration | A token signed without `exp` is accepted and remains valid indefinitely, including after intended access-token lifetime. | Long-lived authenticated access if a trusted token issuer omits expiry. | Medium | Require `sub`, `iat`, and `exp` during JWT decode; retain fixed HS256 allowlist and current-user status check. | `backend/tests/test_auth.py::test_jwt_missing_required_time_claim_is_rejected` | Confirmed before fix (token without `exp` returned 200); fixed and regression-tested. |

## 5. Attack scenarios

The primary confirmed review findings were:

1. **Unattributed account status change:** an authorized but compromised
   administrator freezes or closes a customer's account. Before remediation,
   the status update committed without an audit event. The service now writes
   an `ACCOUNT_STATUS_CHANGED` event containing actor, target, previous state,
   and new state in the same commit as the update.
2. **Database privilege/network exposure:** if PostgreSQL is reachable from
   another host and bootstrap credentials are compromised, a superuser can
   disable database controls. Compose now publishes only on loopback; API
   connections use a separately provisioned non-superuser role. The local
   role and loopback port binding were verified; external firewall rules were
   not assessed.
3. **Synthetic deposit interpretation:** a signed-in holder can increase an
   internal account balance through a deposit request. This is expected demo
   behavior, not external funding. It becomes a severe product risk if these
   balances are represented as cash or connected to real payouts.

Other threat paths are documented in the register and tested where noted;
unverified tests and environment-specific assumptions are not presented as
proven controls.

## 6. Phase 2 route authorization matrix

| Method and endpoint | Anonymous | ACCOUNT_HOLDER | ADMIN | AUDITOR | Additional scope |
|---|---|---|---|---|---|
| `GET /health` | Allowed | Allowed | Allowed | Allowed | Liveness only. |
| `POST /api/v1/auth/register`, `POST /api/v1/auth/login` | Allowed | Allowed | Allowed | Allowed | Registration assigns account-holder role; extra fields are rejected. |
| `GET /api/v1/auth/me` | Denied | Allowed | Allowed | Allowed | User is resolved from the signed token subject and current database status. |
| `POST /api/v1/accounts` | Denied | Allowed | Denied | Denied | Creates an account only for the authenticated holder; no writable account fields. |
| `GET /api/v1/accounts`, `GET /api/v1/accounts/{id}` | Denied | Allowed | Allowed | Allowed | Holders see their own accounts; admin/auditor can inspect all accounts. |
| `PATCH /api/v1/accounts/{id}/status` | Denied | Denied | Allowed | Denied | Admin-only. |
| `POST /api/v1/transactions/deposits`, `/withdrawals`, `/transfers` | Denied | Allowed | Denied | Denied | Service requires account-holder role; source/mutation account ownership checked. Transfers may legitimately target another LedgerLine holder's account. |
| `POST /api/v1/transactions/{id}/reverse` | Denied | Denied | Allowed | Denied | Admin-only in the service. |
| `GET /api/v1/transactions`, `GET /api/v1/accounts/{id}/statement` | Denied | Allowed | Allowed | Allowed | Holder results are owner-scoped; account identifiers are checked. |
| `GET /api/v1/audit-events` | Denied | Denied | Allowed | Allowed | Read-only admin/auditor access. |

This matrix was derived from route dependencies and service checks, then
exercised through the FastAPI test client against PostgreSQL-backed fixtures.
Frontend route guards are not an authorization boundary.

## 7. Existing mitigations

Backend controls include Argon2 password hashing, signed expiring JWTs,
role/ownership checks, typed schemas, integer-paise amounts, PostgreSQL
transactions, account locking, idempotency keys, balanced journals,
compensating reversals, database constraints/triggers, and append-only audit
controls. Frontend controls include role-aware navigation, explicit operation
confirmation, exact-key retry for ambiguous outcomes, and no fabricated
financial data. Frontend checks do not replace backend authorization.

## 8. Automated verification evidence

Verification on 2026-11-07 after the least-privilege migration:

- The existing PostgreSQL 17.11 `ledgerline.public` database was at revision
  `20261107_0004`, with one revision row and no account/customer-ledger
  ownership mismatches. It was upgraded additively to
  `20261107_0005` (`HEAD`); no tables or Docker volumes were dropped or reset.
- `.\.venv\Scripts\alembic.exe current` and `heads` report
  `20261107_0005` as the sole head. `.\.venv\Scripts\alembic.exe check`
  reports no new upgrade operations.
- Before Phase 2, `.\.venv\Scripts\python.exe -m pytest -q` reported
  **44 passed**. Phase 2 added API attack regressions; the final command
  `.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q` from the
  repository root reported **56 passed**, with one Starlette `TestClient`
  deprecation warning. PostgreSQL account and transaction tests used actual
  `ledgerline_app` credentials in generated isolated schemas; no database
  volume was reset.
- Before migration, measured table grants were: `users` and `accounts`
  `SELECT, INSERT`; `alembic_version` `SELECT, INSERT, UPDATE`; and
  `audit_events`, `idempotency_records`, `journal_transactions`,
  `ledger_accounts`, and `ledger_entries` `SELECT, INSERT, UPDATE`.
  Default ACLs also gave the runtime role `INSERT/SELECT/UPDATE` on future
  tables and `SELECT/USAGE` on future sequences.
- After migration, the runtime has table-level `SELECT` on the seven
  application tables and no privilege on `alembic_version`. Column-level
  `INSERT` is limited to the required fields for users, accounts, ledger
  accounts, journals, entries, idempotency, and audit. Account `UPDATE` is
  limited to `balance_paise`, `status`, and `updated_at`. There are no sequence
  grants; future tables and sequences receive no runtime grants. Only two
  application functions are executable by the runtime: journal posting and
  the reversal row-lock helper.
- Direct SQL probes against the live public schema, connected as
  `ledgerline_app`, verified 16 prohibited role, ownership, immutability,
  migration-history, schema-creation, and role-creation operations fail with
  SQLSTATE `42501`. A direct inconsistent balance update reached the database
  trigger and failed with `P0001`, distinguishing trigger rejection from a
  permission denial. The generated temporary-schema suite separately proves
  runtime role insertion cannot specify `ADMIN`.
- The role has no superuser, `CREATEDB`, or `CREATEROLE` attribute, no role
  memberships, and no database/schema `CREATE` privileges. Alembic now
  requires `MIGRATION_DATABASE_URL` and rejects `ledgerline_app`.

The exact table/column grant matrix and residual trust boundaries are also
recorded in [README.md](./README.md).

Frontend checks on this run: `npm run lint`, `npm run typecheck`, `npm test`
(8 files, 16 tests), and `npm run build` all passed from `frontend/`.
`npm audit --audit-level=low` reported **0 vulnerabilities**.

## 9. Residual risks and limitations

- Local Compose configuration is not production deployment hardening.
- Bootstrap/migration credentials remain highly privileged and must be kept
  private. They are read only by Alembic/test setup, not loaded into the
  FastAPI `Settings` object. Production should inject them only into a separate
  migration job, not the running API process.
- External firewall rules, TLS, backups, restore procedures, secret rotation,
  and hosting rules require environment-specific verification.
- Login throttling/rate limiting is not implemented.
- The bearer token is memory-only but remains accessible to same-origin
  JavaScript; no HttpOnly cookie or refresh endpoint exists.
- Deposit clearing is synthetic and provides no external-funding evidence.
- A database superuser or host administrator can bypass database-level
  application protections.
- Account and customer-ledger inserts require writable owner IDs for normal
  account creation. A direct-SQL test confirmed the runtime role can create a
  linked account/ledger pair for another existing user. The database trigger
  enforces that the pair has matching owners, but cannot bind a database
  connection to the authenticated API principal; API authorization remains
  essential.
- The runtime role can update account status and balance columns on any row.
  The balance trigger rejects inconsistent totals, but direct status changes
  can bypass API role checks and audit events. Runtime credentials must remain
  private to the trusted backend.
- The runtime role can insert journal, ledger, idempotency, and audit rows as
  required by financial workflows. Constraints protect ledger consistency,
  but the database role does not itself prove the API authorization context or
  audit-event provenance.
- No OWASP, PCI DSS, banking-regulatory, or other compliance claim is made.

## 10. Phase 2 security testing results

The initial review confirmed two medium-severity findings: missing audit
evidence for administrator account-status changes, and a conditional local
Compose database exposure/privilege risk. A follow-up audit-coverage trace
also identified missing registration/login, account-creation, authentication
denial, and route-level authorization denial events. These findings were
remediated with credential-free audit events, PostgreSQL privilege
restrictions, and an additive migration. Phase 2 also confirmed the missing
JWT time-claim finding T-21: a correctly signed token without `exp` was
accepted with HTTP 200 before the fix. JWT validation now requires `sub`,
`iat`, and `exp`; the new API regression tests reject missing time claims.
The current database revision is `20261107_0005 (head)`.

**Attack attempted and blocked (test evidence):**

- Cross-user account detail, statement, transaction-history filtering,
  deposit, and transfer-source access; no foreign-account financial posting
  or balance change occurred.
- Holder/admin role escalation through registration fields, account owner,
  status, ledger-account and balance fields, transaction ownership/balance
  fields, and a forged `ADMIN` role claim. The claim is not authoritative;
  database user role controls authorization.
- Auditor deposit, withdrawal, transfer, reversal and account-status changes;
  each financial mutation was denied, and financial records remained
  unchanged.
- Expired, malformed, tampered-signature, wrong-algorithm, missing-`sub`,
  missing-`iat`, missing-`exp`, and disabled-user tokens. Rejections returned
  generic authentication errors. Unknown-user and bad-password login
  responses did not disclose account existence.
- Zero, oversized, fractional, and forged financial amounts/fields, missing
  idempotency keys, frozen/closed account operations, sequential and
  simultaneous duplicate reversals, concurrent withdrawals/transfers, and
  duplicate idempotency requests. Database balances and journal/ledger
  invariants were checked after these cases.
- Existing tests also verify same-key/different-payload rejection,
  cross-user idempotency-key isolation, rollback consistency, durable
  rejection/success audit events, and database privilege denials versus
  trigger rejection.

**Attempted and allowed by product design:**

- A holder's transfer to another holder's LedgerLine account succeeds when
  the source account belongs to the caller. Cross-customer destination is an
  intended internal transfer, not an authorization bypass; only source
  ownership is required.

**Not tested in this Phase 2 run:**

- Live brute-force/rate-volume behavior, browser-executed XSS payloads,
  request floods, and network-level CORS attacks were not run. `npm audit`
  reported no known dependency vulnerabilities, but this is not a full supply
  chain assessment. No dedicated secret-leak log-capture test or
  timeout-after-commit client simulation was run. External production
  deployment, TLS/firewall rules, and hosting headers were not assessed.

No Critical or High exploitable application vulnerability was confirmed in
the tested cases; one Medium JWT claim enforcement issue was reproduced,
fixed, and regression-tested. These tests are scoped evidence, not a claim
that LedgerLine has received a comprehensive penetration test. The residual
database-owner trust boundary and deployment risks in Section 9 remain.

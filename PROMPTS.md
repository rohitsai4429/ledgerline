
## Entry — Database Architecture Review

**Date:** 2026-11-07

**Feature:** LedgerLine database architecture

**AI Tools:** ChatGPT

### Prompt Used

Review my initial LedgerLine entity relationship
diagram and identify missing entities, incorrect
relationships and financial-integrity risks.

### Initial AI Suggestion

The initial design connected financial ledger
entries directly to customer accounts.

### Issue Identified

Customer-facing accounts and internal accounting
ledger accounts represent different concepts.

Using customer accounts directly in ledger entries
would make it difficult to properly represent system
clearing accounts and double-entry bookkeeping.

### Correction Implemented

Introduced a separate LEDGER_ACCOUNTS entity.

Updated the relationship so customer accounts
reference their corresponding ledger accounts.

Ledger entries now reference ledger_accounts
instead of customer accounts.

Also reviewed idempotency uniqueness, ledger
line numbering and audit-event relationships.

### Verification

Updated the Mermaid ERD source and reviewed
the resulting entity relationships.

Further database-level validation remains pending.

### Related Commit

To be added after committing the ERD update.

## Entry — Authentication API

**Date:** 2026-11-07

**Feature:** LedgerLine backend authentication

**AI Tools:** Copilot SDK in VS Code

### Prompt Used

Implement registration and login with normalized unique emails,
Argon2 password hashing, role-safe account creation, expiring JWT
authentication, role authorization, a current-user endpoint, an
Alembic migration, and isolated tests.

### Implementation

Added a UUID-based user model with role and status enums, normalized-email
uniqueness, Argon2 password hashing, signed expiring JWTs, authentication
and role authorization dependencies, and `/api/v1/auth/register`,
`/login`, and `/me` endpoints. Public registration creates only
`ACCOUNT_HOLDER` users. Added an additive PostgreSQL Alembic migration.

### Verification

Nine authentication tests and the existing health test passed using an
isolated in-memory SQLite database. PostgreSQL migration SQL generation,
Python compilation, dependency consistency, and Pylance diagnostics passed.
The authentication migration was generated but not applied during this entry.
Pytest reported a Starlette `TestClient` deprecation warning.

## Entry — Account Management

**Date:** 2026-11-07

**Feature:** LedgerLine customer and ledger account management

**AI Tools:** Copilot SDK in VS Code

### Prompt Used

Build account creation, listing, details, ownership checks, admin status
management, ledger-account linkage, integer-paise balances, constraints,
migrations, and PostgreSQL integration/security tests without implementing
financial transactions.

### Implementation

Added customer and ledger-account SQLAlchemy models with one-to-one linkage,
generated unique account numbers, zero initial balances stored as integer
paise, and PostgreSQL constraints. Account holders can create accounts and
read only their own; administrators can list/read all and manage statuses;
auditors have read-only access. Account APIs do not expose balance updates.
Added migration `20261107_0002`.

### Verification

Applied additive migrations through revision `20261107_0002` to the verified
local PostgreSQL 17 `ledgerline` database without dropping data or volumes.
Nine PostgreSQL account integration/security tests passed, as did the full
19-test suite. Alembic schema comparison found no pending operations.
Python compilation, dependency checks, and Pylance diagnostics passed.
Pytest reported a Starlette `TestClient` deprecation warning.

## Entry — Financial Transaction Engine

**Date:** 2026-11-07

**Feature:** LedgerLine double-entry financial transaction engine

**AI Tools:** Copilot SDK in VS Code

### Prompt Used

Implement deposits, withdrawals, internal transfers, double-entry journals,
idempotency, transaction history, account statements, reversals, and durable
audit events on the existing FastAPI/PostgreSQL architecture. Preserve the
existing authentication and account features, use PostgreSQL concurrency
controls, protect posted records at the database level, add an additive
migration, and verify all behavior without resetting the existing database.

### Implementation

Added customer/deposit-clearing/withdrawal-clearing ledger account kinds and
seeded the two INR clearing accounts. Added journal transactions, debit/credit
ledger entries, per-user idempotency records, and audit events. Deposits,
withdrawals, and transfers update balances and post balanced journals in one
database transaction. Admin reversals post opposite entries. Transaction
history, account statements, and administrator/auditor audit-event reads are
available through the API.

PostgreSQL advisory transaction locks serialize identical idempotency keys;
account rows are locked in deterministic UUID order. Rejected business
operations persist a rejection audit and idempotency result without retaining
balance or ledger changes. Database triggers validate posted two-line journals
and ledger/account reconciliation, and reject mutation/deletion of posted
journals, entries, idempotency records, audit events, ledger-account identity,
and account ownership/ledger linkage. These controls are not claimed to be
tamper-proof against privileged database operators. Posting is INR-only; no
external payment settlement or multi-currency processing was added.

Added additive migration `20261107_0003`, extending ledger accounts and
creating the journal, entry, idempotency, and audit tables and constraints.
The migration was applied to the configured PostgreSQL 17 `ledgerline`
database at host port `5433`, after confirming its revision was `20261107_0002`
and its existing user/account tables had no rows.

### Verification

The full suite passed: **35 tests** (the 19 existing tests plus 16 new
PostgreSQL transaction integration tests). The new tests cover deposits,
withdrawals, transfers, reversals, insufficient funds, replay and changed
payload behavior, concurrent duplicate requests, concurrent withdrawals and
transfers, rollback, access control, audit records, statements, ledger
invariants, and database-enforced immutability. Transaction tests use separate
sessions against PostgreSQL in a generated temporary schema, which is dropped
after the test module; the shared database was not used for test records.

Alembic reports revision `20261107_0003` as the sole head and `alembic check`
reports no pending operations. The shared database contains two clearing
ledger accounts and no test users, customer accounts, journals, entries,
idempotency records, or audit events. Application import/OpenAPI routes,
Python compilation, dependency consistency, and Pylance diagnostics passed.
Pytest reports one existing Starlette `TestClient` deprecation warning.

## Entry — LedgerLine React Frontend

**Date:** 2026-11-07

**Feature:** Role-aware LedgerLine frontend and live API integration

**AI Tools:** Copilot SDK in VS Code

### Prompt Used

Build a complete React/Vite/TypeScript application against the existing
FastAPI routes. Inspect the backend contract first, implement real-data
customer, administrator, and auditor workflows, use safe bearer-token and
idempotency behavior, add accessible UI and tests, update setup documentation,
and report only verified results.

### Implementation

Added a responsive React application with role-aware routing, login and
registration, dashboard, account management, deposits, withdrawals, transfers,
transaction history, account statements, administrator status/reversal
controls, and auditor audit views. Pages use the existing typed FastAPI
endpoints only; balances and activity are not mocked. `frontend/README.md`
documents the verified request/response, authorization, and error map.

Bearer tokens remain in memory because the API does not provide HttpOnly-cookie
authentication or refresh. Financial requests retain the same idempotency key
and exact payload in tab-scoped session storage after an ambiguous failure.
Paise values are parsed from raw JSON into strings and formatted with integer
arithmetic to avoid JavaScript precision loss. Added Vite/Tailwind setup,
frontend environment example, SPA redirect fallback, API CORS configuration,
and a preflight test. Removed unused ESLint dependencies after `npm audit`
reported advisories in those packages; the active Oxlint toolchain remains.

### Verification

- Frontend: `npm run lint` passed without warnings; `npm run typecheck` passed;
  `npm test` passed **13 tests across 7 files**; `npm run build` passed with
  route-level chunks; `npm audit` reported **0 vulnerabilities**.
- Backend regression suite: **36 passed**, with one existing Starlette
  `TestClient` deprecation warning.
- Browser smoke checks rendered login and registration, confirmed mobile
  layout at 390px without horizontal overflow, and confirmed a deep SPA URL
  falls back to the app and redirects unauthenticated users to sign-in.
- FastAPI startup and live `GET /health` returned `200`; Vite-origin CORS
  preflight returned `200` with `Authorization` and `Idempotency-Key` allowed;
  unauthenticated `GET /api/v1/auth/me` returned `401`.

The frontend transaction form, API error handling, numeric response parsing,
role gate, and idempotent retry behavior are covered by mocked frontend tests.
No authenticated financial operation was claimed as a live end-to-end browser
test. No Git commit or push was made.

## Entry — LedgerLine Product Scope Refinement

**Feature:** Align the existing frontend with the internal-ledger product definition

**AI Tools:** Copilot SDK in VS Code

### Prompt Used

Refine the existing LedgerLine frontend without replacing working API
integrations. Make it clear that deposits, withdrawals, and transfers update
internal LedgerLine records only; improve role-specific workflows, transaction
details and filtering, and add explicit confirmation before posting. Use only
backend capabilities that exist, document limitations, add tests, and report
verified results.

### Implementation

Added internal-only product disclosures and explicit internal transaction
labels across authentication, customer workflows, and the application shell.
Added administrator account filtering and API-backed details, confirmation
before account status changes, current-page transaction text/type filters,
transaction detail and reversal references, expandable audit metadata, and
explicit confirmation before posting a financial operation. Added dialog
keyboard handling and loading skeletons. Updated root and frontend setup and
scope documentation; no backend routes or financial API behavior were added.

### Verification

- `npm run typecheck` passed.
- `npm run lint` passed.
- `npm test` passed: **16 tests across 8 files**.
- `npm run build` passed.
- `npm audit --audit-level=moderate` reported **0 vulnerabilities**.

No backend suite was rerun for this frontend-only refinement. No Git commit or
push was made.


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

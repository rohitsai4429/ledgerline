# 1. ADR-001: LedgerLine Technology Stack

## 2. Status

**Accepted**

## 3. Decision date

**2026-11-07.** This date is supported by the dated implementation entries in
`PROMPTS.md` and the Alembic revision metadata. No earlier, separate stack
decision date is recorded.

## 4. Context and problem statement

LedgerLine is an internal INR ledger demonstration. It needs authenticated,
role-aware account workflows and auditable financial postings whose balances
remain consistent under retries, concurrent requests, and failures. The
project also needs a maintainable web interface that consumes the actual API.
Deposits, withdrawals, and transfers update LedgerLine records; they do not
settle through banks or external payment providers.

The implementation is a single deployable backend application organized by
domain and responsibility, with a separate browser frontend and a relational
database. This is a **modular monolith**, not a set of independently deployed
services.

## 5. Decision

Use Python and FastAPI for the backend, PostgreSQL as the system of record,
SQLAlchemy for persistence, and Alembic for additive schema migrations. Use a
React and TypeScript single-page application built with Vite. Keep the backend
modular within one application process, and make PostgreSQL transactions,
constraints, and triggers part of the financial-integrity boundary.

## 6. Selected technologies and responsibilities

| Area | Implemented technology | Responsibility |
|---|---|---|
| Backend runtime and API | Python 3.11, FastAPI, Uvicorn | One HTTP API application with health, authentication, account, and transaction routes. |
| Validation and settings | Pydantic, Pydantic Settings | Validate API request/response models and load application configuration. |
| Persistence | SQLAlchemy 2.x, psycopg 3 | Map domain records and execute PostgreSQL queries and transactions. |
| Database and schema evolution | PostgreSQL 17, Alembic | Persist user, account, journal, ledger, idempotency, and audit records; apply versioned additive migrations. |
| Authentication | PyJWT, Argon2 | Issue and verify expiring bearer JWTs and hash passwords. |
| Frontend | React, TypeScript, Vite | Build and serve the role-aware browser application and static production bundle. |
| Frontend routing and data | React Router, TanStack Query | Client-side navigation, query caching, and mutation lifecycle management. |
| Forms and presentation | React Hook Form, Zod, Tailwind CSS, Lucide React, Recharts | Form state and validation, styling, icons, and charts where used. |
| Backend tests | Pytest, HTTPX, PostgreSQL | Unit/API and PostgreSQL integration/privilege tests. PostgreSQL tests use isolated temporary schemas. |
| Frontend tests and checks | Vitest, React Testing Library, Playwright, Oxlint, TypeScript | Component/unit tests, real-browser end-to-end testing, linting, and type checking. |
| Local database environment | Docker Compose, `postgres:17` | Run the local PostgreSQL service with a persistent named volume and loopback-only host binding. |

## 7. Alternatives

No alternatives evaluation is recorded in the existing project documentation.
This ADR does not claim that alternatives were historically benchmarked or
rejected.

## 8. Reasons for the selected architecture

- The modular monolith keeps API routes, domain services, repositories,
  database models, schemas, and core configuration separated while allowing a
  transaction to cross those modules in one application-controlled database
  transaction. It avoids introducing independently deployed services that the
  current scope does not require.
- PostgreSQL provides relational constraints and transaction semantics suited
  to the ledger's ownership links, unique idempotency scope, journal
  references, and atomic updates.
- A financial operation updates account balances, creates a journal and
  entries, and records its idempotency and audit outcome within transactional
  boundaries. Account rows are locked in deterministic order; PostgreSQL
  advisory transaction locks serialize identical idempotency keys.
- Database checks and triggers enforce positive INR amounts, valid account and
  ledger relationships, nonnegative balances, posted-journal balance, ledger
  reconciliation, and immutability protections. Reversals post compensating
  entries rather than editing posted entries. These database controls
  complement, but do not replace, application authorization.
- The React client uses typed API modules and real API data. Role checks in
  the browser support navigation and user experience; the backend remains the
  authorization boundary.

## 9. Consequences and trade-offs

**Benefits**

- Domain modules can be developed and tested independently while sharing one
  deployable FastAPI application.
- PostgreSQL is the authoritative store for account balances, journals,
  idempotency records, and audit events, allowing integrity checks and
  financial writes to participate in database transactions.
- Alembic provides explicit, additive schema evolution. A separate migration
  connection is used rather than granting migration privileges to the
  restricted runtime role.

**Trade-offs and security implications**

- The financial implementation relies on PostgreSQL-specific behavior,
  including advisory locks and database triggers; using another database
  would require a deliberate redesign and revalidation.
- Database triggers and least-privilege grants do not defend against a
  privileged database owner who can alter them. The application runtime role
  is shared by requests, so ownership and role authorization must be enforced
  by the backend.
- Authentication currently uses bearer tokens, not HttpOnly cookies or a
  refresh-token flow. The frontend keeps the access token in JavaScript
  memory; reload requires signing in again, and memory storage is not an XSS
  defense.
- The current accounting scope is INR-only and internal to LedgerLine. There
  is no bank, UPI, card, external payment, or multi-currency integration.
- A modular monolith keeps deployment simple for this scope but does not
  provide independent service scaling or failure isolation.

### Deployment scope

At the time this ADR was written (2026-11-07), the verified deployment in
repository evidence was the local PostgreSQL/Compose setup with FastAPI and
Vite run separately. The owner now confirms the frontend and backend are
deployed on Render Free and the production database is Neon PostgreSQL; see
the [current project documentation](../PROJECT_DOCUMENTATION.md#26-deployment-architecture).
Exact Render Dashboard values, source branch, auto-deployment trigger, and
production database settings remain external and were not independently
verified during the current documentation audit. The repository still does
not define a Compose deployment for the API/frontend.

## 10. Validation and implementation evidence

- The backend is organized under `backend/app` into API, core, database,
  models, schemas, services, and repositories. `backend/app/main.py`
  assembles one FastAPI application.
- `backend/requirements.txt` and `frontend/package.json` declare the runtime,
  persistence, UI, and test dependencies listed above.
- At the time this ADR was written, `backend/alembic/versions/` contained
  migration history through `20261107_0005_runtime_privilege_hardening`.
  Migrations `20261108_0006` and `20261108_0007` were added later; the current
  repository head is `20261108_0007`. The transaction model and migrations
  define PostgreSQL checks, foreign keys, uniqueness rules, and trigger-based
  integrity protections.
- `backend/compose.yaml` currently defines PostgreSQL only. The API is run
  separately with Uvicorn during local development; the frontend is run with
  Vite. The Compose file binds the database to `127.0.0.1:5433` and persists
  its data in the `ledgerline_data` volume.
- Verification recorded at the time of this ADR included 56 passing backend
  tests, 16 passing frontend unit tests, passing frontend lint and typecheck,
  a successful production build, and one passing Playwright browser journey
  against the real frontend, API, and an isolated PostgreSQL schema. These
  are historical, not the latest overall results. Current time-scoped test
  evidence is in the [project documentation](../PROJECT_DOCUMENTATION.md#28-testing-strategy-and-test-results).
- The E2E database verifier checks balanced journal entries and reconciled
  account balances. These test results are evidence of implemented behavior,
  not performance benchmarks, a security certification, or proof of
  production readiness.

## 11. References

- [Project overview, setup, security, and verification](../../README.md)
- [Implementation history and recorded engineering verification](../../PROMPTS.md)
- [Functional and financial-integrity requirements](../requirements.md)
- [Frontend architecture, API integration, and deployment notes](../../frontend/README.md)
- [Security threats and residual trust boundaries](../../THREATS.md)
- [Backend dependencies](../../backend/requirements.txt)
- [Local PostgreSQL service configuration](../../backend/compose.yaml)
- [Backend application modules](../../backend/app/)
- [Backend tests](../../backend/tests/)
- [Frontend dependency and script manifest](../../frontend/package.json)
- [Playwright browser-test configuration](../../frontend/playwright.config.ts)
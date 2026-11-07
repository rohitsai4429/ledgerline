# LedgerLine

### Money Movement with a Verifiable Ledger

LedgerLine is a secure financial transaction management
system designed to ensure accurate money movement,
prevent duplicate transactions and maintain verifiable
financial records.

## Problem Statement

Build a financial system supporting deposits,
withdrawals and transfers while ensuring financial
integrity, transaction consistency and auditability.

## Core Objectives

- Prevent negative account balances.
- Prevent duplicate transactions.
- Maintain double-entry bookkeeping.
- Handle concurrent transactions safely.
- Enforce role-based access control.
- Maintain tamper-resistant financial records.
- Provide transaction statements and audit trails.

## User Roles

1. Administrator
2. Account Holder
3. Auditor

## Technology Stack

- Backend: Python 3.11 + FastAPI
- Database: PostgreSQL 17
- ORM and migrations: SQLAlchemy 2.x + Alembic
- Validation and configuration: Pydantic
- Testing: Pytest

## Project Status

- [x] Problem understanding
- [x] Requirement analysis
- [x] System architecture
- [x] Database design
- [x] Backend scaffold
- [x] Authentication
- [x] Account management
- [ ] Deposits, withdrawals, and transfers
- [ ] Frontend development
- [ ] Security testing
- [ ] Deployment

## Repository Structure

The backend is organized as a modular monolith under `backend/app`:
API routes, core configuration and logging, database setup, and separate
models, schemas, services, and repositories packages.

## Setup Instructions

### Backend

Install Python 3.11 and Docker Desktop, then run these commands from `backend`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Set a local `POSTGRES_PASSWORD` in `.env`. Set `DATABASE_URL` to use the same
password, URL-encoded for a PostgreSQL connection URL. Keep `.env` private; it
is ignored by Git. The example file contains placeholders only.

Replace the example `JWT_SECRET_KEY` once with a locally generated secret.
This writes it directly to the ignored `.env` file without printing it:

```powershell
python -c "import secrets; from dotenv import set_key; set_key('.env', 'JWT_SECRET_KEY', secrets.token_urlsafe(48))"
```

An exported `DATABASE_URL` environment variable takes precedence over `.env`.

Start PostgreSQL from `backend`:

```powershell
docker compose up -d db
docker compose ps
```

Compose publishes PostgreSQL on host port `5433` (container port `5432`) to
avoid conflicts with a PostgreSQL service already using `5432` on Windows.
The application connects to `localhost:5433`.

Apply all additive database migrations (this does not reset or delete data):

```powershell
alembic upgrade head
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

The liveness endpoint is available at `http://127.0.0.1:8000/health`. Run the
backend tests from `backend` with:

```powershell
python -m pytest
```

Authentication endpoints:

- `POST /api/v1/auth/register` — public registration; always creates an
  `ACCOUNT_HOLDER`.
- `POST /api/v1/auth/login` — verifies credentials and returns a short-lived
  bearer token.
- `GET /api/v1/auth/me` — returns the authenticated user's safe profile.

Passwords must be at least 12 characters. Registration does not accept a
caller-supplied role; administrative account provisioning is not implemented.
The authentication migration creates the users table and normalized-email
uniqueness constraint.

Account management endpoints:

- `POST /api/v1/accounts` — authenticated account holders create an account
  with a generated account number, an associated ledger account, and a zero
  balance.
- `GET /api/v1/accounts` and `GET /api/v1/accounts/{account_id}` — account
  holders see their own accounts; administrators and auditors can read all
  accounts.
- `PATCH /api/v1/accounts/{account_id}/status` — administrators can set
  `ACTIVE`, `FROZEN`, or `CLOSED`; closed accounts cannot be reactivated.

Balances are stored as integer paise and constrained to be nonnegative.
Account APIs do not accept balance changes. Auditors have read-only access;
deposits, withdrawals, and transfers are not implemented.

Both Alembic migrations are applied to the configured local database; current
revision is `20261107_0002`. PostgreSQL schema comparison reports no pending
model differences. On an existing Docker volume, changing `POSTGRES_PASSWORD`
does not update the stored PostgreSQL role password; update it explicitly and
keep `DATABASE_URL` synchronized.

### Backend work completed

- FastAPI scaffold with modular API, core, database, model, schema, service,
  and repository packages.
- PostgreSQL 17 development database configured through Docker Compose on
  host port `5433`; SQLAlchemy TCP connectivity was verified.
- Authentication with normalized unique emails, Argon2 password hashing,
  account status checks, signed expiring JWTs, and role authorization.
- Public registration always assigns `ACCOUNT_HOLDER`; callers cannot set
  their own role.
- Account management with generated account numbers, owner-scoped access,
  admin status controls, auditor read-only access, and a required one-to-one
  ledger-account relationship.
- Balances stored in integer paise with a database nonnegative constraint;
  no account API can modify balances.
- Additive Alembic migrations for users, ledger accounts, and customer
  accounts.

The current test suite has 19 passing tests, including 9 account integration
and security tests against PostgreSQL. Authentication unit tests use an
in-memory SQLite database. PostgreSQL integration test data is rolled back
after each test. Pytest currently emits a Starlette `TestClient` deprecation
warning.

## Security and Integrity

Detailed security controls and threat analysis
will be documented as development progresses.

## Documentation

- PROMPTS.md — AI usage and engineering corrections.
- THREATS.md — Security threat modelling.
- docs/ — Requirements, architecture and design decisions.


## System Architecture

LedgerLine follows a Modular Monolithic Architecture.

### Technology Stack

- Backend: Python + FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Frontend: React + Vite
- Testing: Pytest

### Architecture Documentation

| Document | Description |
|---|---|
| [ER Diagram](docs/architecture/erd.mmd) | Database entities and relationships |
| [System Architecture](docs/architecture/system-architecture.md) | Application architecture |
| [Data Dictionary](docs/architecture/data-dictionary.md) | Database tables and constraints |
| [Transaction Flow](docs/architecture/transaction-flow.md) | Financial transaction workflows |
| [Technology Decision](docs/decisions/ADR-001-technology-stack.md) | Technology selection rationale |
| [Ledger Design](docs/decisions/ADR-002-ledger-design.md) | Double-entry accounting decisions |

### Current Development Status

- [x] Problem understanding
- [x] Initial requirement analysis
- [x] Initial ER diagram
- [x] Requirements documentation
- [x] Data dictionary
- [x] Architecture documentation
- [x] Database schema and migrations
- [x] Backend scaffold
- [x] Authentication
- [x] Account management
- [ ] Deposits, withdrawals, and transfers
- [ ] Frontend development
- [ ] Security testing
- [ ] Deployment

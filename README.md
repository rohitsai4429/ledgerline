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

- Backend: Python 3.12 + FastAPI
- Database: PostgreSQL
- ORM and migrations: SQLAlchemy 2.x + Alembic
- Validation and configuration: Pydantic
- Testing: Pytest

## Project Status

- [x] Problem understanding
- [x] Requirement analysis
- [x] System architecture
- [x] Database design
- [x] Backend scaffold
- [ ] Backend features
- [ ] Frontend development
- [ ] Security testing
- [ ] Deployment

## Repository Structure

The backend is organized as a modular monolith under `backend/app`:
API routes, core configuration and logging, database setup, and separate
models, schemas, services, and repositories packages.

## Setup Instructions

### Backend

Install Python 3.12 and PostgreSQL, then run these commands from `backend`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `DATABASE_URL` in `.env` to the PostgreSQL connection string for your
local database. The example uses local PostgreSQL authentication and contains
no credentials.

Start the API:

```powershell
uvicorn app.main:app --reload
```

The liveness endpoint is available at `http://127.0.0.1:8000/health`. Run the
backend tests from `backend` with:

```powershell
python -m pytest
```

Alembic is configured for future schema revisions; no application tables or
migrations are included in this scaffold.

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
- [ ] Database implementation
- [x] Backend scaffold
- [ ] Backend features
- [ ] Frontend development
- [ ] Security testing
- [ ] Deployment

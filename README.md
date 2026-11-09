# LedgerLine

### Money Movement with a Verifiable Ledger

LedgerLine is a secure internal financial ledger platform designed to
demonstrate reliable money movement, balanced accounting records and
verifiable transaction history.

> LedgerLine is a demonstration financial ledger. Transactions update internal
> account records and do not move real money through banks or payment providers.

## At a glance

| Frontend | Backend | Database | Hosting |
|---|---|---|---|
| [Render Static Site](https://ledgerline-frontend-bmtt.onrender.com) | [FastAPI on Render](https://ledgerline-api-9dld.onrender.com) | Neon PostgreSQL | Render Free |

Authentication supports password and Google Identity Services sign-in, both
followed by email OTP through Google Apps Script and Gmail MailApp. The
repository is private; ask the project owner for access.

### Documentation and architecture

- [Project and technical documentation](docs/PROJECT_DOCUMENTATION.md)
- [Technology stack](docs/TECHNOLOGY_STACK.md) ·
  [Development history](docs/PROJECT_DEVELOPMENT_HISTORY.md) ·
  [API reference](docs/API_REFERENCE.md) ·
  [Environment configuration](docs/ENVIRONMENT_CONFIGURATION.md)
- [Threat model](THREATS.md) ·
  [Architecture index](docs/architecture/README.md)
- [System diagram](docs/architecture/system-architecture.md) ·
  [Authentication/OTP diagram](docs/architecture/authentication-otp-flow.png) ·
  [Transaction flow](docs/architecture/transaction-flow.md) ·
  [Deployment diagram](docs/architecture/deployment-architecture.md)

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
- Protect posted ledger records against ordinary application-level mutation.
- Provide transaction statements and audit trails.

## User Roles

1. **Account holder** — manages owned accounts, makes internal deposits,
   withdrawals and transfers, and reviews transactions and statements.
2. **Administrator** — reviews all customer accounts and system-wide
   transactions, manages account statuses, inspects audit events and can post
   authorized transaction reversals.
3. **Auditor** — read-only access to customer accounts, transaction history,
   per-account debit/credit statement entries and audit events.

Public registration always creates an account holder. Administrator/auditor
provisioning is performed by a trusted operator using backend bootstrap
tooling, not through public registration or the frontend.

## Technology Stack

- Backend: Python 3.11 + FastAPI
- Database: PostgreSQL 17
- ORM and migrations: SQLAlchemy 2.x + Alembic
- Validation and configuration: Pydantic
- Testing: Pytest
- Frontend: React, TypeScript, Vite, Tailwind CSS, TanStack Query, React Router,
  React Hook Form, Zod, Lucide, Recharts, Vitest, Testing Library, and Playwright

## Project Status

- [x] Problem understanding
- [x] Requirement analysis
- [x] System architecture
- [x] Database design
- [x] Backend scaffold
- [x] Authentication
- [x] Account management
- [x] Deposits, withdrawals, and transfers
- [x] Frontend development
- [ ] Independent security assessment
- [x] Render Free deployment with Neon PostgreSQL

### Current deployment and verification

| Component | Current deployment |
| --- | --- |
| Frontend | [https://ledgerline-frontend-bmtt.onrender.com](https://ledgerline-frontend-bmtt.onrender.com) |
| Backend API | [https://ledgerline-api-9dld.onrender.com](https://ledgerline-api-9dld.onrender.com) |
| Health | [https://ledgerline-api-9dld.onrender.com/health](https://ledgerline-api-9dld.onrender.com/health) |
| Database | Production Neon PostgreSQL |
| Hosting | Render Free |

Authentication uses passwords or Google Identity Services, followed by email
OTP verification. OTP email is delivered through a Google Apps Script Web App
using Gmail `MailApp`. The full backend suite passed 75 tests before the mailer
integration; the focused OTP/authentication/health suite passed 37 tests after
the integration. Live password login and Google sign-in/account linking have
been tested successfully. Fresh registration to a recipient other than the
Apps Script owner's email remains to be verified after the mailer change.
See [Project Documentation](docs/PROJECT_DOCUMENTATION.md) for the detailed
verification record, production settings, limitations, and architecture
diagrams.

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

Set distinct local values for `POSTGRES_PASSWORD` and `APP_DB_PASSWORD`.
`POSTGRES_PASSWORD` is for the local Compose bootstrap/migration role;
`DATABASE_URL` must use the restricted `ledgerline_app` role and its
`APP_DB_PASSWORD`. `MIGRATION_DATABASE_URL` uses the bootstrap role and is
read only by Alembic. URL-encode credentials when they contain reserved URL
characters. Keep `.env` private; it is ignored by Git. The example file
contains placeholders only.

Replace the example `JWT_SECRET_KEY` once with a locally generated secret.
This writes it directly to the ignored `.env` file without printing it:

```powershell
python -c "import secrets; from dotenv import set_key; set_key('.env', 'JWT_SECRET_KEY', secrets.token_urlsafe(48))"
```

An exported `DATABASE_URL` environment variable takes precedence over `.env`.
Alembic and the PostgreSQL integration-test fixture read
`MIGRATION_DATABASE_URL` separately; the FastAPI settings object does not load
that privileged connection URL.

Start PostgreSQL from `backend`:

```powershell
docker compose up -d db
docker compose ps
```

Compose binds PostgreSQL to `127.0.0.1:5433` (container port `5432`), avoiding
conflicts with a PostgreSQL service already using `5432` on Windows without
exposing the database on other host interfaces. The API connects to
`127.0.0.1:5433` using the non-superuser `ledgerline_app` role. The bootstrap
role remains privileged for local migrations only.

On a new Docker volume the Compose initialization script creates the app role.
For an existing volume, the init script is not rerun automatically. Preserve
the volume and provision/update the restricted role once after updating `.env`
and restarting the database service:

```powershell
docker compose up -d db
docker compose exec -T db psql -U ledgerline_user -d ledgerline -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/10-create-app-role.sql
```

The script only creates or updates the `ledgerline_app` role and adjusts its
least-privilege grants; it does not drop, recreate, or reset database objects
or volumes. The runtime role cannot update user rows or account ownership and
can update only account balance, status, and timestamp columns.

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

- `POST /api/v1/auth/register` — creates an `ACCOUNT_HOLDER` and starts email
  verification; it never returns a LedgerLine token.
- `POST /api/v1/auth/login` — verifies the password and starts email
  verification; it never returns a LedgerLine token.
- `POST /api/v1/auth/google` — verifies a Google ID token; an existing matching
  password account requires explicit link confirmation and email OTP.
- `POST /api/v1/auth/otp/verify` — consumes an eight-digit single-use code and
  returns the LedgerLine bearer token only after successful verification.
- `POST /api/v1/auth/otp/resend` — resends a code subject to the 60-second
  cooldown and per-user hourly limit.
- `GET /api/v1/auth/me` — returns the authenticated user's safe profile.

Passwords must be at least 12 characters. Registration does not accept a
caller-supplied role; privileged role provisioning is restricted to the
trusted operator bootstrap process.
OTP codes expire after five minutes, allow at most five attempts, and are
stored only as HMAC digests. Resends have a 60-second cooldown and a limit of
five per account per hour. Configure `OTP_HMAC_SECRET`, `OTP_MAILER_URL`,
`OTP_MAILER_SECRET`, and `GOOGLE_CLIENT_ID` in the backend environment.
`OTP_MAILER_URL` is the Google Apps Script Web App deployment URL; the mailer
receives the shared secret, recipient email, and OTP in a JSON POST. Set
`VITE_GOOGLE_CLIENT_ID` in the frontend build environment; it is a public client
identifier, not a secret. Never put backend credentials in a `VITE_` variable.
Authentication migration `20261108_0006` adds verified-email state, Google
identity mappings, and persistent OTP challenges. Migration `20261108_0007`
resets legacy email-verification state when OTP audit evidence is absent.

Account management endpoints:

- `POST /api/v1/accounts` — authenticated account holders create an account
  with a generated account number, an associated ledger account, and a zero
  balance.
- `POST /api/v1/accounts/recipient-lookup` — resolves a recipient account
  number and returns a masked identifier for transfer confirmation.
- `GET /api/v1/accounts` and `GET /api/v1/accounts/{account_id}` — account
  holders see their own accounts; administrators and auditors can read all
  accounts.
- `PATCH /api/v1/accounts/{account_id}/status` — administrators can set
  `ACTIVE`, `FROZEN`, or `CLOSED`; closed accounts cannot be reactivated.

Balances are stored as integer paise and constrained to be nonnegative.
Account APIs do not accept balance changes. All transaction amounts are
positive integer paise in INR; multi-currency posting is not enabled.
Auditors have read-only access.

The audit log records successful account creation/status changes, authentication
outcomes, authentication and role denials, and accepted/rejected financial
service operations. Anonymous events have no actor UUID and store only a
categorical reason plus request method/path; they do not store passwords,
tokens, or submitted emails.

The additive Alembic migrations are applied to the configured local
database; authentication migration `20261108_0006` follows
`20261107_0005`, and `20261108_0007` corrects legacy email-verification state
without OTP audit evidence. The repository head is `20261108_0007`.
PostgreSQL schema comparison
reports no pending model differences. Alembic requires the separate
`MIGRATION_DATABASE_URL` and refuses to run as `ledgerline_app`. On an existing Docker volume, changing
`POSTGRES_PASSWORD` does not update the stored PostgreSQL role password.
Keep `MIGRATION_DATABASE_URL` synchronized with that existing bootstrap role;
the application itself must continue to use the restricted role in
`DATABASE_URL`.

### Financial transaction API

- `POST /api/v1/transactions/deposits` — credit an owned active account against
  the INR deposit-clearing ledger account.
- `POST /api/v1/transactions/withdrawals` — debit an owned active account
  against the INR withdrawal-clearing ledger account; overdrafts are rejected.
- `POST /api/v1/transactions/transfers` — transfer paise from an owned active
  account to another active account.
- `POST /api/v1/transactions/{transaction_id}/reverse` — administrator-only
  correction by posting an opposite journal, never by editing posted entries.
- `GET /api/v1/transactions` — paginated transaction history. Account holders
  see transactions involving their own accounts; administrators and auditors
  can read all transactions.
- `GET /api/v1/accounts/{account_id}/statement` — account-scoped statement with
  opening, closing, and running integer-paise balances.
- `GET /api/v1/audit-events` — administrator/auditor access to operation audit
  events.

Each posting requires an `Idempotency-Key` header. Keys are unique per user;
retrying the same key and payload returns the original success or rejection,
while reusing a key with a different payload is rejected. PostgreSQL advisory
locks serialize duplicate keys. Account rows are locked in UUID order to
prevent concurrent overspending.

Each journal is posted with exactly one debit and one credit of the same
positive amount and currency. Deferred PostgreSQL triggers validate the
two-line balance, transaction-party mapping, and agreement between customer
account balances and their ledger entries. Posted journals, ledger entries,
idempotency records, audit events, ledger-account identities, and account
ownership/ledger links are protected from updates and deletes by database
triggers. These controls are not tamper-proof against a database owner or
superuser who can alter or disable the triggers; no cryptographic or
write-once audit system is claimed.

### Backend work completed

- FastAPI scaffold with modular API, core, database, model, schema, service,
  and repository packages.
- PostgreSQL 17 development database configured through Docker Compose on
  host port `5433`; SQLAlchemy TCP connectivity was verified.
- Authentication with normalized unique emails, Argon2 password hashing,
  Google identity verification, HMAC-digested email OTP, signed expiring JWTs,
  account status checks, and role authorization.
- Public registration always assigns `ACCOUNT_HOLDER`; callers cannot set
  their own role.
- Account management with generated account numbers, owner-scoped access,
  admin status controls, auditor read-only access, and a required one-to-one
  ledger-account relationship.
- Balances stored in integer paise with a database nonnegative constraint;
  no account API can modify balances.
- Double-entry financial transaction engine for deposits, withdrawals,
  internal transfers, admin reversals, transaction history, statements, and
  operation audits.
- Additive Alembic migrations for users, customer/system ledger accounts,
  journals, entries, idempotency records, audit events, Google identities, and
  email OTP challenges.

Earlier feature-specific test notes are historical. See
[Project Documentation](docs/PROJECT_DOCUMENTATION.md#28-testing-strategy-and-test-results)
for the latest full-suite and focused post-mailer results and their timing.

### Frontend product scope and limitations

The frontend is a role-aware client for internal LedgerLine accounting
operations; it is not connected to a bank, UPI rail, card processor or external
payment provider. Its login and registration pages, customer accounts and
money-movement forms, transaction details, administrator controls, read-only
auditor screens and API integration map are documented in
[frontend/README.md](frontend/README.md).

The current API provides per-account statements containing debit/credit
entries, but no journal-wide raw-entry endpoint. Transaction history supports
server-side account filtering and pagination; free-text and type filters in the
frontend apply only to the currently loaded result page. A recipient lookup
endpoint resolves an account number before transfer; the transaction request
uses the resolved account UUID.
Bearer JWTs are kept in browser memory because cookie authentication and token
refresh are not supported. These frontend limitations are not replaced with
mock data.

### Frontend local run

In a second PowerShell terminal while the backend and PostgreSQL are running:

```powershell
cd C:\Users\Rohith\ledgerline\frontend
npm install
if (!(Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

Set `VITE_API_BASE_URL` in the ignored frontend `.env` if the API is not at
`http://127.0.0.1:8000`. For a separate frontend deployment, use the deployed
API URL at build time and add the exact frontend origin to backend
`CORS_ALLOWED_ORIGINS`; do not put credentials in `VITE_*` variables. Build
with `npm run build` and configure the static host to serve `index.html` for
application routes (the Netlify-compatible fallback is in
`frontend/public/_redirects`).

### Frontend

The role-aware React application uses the live API only. Its exact endpoint,
request, response, authorization, and error mapping plus authentication and
local setup details are documented in [frontend/README.md](frontend/README.md).
The UI includes login/registration, account-holder money movement, account and
statement views, transaction history, administrator account/reversal controls,
and read-only auditor screens. Bearer tokens remain in memory because the API
does not support HttpOnly-cookie authentication or token refresh. Transaction
retries preserve their exact payload and idempotency key after ambiguous
failures.

For frontend setup, start the API as described above, then run `npm install`,
copy `frontend/.env.example` to `frontend/.env`, and run `npm run dev` from
`frontend`. To validate changes, run `npm run lint`, `npm run typecheck`,
`npm test`, and `npm run build` in that directory. Verification results for the
current frontend implementation are recorded in [PROMPTS.md](PROMPTS.md).

### Browser end-to-end integration tests

The Playwright suite exercises the real React app, FastAPI routes, and
PostgreSQL runtime role without mocked API responses. It uses a fresh
`ledgerline_e2e_<random hex>` schema in the database configured by
`DATABASE_URL` and `MIGRATION_DATABASE_URL`, applies the additive migrations
to that schema, and drops only that exact generated schema after the run. It
does not touch the existing `public` schema, records, or Docker volume.

Prerequisites: PostgreSQL 17 running through the existing Compose service,
`backend/.env` configured with the migration `ledgerline_user` and runtime
`ledgerline_app` URLs pointing at the same database, installed frontend npm
dependencies, and the backend virtual environment. Start the existing database
service (from `backend`) without removing or resetting its volume, then install
the browser and run the test (from `frontend`):

```powershell
cd backend
docker compose up -d db
cd ..\frontend
npx playwright install chromium
npm run test:e2e
```

Ports `127.0.0.1:18000` (isolated-schema API) and `127.0.0.1:15173` (Vite)
must be free. Test-only role credentials are randomly generated at runtime,
kept in an ignored temporary state file, and removed after teardown. The setup
refuses to overwrite a leftover state file. If setup or a test is interrupted,
inspect
`frontend/.playwright-state.json` and remove only its named
`ledgerline_e2e_<random hex>` schema using the configured migration role. The
scoped helper validates the schema prefix:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\e2e_db.py cleanup ledgerline_e2e_0123456789ab 0123456789ab
```

Cleanup also verifies the schema's E2E-run marker before dropping it. Never
use a wildcard or drop any other schema. If the schema is absent or has no
matching marker, cleanup refuses to drop anything; remove the stale state file
only after confirming that its schema was never created or is already absent.

**Previously recorded result:** `npm run test:e2e` — **1 browser journey passed**
on Chromium. It registered two account holders, logged in as each, created
separate owned accounts, posted an internal deposit, withdrawal and transfer,
replayed a request with the same idempotency key, rejected insufficient
funds and foreign-account access, displayed history and a statement, refreshed
and reauthenticated, changed an account status and reversed a transfer as
ADMIN, and verified read-only AUDITOR access including denied financial and
status mutations. PostgreSQL verification found exactly four posted journals
(deposit, withdrawal, transfer, reversal), eight balanced ledger entries,
final reconciled balances of `9,000` paise for Customer A and `0` paise for
Customer B, the expected frozen status, and audit/idempotency records. The
Playwright HTML report with attached role screenshots is generated at
`frontend/playwright-report/index.html`; test results are in
`frontend/test-results/`. These generated files are ignored by Git.

## Render Free + Neon Deployment and Operations

LedgerLine is currently deployed as a demonstration service, not a production
availability commitment. The frontend and backend use Render Free; Render
Free web services may sleep after inactivity, have ephemeral filesystems,
cannot receive private-network traffic, and do not provide Shell or one-off
jobs. The production database is Neon PostgreSQL; its plan and current usage
limits should be checked in the Neon console rather than inferred here. Review
provider limits and monitor usage. Render Free may also suspend services that
generate unusual outbound traffic to external databases.

The repo's [`render.yaml`](./render.yaml) defines the API and static frontend.
It does not create Neon resources or store any secret.

### Render service configuration

The project owner confirms the frontend and backend are deployed at the URLs
above. The checked-in Blueprint defines a **Static Site** and a **Web
Service**; the exact Render Dashboard values, source branch, and
auto-deployment trigger were not independently inspected. Keep the repository
private. The Blueprint pins the Web Service to `plan: free`; when reproducing
this deployment, explicitly choose **Free**. Static Site hosting is free.

| Setting | Frontend | Backend |
| --- | --- | --- |
| Root directory | `frontend` | `backend` |
| Runtime | Static Site | Python |
| Build command | `npm ci && npm run build` | `python -m pip install -r requirements.txt` |
| Publish directory | `dist` | — |
| Start command | — | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health-check path | — | `/health` |
| Python version | — | `3.11.9` |
| Node version | `24.22.1` | — |
| SPA rewrite | `/*` → `/index.html` | — |
| Plan | Free | Free |

These settings are also in the Blueprint. On Render Free the API cannot
receive private-network traffic and Neon is not on Render's private network;
the API must connect to Neon's public endpoint over TLS. Do not configure
Render's private database URL or claim this path is private networking.
The deployed service URLs are
`https://ledgerline-api-9dld.onrender.com` and
`https://ledgerline-frontend-bmtt.onrender.com`. Set
`VITE_API_BASE_URL` to the backend URL and `CORS_ALLOWED_ORIGINS` to the exact
frontend origin shown here. `DATABASE_URL` and `JWT_SECRET_KEY` use
`sync: false` and must be entered manually as secret environment values; no
secret is in the manifest.

### Neon project and restricted runtime role

1. Production PostgreSQL is hosted on Neon. The remaining steps document the
   owner/runtime-role setup for initial provisioning or recovery; they are
   not an instruction to create a duplicate production project. Confirm the
   active project and database details in the Neon console before operating.
2. Obtain separate Neon connection strings for the database owner and runtime
   role. Use the **direct** endpoint for provisioning and Alembic, and the
   **pooled** (`-pooler`) endpoint for the FastAPI runtime. Change only the
   driver prefix to `postgresql+psycopg://`; retain Neon's host, credentials,
   database, `sslmode=require`, and `channel_binding=require` query options.
   Psycopg 3 (`psycopg[binary]` in requirements) accepts PostgreSQL TLS
   connection parameters; Neon requires TLS. The application uses
   SQLAlchemy's normal connection pool and `pool_pre_ping`; its advisory lock
   is transaction-scoped and it does not depend on session-local state, so
   Neon transaction pooling is suitable for the runtime URL. The Alembic
   environment rejects Neon `-pooler` endpoints.
3. From a trusted local machine, install backend requirements, then provision
   the runtime role. The helper prompts without echoing the migration URL and
   asks for the new runtime password twice. The URL is not stored in the
   repository or Render:

   ```powershell
   cd backend
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python scripts\provision_runtime_role.py
   ```

   The helper requires database name `ledgerline`, a TLS-enabled direct
   `postgresql+psycopg` URL, a migration role that owns the `public` schema
   (including PostgreSQL's `pg_database_owner` ownership), and effective
   role-management capability. It creates/updates only
   `ledgerline_app` with `LOGIN` and `NOINHERIT`, and enforces `NOSUPERUSER`,
   `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, and `NOBYPASSRLS`,
   strips role memberships, denies schema/database creation, and preserves
   the project's column-level privilege model. Do not create the runtime role
   using Neon Console/CLI role creation if that method grants it membership in
   Neon's administrative role; use the SQL-based provisioner instead.
   Rerunning with the same password is idempotent; entering a different one
   rotates the runtime credential, so update Render's `DATABASE_URL` to match.

4. Configure Render API `DATABASE_URL` with Neon's pooled endpoint, database
   `ledgerline`, role `ledgerline_app`, its separately prompted password, and
   the same TLS query options. URL-encode reserved characters in credentials.
   Never put the Neon owner/migration URL on either Render service.

### Migration owner and exact manual migration procedure

Migrations `0001` through `0004` do not name a PostgreSQL owner role.
`20261107_0005` previously hardcoded `ledgerline_user` in its
`ALTER DEFAULT PRIVILEGES` statements. It now checks the actual owner of every
LedgerLine table, requires the migration role to match that owner, safely
quotes it, and scopes runtime-role default privileges to the application
schema. It verifies the `SECURITY DEFINER` functions are owned by the table
owner; their `EXECUTE` privilege is revoked from `PUBLIC` and granted only to
`ledgerline_app`. The migration also refuses if `ledgerline_app` still has
effective schema `CREATE` privileges rather than revoking broader grants.
The migration role must own `public`, create/manage `ledgerline_app`, and
execute the reviewed SQL. `0005` intentionally fails rather than broadening
runtime permissions. `ledgerline_user` remains only in the local Docker
bootstrap configuration, not as a migration prerequisite.

Render Free does not provide Shell or one-off jobs. Run migrations from the
trusted local machine using the Neon owner URL, not from API startup. The
provisioner above uses a hidden prompt for role credentials. For Alembic, use
PowerShell to enter the privileged URL without echo; it is passed only to the
local Alembic process and removed immediately:

```powershell
$secureUrl = Read-Host "Neon migration DATABASE_URL" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
try {
    $env:MIGRATION_DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed" }
    python -m alembic current
}
finally {
    Remove-Item Env:\MIGRATION_DATABASE_URL -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
```

Paste only the TLS-enabled **direct** `postgresql+psycopg://` URL at the
secure prompt.
Review the resulting revision before deploying the API. Never put the
privileged URL in Render environment variables, command-line arguments, logs,
or committed files. Do not run Alembic in the web-service start command.

### One-time ADMIN/AUDITOR bootstrap

Public registration accepts only email and password; its schema rejects extra
fields, and the database default assigns `ACCOUNT_HOLDER`. Do not promote
accounts by editing the role directly. After `alembic upgrade head`, create
each operator from a trusted local machine using the same direct privileged
connection. From `backend`, run:

```powershell
python scripts\bootstrap_operator.py
```

The script prompts without echo for the direct TLS migration URL and operator
password (twice), and visibly prompts for exactly `ADMIN` or `AUDITOR` and the
email. It uses the application's Argon2 hasher, rejects duplicate normalized
email addresses, writes the user and a `PRIVILEGED_USER_BOOTSTRAPPED` audit
event in one transaction, and prints no password or connection string. Run
once per named operator; there are no default credentials. The migration
credential is used only by this local process and must never be configured on
Render.

### Environment-variable checklist

| Service/process | Variable | Value |
| --- | --- | --- |
| Render API | `DATABASE_URL` | Neon pooled (`-pooler`) `postgresql+psycopg://` URL using `ledgerline_app`, database `ledgerline`, TLS required |
| Render API | `JWT_SECRET_KEY` | Unique generated secret, at least 32 characters |
| Render API | `CORS_ALLOWED_ORIGINS` | `https://ledgerline-frontend-bmtt.onrender.com` |
| Render API | `APP_ENV` | `production` |
| Render API | `LOG_LEVEL` | `INFO` |
| Render API | `APP_NAME` | Optional; defaults to `LedgerLine API` |
| Render API | `JWT_ALGORITHM` | Optional; defaults to `HS256` |
| Render API | `JWT_ACCESS_TOKEN_MINUTES` | Optional; defaults to `30` |
| Render API | `GOOGLE_CLIENT_ID` | Google Identity Services Web Client ID |
| Render API | `OTP_HMAC_SECRET` | Unique random secret, at least 32 characters |
| Render API | `OTP_MAILER_URL` | Deployed Google Apps Script Web App `/exec` URL |
| Render API | `OTP_MAILER_SECRET` | Backend-only shared secret for the Apps Script mailer |
| Render Static Site build | `VITE_API_BASE_URL` | `https://ledgerline-api-9dld.onrender.com` |
| Render Static Site build | `VITE_GOOGLE_CLIENT_ID` | Public Google Identity Services Web Client ID; must match backend `GOOGLE_CLIENT_ID` |
| Local migration/provision/bootstrap process only | `MIGRATION_DATABASE_URL` | Neon direct migration-owner URL; never configured on Render |

`backend/app/core/config.py` loads runtime settings from the API process
environment (or the ignored local `.env`). Set `OTP_MAILER_URL` to the Apps
Script deployment URL and `OTP_MAILER_SECRET` to the matching backend-only
shared secret; retain the separate `OTP_HMAC_SECRET` for OTP digesting.
Alembic independently reads
`MIGRATION_DATABASE_URL` in `backend/alembic/env.py`. Frontend
`VITE_API_BASE_URL` is a public build-time setting, not a secret. Set
`CORS_ALLOWED_ORIGINS` to `https://ledgerline-frontend-bmtt.onrender.com`.
For browser previews or custom domains, add only each exact origin.
`POSTGRES_PASSWORD` and `APP_DB_PASSWORD` in `backend/.env.example` are for the
local Docker Compose bootstrap only; do not configure them on Render or use
them for Neon. `backend/docker/init-app-role.sql` is likewise a local Compose
bootstrap script, not a Neon provisioning script.

### Production deployment and verification

The `/health` route returns `{"status":"ok"}` in the application and is
suitable as Render's liveness health-check path, but it does not check the
database. Financial tables, constraints, deferred triggers, and PL/pgSQL
functions use PostgreSQL features supported by Neon. The project owner
confirms production uses Neon PostgreSQL and Render Free at the URLs above.
The documented connection strategy requires TLS and uses Neon's direct
endpoint for Alembic/provisioning and a pooled endpoint for the API; actual
production connection strings and Dashboard settings were not inspected.
The health endpoint does not independently confirm database readiness.

Use synthetic demonstration data for any further live checks:

1. Health: `curl -fsS https://ledgerline-api-9dld.onrender.com/health` returns
   `{"status":"ok"}`.
2. Database: use a local, hidden-prompt smoke-check script or the API logs to
   confirm API connections authenticate as `ledgerline_app` to `ledgerline`;
   never print the URL. Confirm registration succeeds, which exercises the
   restricted runtime role.
3. HTTPS/CORS: use the deployed frontend origin and verify its browser
   requests reach the HTTPS API. Check a preflight:

   ```sh
   curl -i -X OPTIONS 'https://ledgerline-api-9dld.onrender.com/api/v1/auth/login' \
     -H 'Origin: https://ledgerline-frontend-bmtt.onrender.com' \
     -H 'Access-Control-Request-Method: POST' \
     -H 'Access-Control-Request-Headers: content-type'
   ```

   Confirm `Access-Control-Allow-Origin` exactly matches the frontend origin;
   do not use `*`.
4. Register and log in with synthetic customers, create accounts, and test
   internal deposit, transfer, history, and statements.
5. Public registration only creates `ACCOUNT_HOLDER`. Admin/auditor verification
   requires separately approved synthetic operator-created users. Verify
   admin account/status/reversal/audit functions and auditor read-only access;
   confirm auditor mutations are denied. Never elevate a public registration
   or use real financial/customer records.

## Security and Integrity

Database triggers enforce journal balancing, valid transaction-party mapping,
ledger-to-balance reconciliation, and immutability for posted records. Rejected
business operations are recorded in durable audit and idempotency records
without committing balance or ledger changes. These protections are not
tamper-proof against privileged database operators. No external payment
settlement, multi-currency processing, or cryptographic audit chain is
implemented.

### PostgreSQL runtime least privilege

Migration `20261107_0005` was applied additively to PostgreSQL 17.11 on
`ledgerline` after verifying the existing revision was `20261107_0004`, the
database/schema target was `ledgerline.public`, and existing account-to-ledger
ownership links were consistent. The migration did not drop or recreate
tables, delete records, or reset the Docker volume.

The measured table-level grants changed as follows:

| Table | Before migration | After migration |
|---|---|---|
| `users` | `SELECT`, `INSERT` | `SELECT`; column-limited `INSERT` |
| `accounts` | `SELECT`, `INSERT`; column-limited `UPDATE` | `SELECT`; column-limited `INSERT` and `UPDATE` |
| `ledger_accounts` | `SELECT`, `INSERT`, `UPDATE` | `SELECT`; column-limited `INSERT` |
| `journal_transactions` | `SELECT`, `INSERT`, `UPDATE` | `SELECT`; column-limited `INSERT` |
| `ledger_entries` | `SELECT`, `INSERT`, `UPDATE` | `SELECT`; column-limited `INSERT` |
| `idempotency_records` | `SELECT`, `INSERT`, `UPDATE` | `SELECT`; column-limited `INSERT` |
| `audit_events` | `SELECT`, `INSERT`, `UPDATE` | `SELECT`; column-limited `INSERT` |
| `alembic_version` | `SELECT`, `INSERT`, `UPDATE` | No runtime privileges |

Column-level writes after the migration are exactly:

- `users`: `INSERT (id, email, password_hash)`. Database defaults set
  `role=ACCOUNT_HOLDER` and `status=ACTIVE`; role/status updates are not
  granted.
- `accounts`: `INSERT (id, account_number, owner_user_id, ledger_account_id)`;
  `UPDATE (balance_paise, status, updated_at)`.
- `ledger_accounts`: `INSERT (id, owner_user_id)`. System clearing ledgers are
  provisioned by migrations; customer ledger rows are required by account
  creation.
- `journal_transactions`: `INSERT (id, transaction_type, amount_paise,
  source_account_id, destination_account_id, related_transaction_id,
  initiated_by_user_id)`. Posting status is database-defaulted and transitions
  through a narrowly granted database function.
- `ledger_entries`: `INSERT (id, journal_transaction_id, ledger_account_id,
  entry_type, amount_paise)`.
- `idempotency_records`: `INSERT (id, user_id, idempotency_key, request_hash,
  outcome, journal_transaction_id, result_code)`.
- `audit_events`: `INSERT (id, actor_user_id, journal_transaction_id,
  event_type, outcome, details)`.

The runtime has no sequence privileges, no `alembic_version` access, no
database/schema `CREATE`, no superuser/database-creator/role-creator
attributes, and no role memberships. The live default ACL no longer grants
future tables or sequences to the runtime role. Before migration, the measured
default ACL granted `INSERT/SELECT/UPDATE` on future tables and `SELECT/USAGE`
on future sequences. Future migrations must add only explicitly justified
grants. The two granted functions are the journal posting transition and the
protected journal row lock used during reversal.

Adversarial SQL checks against the live public schema were run as
`ledgerline_app`: explicit ADMIN-user insertion, role/ownership changes,
Alembic history changes, audit/idempotency/journal/ledger mutations, and schema
or role creation each failed with PostgreSQL SQLSTATE `42501`. A direct
inconsistent balance change reached the database consistency trigger and
failed with `P0001`, distinguishing trigger rejection from permission denial.
The PostgreSQL suite also confirmed that a future table receives no runtime
grants.

**Residual trust boundary:** account and customer-ledger inserts must include
`owner_user_id` for normal account creation. A direct-SQL test confirmed the
runtime role can choose an existing user's ID on a new account/ledger pair;
the deferred trigger checks that the pair is linked and has matching owners,
but cannot determine which authenticated application user initiated the SQL.
The API must continue enforcing ownership and authorization. Likewise, the
runtime role can issue account status updates and attempt balance updates on
any row; database triggers reject balances inconsistent with ledger entries,
but role-based authorization and audit attribution for status changes remain
application responsibilities. Runtime credentials are therefore trusted
backend credentials, not per-user database identities.

Historical verification at the restricted-role migration stage (before later
authentication and mailer changes):

- `.\.venv\Scripts\alembic.exe current` and `heads` — `20261107_0005` is the
  current revision and sole head.
- `.\.venv\Scripts\alembic.exe check` — no new upgrade operations detected.
- `.\.venv\Scripts\python.exe -m pytest -q` — **56 passed** (one existing
  Starlette `TestClient` deprecation warning); this is not the latest full
  suite result or a post-mailer test run.
- Direct SQL permission probes against the existing public schema — all 16
  prohibited operations returned SQLSTATE `42501`; inconsistent balance
  mutation was rejected by the database trigger with `P0001`.

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
| [ER Diagram](docs/architecture/erd.mmd.png) | Database entities and relationships |
| [System Architecture Diagram](docs/architecture/system-architecture.md) | Deployment and logical components |
| [Authentication and OTP Flow](docs/architecture/authentication-otp-flow.png) | Password/Google authentication and email OTP sequence |
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
- [x] Deposits, withdrawals, and transfers
- [x] Frontend development
- [ ] Independent security assessment
- [x] Render Free deployment with Neon PostgreSQL

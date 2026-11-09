# LedgerLine Technology Stack

This inventory is based on the committed source, dependency manifests,
deployment configuration, tests, and documented verification. "Active" means
the technology is present and used by the current repository. It does not
mean every production console setting was independently inspected.

## Status key

| Status | Meaning |
|---|---|
| Active | Present in current source or manifests and used by the application or its tests |
| Historical | Previously used or considered; not part of the current runtime path |
| Configured / not independently verified | Present in configuration or user-reported deployment, but external state was not checked from this repository |
| Not used | No repository evidence of use; not claimed as part of the implementation |

## A. Programming languages and data formats

| Technology | Status | Evidence and use |
|---|---|---|
| Python 3.11 | Active | FastAPI application, backend scripts, tests, and Render's `PYTHON_VERSION` setting (`3.11.9`) |
| TypeScript | Active | React application, API client/types, hooks, and Playwright test sources |
| JavaScript | Active | ES module build/test configuration and JavaScript tooling configuration |
| HTML5 | Active | Vite `index.html` application entry |
| CSS3 | Active | Global and component stylesheets, including responsive layouts |
| SQL | Active | Alembic DDL/DML, database constraints/triggers/functions, SQLAlchemy expressions, and PostgreSQL test setup |
| JSON | Active | REST request/response payloads, package manifests, and audit details |
| Graphviz DOT | Active documentation source | Existing system and authentication diagrams |
| Mermaid | Active documentation source | GitHub-rendered transaction and deployment diagrams |

## B. Frontend

Dependencies below are declared in `frontend/package.json`; package lock
versions are resolved by `npm ci`.

| Technology | Status | Purpose |
|---|---|---|
| React / React DOM | Active | Component-based browser application |
| TypeScript | Active | Typed components, API contracts, and frontend logic |
| Vite | Active | Local development server and production bundler |
| Tailwind CSS 3.4 | Active | Utility-first styling, with project CSS for shared components and layout |
| TanStack Query | Active | Server-state caching, query invalidation, and mutation state |
| React Router | Active | SPA navigation, nested routes, and role-aware route guards |
| React Hook Form | Active | Form state and submission handling |
| Zod and `@hookform/resolvers` | Active | Client-side form validation |
| Lucide React | Active | Interface icons |
| Recharts | Active | Data visualizations |
| Vitest | Active | Frontend unit/component test runner |
| Testing Library (`jest-dom`, `react`, `user-event`) | Active | DOM-level component and interaction tests |
| Playwright | Active | Browser end-to-end suite under `frontend/e2e` |
| Oxlint | Active | Frontend lint command (`npm run lint`) |
| TypeScript compiler | Active | Frontend type check (`npm run typecheck`) |
| PostCSS / Autoprefixer | Active | CSS processing in the build toolchain |
| ESLint | Not used | Not declared by the current frontend package manifest; Oxlint is the configured linter |

### Frontend structure and behavior

- `src/App.tsx` creates the query client, authentication provider, browser
  router, lazy-loaded pages, and nested `RequireAuth` / `RequireRole` guards.
- `src/pages/` contains login/registration, dashboard, accounts, money
  operations, statements, transactions, administrator, and audit screens.
- `src/api/` contains typed endpoint wrappers and a shared `fetch` client.
  The client attaches the in-memory bearer token, omits cookies, parses
  integer-paise JSON values without JavaScript number precision loss, and
  maps HTTP failures to a typed API error.
- `AuthProvider` keeps the authenticated profile and token in browser memory.
  A 401 clears the session and query cache. There is no refresh-token flow or
  HttpOnly-cookie session.
- React Hook Form and Zod validate user input before requests; the backend
  independently validates and authorizes every operation.
- Money amounts are converted to integer paise before submission. Transaction
  operations use an idempotency key and keep the exact payload/key in
  tab-scoped `sessionStorage` when the request outcome is ambiguous. This is
  a retry aid, not a replacement for backend idempotency.
- The interface is role-aware, but frontend route hiding is not an
  authorization boundary. FastAPI performs the authoritative checks.

## C. Backend

Declared in `backend/requirements.txt` and confirmed against imports:

| Technology | Status | Purpose |
|---|---|---|
| Python 3.11 | Active | Backend runtime and tests |
| FastAPI | Active | REST API, dependency injection, request/response validation |
| Uvicorn | Active | ASGI server used locally and by Render |
| Pydantic | Active | Request/response models, field constraints, serialization |
| Pydantic Settings | Active | Environment and dotenv-backed runtime settings |
| SQLAlchemy 2.x | Active | ORM, query construction, transaction/session handling |
| Alembic | Active | Additive schema migrations |
| Psycopg 3 | Active | PostgreSQL driver (`psycopg[binary]`) |
| HTTPX | Active | Apps Script mailer HTTPS POST with timeout and redirect following; also used by FastAPI test client stack |
| PyJWT | Active | Signed HS256 access tokens and token validation |
| `argon2-cffi` | Active | Password hashing and verification |
| `google-auth` | Active | Google ID-token verification using Google's public keys |
| Requests | Active / transitive integration | HTTP transport used by `google-auth`'s `google.auth.transport.requests.Request` |
| Pytest | Active | Backend unit, API, and PostgreSQL integration tests |
| `python-dotenv` | Active through settings support | `.env` file parsing for runtime settings and migration URL lookup |
| Resend SDK | Not used | No current Resend dependency or runtime call |

### Backend architecture

The backend is a modular monolith under `backend/app`:

- `api/routes/` exposes authentication, account, transaction, and health
  endpoints; `api/dependencies.py` supplies the database session, JWT user,
  and role checks.
- `schemas/` defines strict Pydantic request and response contracts.
- `models/` defines SQLAlchemy UUID-backed ORM models and constraints.
- `repositories/` holds reusable persistence queries.
- `services/` implements authentication, OTP, Google identity resolution,
  accounts, audits, and financial transaction workflows.
- `core/` contains cached settings, password/JWT helpers, and JSON logging.
- `database/` creates the SQLAlchemy engine/session factory and yields
  request-scoped sessions.

`main.py` configures JSON logging and explicit CORS origins, disables
credentialed CORS, and allows only the configured methods/headers. FastAPI
dependency injection provides request DB sessions and bearer authentication.
Route handlers map expected domain exceptions to HTTP errors; unexpected
database/service errors are not converted into success responses.

Authentication uses Argon2 hashes and signed bearer JWTs. Current-user
validation requires `sub`, `iat`, and `exp`, verifies the configured algorithm
and signature, checks the user status and email verification, and derives
authorization from the database user role rather than trusting a role claim
alone.

## D. Database and financial engineering

| Technology / mechanism | Status | Evidence and role |
|---|---|---|
| PostgreSQL 17 | Active | Local Compose uses `postgres:17`; production is user-confirmed Neon PostgreSQL |
| Neon PostgreSQL | Configured / production, not independently inspected in this audit | Managed production database, as confirmed by project owner |
| SQLAlchemy ORM | Active | Model mapping and application queries |
| Alembic | Active | Seven linear migrations; repository migration head is `20261108_0007` |
| UUID identifiers | Active | User, account, identity, challenge, journal, entry, and audit IDs |
| Integer paise / INR | Active | Amounts and balances are integer minor units; database/model checks restrict currency to INR |
| Double-entry journals | Active | Each posted operation creates debit/credit ledger entries and is checked in PostgreSQL |
| PostgreSQL constraints/triggers | Active | Positive amount, currency, parties, account balance reconciliation, journal balance, linkage, and immutability rules |
| Row-level locks | Active | Account and OTP challenge rows are locked during state changes |
| Advisory transaction locks | Active | Serialize requests scoped to actor and idempotency key |
| Restricted `ledgerline_app` runtime role | Active configuration and historical verification | API runtime permissions are narrower than migration permissions |
| Separate migration connection | Active | Alembic reads `MIGRATION_DATABASE_URL`, separate from API runtime settings |
| Append-only protections | Active for normal runtime role | Database triggers/privileges reject ordinary updates/deletes of posted journals, entries, idempotency, audit, and protected links; database owners remain privileged |
| Compensating reversals | Active | Admin reversal posts a linked opposite journal; it does not rewrite the original |

The primary records include users, Google identities, OTP challenges, customer
accounts, customer/system ledger accounts, journal transactions, ledger
entries, idempotency records, and audit events. Deposits and withdrawals post
against internal clearing ledger accounts. They do not authorize an external
payment or prove external funding.

The runtime role is trusted backend infrastructure, not an end-user identity.
Database constraints protect accounting consistency, but application
authorization is still required. A privileged database owner/superuser can
change schema or disable protections.

## E. Authentication and Google Identity Services

### Password flow

Registration normalizes email, enforces a unique normalized address, hashes
the password with Argon2, and creates an OTP challenge. Login verifies the
password and status before starting the OTP flow. The bearer JWT is returned
only after successful OTP verification.

Duplicate registration intentionally returns a generic challenge-shaped
response without revealing account existence and without sending an email.

### Google flow

The frontend loads Google's Identity Services JavaScript client, renders its
sign-in button, and submits the returned credential (ID token) to
`POST /api/v1/auth/google`. This is a Google Identity Services credential
flow; the repository does not implement a traditional redirect-based OAuth
callback.

The backend uses `google-auth` to verify signature, expiry, and audience
against `GOOGLE_CLIENT_ID`, then checks the issuer, subject, email shape, and
`email_verified` claim. A new identity is mapped to a user. An existing
unlinked account with the same normalized email requires explicit link
confirmation and an email OTP before the Google identity is attached.
`VITE_GOOGLE_CLIENT_ID` is a public client identifier required in the browser;
it is not a client secret. Backend signing/database/mailer credentials and any
Google client secret must never be exposed in `VITE_*` variables or committed.

The repository confirms the client-ID configuration and verification code.
Google Cloud project name, consent-screen publication state, and exact
authorized JavaScript origin list are external console settings and were not
independently inspected in this audit.

### Email OTP controls

- Eight digits from Python's cryptographically secure `secrets` module.
- HMAC-SHA256 digest persisted; plaintext code is not stored in the challenge.
- Five-minute expiry, single-use consumption, and at most five attempts.
- Sixty-second resend cooldown and at most five sends per account/hour.
- Successful verification records an audit event and only then allows JWT
  issuance. A pending Google identity is attached in the successful
  verification transaction.

The current challenge implementation persists challenge state before the
external email request. A mailer delivery error is surfaced; retry timing is
still subject to the challenge cooldown. The email copy and API responses do
not return the OTP.

## F. Email delivery: Apps Script and Gmail

The active runtime provider is a Google Apps Script Web App using Gmail
`MailApp`; Resend is historical, not a current runtime dependency.

```text
FastAPI OTP service
  -> HTTPX HTTPS JSON POST (10-second timeout, follows redirects)
  -> Apps Script Web App doPost(e)
  -> shared-secret validation via Properties Service
  -> Gmail MailApp.sendEmail()
  -> recipient inbox
```

The request contains `secret`, `email`, and `code`. The backend checks the
final HTTP status and requires a JSON object with `ok: true`; HTTP errors,
invalid JSON, or any other body become an OTP delivery failure. The expected
Apps Script property name is `LEDGERLINE_MAILER_SECRET`; it must match
backend `OTP_MAILER_SECRET`. The backend URL is configured as
`OTP_MAILER_URL`. No live URL or secret value is included here.

Google's daily send quota depends on account type and applicable Workspace
policy; consult current Google Apps Script `MailApp` quotas for the deploying
account. Delivery is subject to those limits and Gmail policies.

Resend was initially configured/considered. Project verification records a
reported HTTP 403 from the `onboarding@resend.dev` testing sender when sending
to a recipient other than the Resend account owner's address. The project
switched to Apps Script/Gmail; current backend requirements and source contain
no Resend integration.

## G. DevOps, cloud, and local development

- Git and GitHub: private repository, `main` branch, with committed milestone
  history. Reviewer access must be granted by the repository owner if needed.
- Render Web Service: FastAPI/Uvicorn API; `/health` is configured as its
  liveness path. Free services can spin down after inactivity. The Render
  manifest defines build/start commands and public service origins but does
  not contain secrets.
- Render Static Site: Vite production build, `dist` publication, and SPA
  fallback rewrite to `/index.html`.
- Neon: production PostgreSQL over TLS. The documented connection strategy
  uses a pooled runtime URL and a direct, privileged migration URL. Production
  branch/compute settings were not independently inspected in this audit.
- Alembic migrations run out-of-band from the Render Web Service; do not run
  a privileged migration as part of API startup.
- Local development uses Python 3.11 virtual environments, Docker Desktop /
  Compose with PostgreSQL 17 bound to loopback port 5433, Node.js/npm, and
  Vite. Windows PowerShell setup is documented in the root README.
- Google Identity Services requires a configured Web Client ID and an
  authorized browser origin. Exact Google Cloud console configuration was
  not inspected.
- The Render Blueprint does not establish that automatic deployment from
  `main` is enabled; deployment trigger settings are external Dashboard
  configuration.
- No repository evidence was found for Kubernetes, AWS, Azure, Terraform, or
  a CI/CD workflow; none is claimed.

Project-owner-provided deployment investigation history: Resend custom-domain
verification was considered; Namecheap access was unavailable and Cloudflare
nameserver activation was not completed. DNS/custom-domain mail delivery is
not active; Apps Script/Gmail was selected without a custom sending domain.

## H. Tooling, previous choices, and unverified claims

| Technology or service | Classification |
|---|---|
| Resend | Historical provider attempt; replaced by Apps Script/Gmail; no current source dependency |
| Google Apps Script Web App / Gmail MailApp | Active external mail delivery, according to current implementation and owner-provided deployment facts |
| Render Free / Neon PostgreSQL | Configured/live deployment according to owner; external account/branch settings not inspected |
| PostgreSQL local Compose | Active development/test support |
| ESLint | Not used by current manifest; Oxlint is used |
| Graphviz executable | Not installed in the current environment; existing DOT sources and diagram exports are present |
| Kubernetes, AWS, Azure, Terraform, CI/CD workflows | Not used / no repository evidence |
| Google Cloud project and OAuth console details | Configured for the live flow by owner report; exact project/origins/consent settings not independently verified |

For detailed routes, configuration names, migration history, security risks, and
verification qualifications, see [Project Documentation](PROJECT_DOCUMENTATION.md),
[API Reference](API_REFERENCE.md), [Environment Configuration](ENVIRONMENT_CONFIGURATION.md),
[Project Development History](PROJECT_DEVELOPMENT_HISTORY.md), and
[Threat Model](../THREATS.md).

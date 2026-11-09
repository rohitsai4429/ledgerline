# Environment Configuration

This reference lists names and safe descriptions only. Configure actual
credentials in the relevant provider's secret store or ignored local
environment file. Never copy a real value into documentation, Git, logs, or
the frontend bundle.

## Render backend Web Service

| Variable | Required / type | Purpose |
|---|---|---|
| `DATABASE_URL` | Required secret | Neon pooled PostgreSQL runtime URL using the restricted `ledgerline_app` role and TLS |
| `JWT_SECRET_KEY` | Required secret, at least 32 characters | HS256 JWT signing key |
| `GOOGLE_CLIENT_ID` | Public identifier | Expected Google ID-token audience |
| `OTP_HMAC_SECRET` | Required for OTP, secret, at least 32 characters | HMAC-SHA256 OTP digest key |
| `OTP_MAILER_URL` | Required for delivery | Google Apps Script Web App `/exec` endpoint |
| `OTP_MAILER_SECRET` | Required for delivery, secret | Shared request secret; matches Apps Script property `LEDGERLINE_MAILER_SECRET` |
| `CORS_ALLOWED_ORIGINS` | Required deployment configuration | Exact frontend origin, `https://ledgerline-frontend-bmtt.onrender.com` |
| `APP_ENV` | Configured | `production` |
| `LOG_LEVEL` | Configured | `INFO` |
| `APP_NAME` | Optional | Defaults to `LedgerLine API` |
| `JWT_ALGORITHM` | Optional | Defaults to `HS256` |
| `JWT_ACCESS_TOKEN_MINUTES` | Optional | Defaults to 30 |
| `PYTHON_VERSION` | Configured by Render Blueprint | `3.11.9` |

The checked-in `render.yaml` includes only some environment variables. It
does not embed credentials and does not currently declare `GOOGLE_CLIENT_ID`,
`OTP_HMAC_SECRET`, `OTP_MAILER_URL`, or `OTP_MAILER_SECRET`; add those through
the Render backend service environment settings as appropriate. Confirm actual
Dashboard values without printing them.

## Render frontend Static Site

| Variable | Required / type | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | Public URL | Production API base URL: `https://ledgerline-api-9dld.onrender.com` |
| `VITE_GOOGLE_CLIENT_ID` | Public identifier | Google Identity Services Web Client ID used by browser code |
| `NODE_VERSION` | Blueprint configuration | `24.22.1` |

The checked-in Render manifest sets `VITE_API_BASE_URL` but does not declare
`VITE_GOOGLE_CLIENT_ID`; configure it in the Static Site build environment if
Google sign-in is enabled. Every `VITE_*` value is shipped to the browser.
Never put private credentials in these variables.

## Local backend (`backend/.env`)

Copy `backend/.env.example` to the ignored `backend/.env` and set:

| Variable | Purpose |
|---|---|
| `APP_NAME`, `APP_ENV`, `LOG_LEVEL` | Local service identity and logging |
| `DATABASE_URL` | Local PostgreSQL URL using restricted runtime role |
| `POSTGRES_PASSWORD` | Local Compose bootstrap role only |
| `APP_DB_PASSWORD` | Local Compose runtime role password |
| `MIGRATION_DATABASE_URL` | Local-only privileged direct URL for Alembic/provisioning |
| `JWT_SECRET_KEY` | Local JWT signing key; replace placeholder |
| `JWT_ACCESS_TOKEN_MINUTES` | Optional token lifetime |
| `GOOGLE_CLIENT_ID` | Google ID-token audience, if testing Google login |
| `OTP_HMAC_SECRET` | OTP digest key |
| `OTP_MAILER_URL` | Apps Script Web App URL for mail delivery |
| `OTP_MAILER_SECRET` | Shared secret for mailer |
| `CORS_ALLOWED_ORIGINS` | Local frontend origin(s) |

`MIGRATION_DATABASE_URL` is intentionally not part of `Settings`; Alembic and
local scripts load it separately. Never configure the migration owner URL on
the long-running Render API. URL-encode credentials in PostgreSQL URLs.

## Local frontend (`frontend/.env`)

Copy `frontend/.env.example` to ignored `frontend/.env`.

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Defaults to local FastAPI `http://127.0.0.1:8000` |
| `VITE_GOOGLE_CLIENT_ID` | Public Google Web Client ID for browser sign-in |

## Google Cloud / Google Identity Services

Configure a Google OAuth 2.0 Web Client and use the same public client ID in
backend `GOOGLE_CLIENT_ID` and frontend `VITE_GOOGLE_CLIENT_ID`. Add the exact
local and deployed JavaScript origins in Google Cloud configuration. The
project uses the Google Identity Services credential response; no Google
client secret belongs in the SPA. The exact Cloud project identifier, consent
publication state, and origin list are not stored in this repository and were
not independently verified during the documentation audit.

## Apps Script Script Properties

| Property | Purpose |
|---|---|
| `LEDGERLINE_MAILER_SECRET` | Shared secret validated by the Apps Script Web App; must match backend `OTP_MAILER_SECRET` |

Do not include the deployment URL or secret in public documentation. Google
MailApp sending quotas depend on account type and Google policy; check the
current official quota for the account that owns the script.

## Migration-only configuration

| Variable | Where | Purpose |
|---|---|---|
| `MIGRATION_DATABASE_URL` | Trusted local migration/provisioning process only | Direct privileged Neon PostgreSQL connection |

Keep migration credentials separate from Render runtime credentials. The API
does not load this variable into its Pydantic settings.

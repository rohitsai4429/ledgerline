# LedgerLine web application

The React/Vite application consumes the existing FastAPI service; it does not
provide mock balances, transaction records, or audit events.

> LedgerLine is a demonstration financial ledger. Transactions update internal
> account records and do not move real money through banks or payment providers.

## Features and roles

- **Account holders:** register/sign in, open accounts, view internal ledger
  balances, post internal deposits/withdrawals/transfers, browse transactions,
  and view statements.
- **Administrators:** search/filter accounts, load API-backed account details,
  change permitted account status, review system-wide transactions and audit
  events, and reverse eligible transactions after explicit confirmation.
- **Auditors:** read-only account, transaction, per-account debit/credit
  statement, reference and audit-event views. There are no auditor mutation
  controls.

Every financial value is sourced from the API. Account balances cannot be
edited through the UI. Frontend role checks are navigation aids, not a
replacement for backend authorization.

## Local setup

Use Node.js 20.19+ (or 22.12+) and npm. From `frontend`:

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

By default the app calls `http://127.0.0.1:8000`. Set
`VITE_API_BASE_URL` in the ignored local `.env` file to the reachable API
origin when it differs. This is a public build-time URL, not a place for
credentials. Start the backend separately; its default CORS allow-list
includes `http://localhost:5173` and `http://127.0.0.1:5173`.

The frontend test and release checks are:

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

The production output is `dist/`. `public/_redirects` provides the SPA
fallback for static hosts that support the Netlify redirects format. Vite's
development and preview servers also fall back to `index.html`.

## Backend API integration map

Requests use JSON and `Authorization: Bearer <access_token>` after sign-in.
Errors are parsed from FastAPI's `{ "detail": ... }` response shape. Amounts
sent to transaction endpoints are integer INR paise. The browser client parses
paise integers from raw response JSON into decimal strings so large balances
and amounts are not rounded by JavaScript number parsing.

| Method and endpoint | Request | Response used by the app | Access and relevant errors |
|---|---|---|---|
| `POST /api/v1/auth/register` | `{email, password}` | OTP challenge (`challenge_id`, expiry and resend interval) | Public; always `ACCOUNT_HOLDER`; `422` invalid input |
| `POST /api/v1/auth/login` | `{email, password}` | OTP challenge; never a LedgerLine token | Public; `401` invalid credentials, `403` disabled user, `422` invalid input |
| `POST /api/v1/auth/google` | `{credential, confirm_account_link?}` | OTP challenge or explicit account-link confirmation | Public; backend verifies the signed Google ID token; `401` invalid credential |
| `POST /api/v1/auth/otp/verify` | `{challenge_id, code}` | `{access_token, token_type, expires_in}` | Public; token is issued only after a valid single-use code |
| `POST /api/v1/auth/otp/resend` | `{challenge_id}` | Generic resend response | Public; subject to cooldown and hourly limits |
| `GET /api/v1/auth/me` | None | Safe user profile | Bearer auth; `401` invalid/expired token or unavailable user |
| `POST /api/v1/accounts` | Empty JSON object | Account including account number, status, integer-paise balance, ledger account ID, timestamps | Account holder; `201`; `403` wrong role, `422` writable fields rejected, `503` account number unavailable |
| `POST /api/v1/accounts/recipient-lookup` | `{account_number}` | Available destination account UUID and masked account number | Account holder; `404` unavailable recipient, `422` invalid account number |
| `GET /api/v1/accounts` | None | Array of accounts | Authenticated; holder sees own accounts, admin/auditor see all; `401` unauthenticated |
| `GET /api/v1/accounts/{account_id}` | UUID path parameter | Account | Authenticated; holder ownership is enforced; `404` unavailable/not owned, `422` invalid UUID |
| `PATCH /api/v1/accounts/{account_id}/status` | `{status: "ACTIVE" \| "FROZEN" \| "CLOSED"}` | Updated account | Admin only; `403`, `404`, `409` closed-account transition, `422` invalid input |
| `POST /api/v1/transactions/deposits` | `{account_id, amount_paise}` and `Idempotency-Key` header | Posted transaction | Authenticated; service enforces account-holder ownership and active status; `403`, `404`, `409`, `422` |
| `POST /api/v1/transactions/withdrawals` | `{account_id, amount_paise}` and `Idempotency-Key` header | Posted transaction | As above; `409` includes insufficient funds |
| `POST /api/v1/transactions/transfers` | `{source_account_id, destination_account_id, amount_paise}` and `Idempotency-Key` header | Posted transaction | Authenticated; source ownership and both account statuses checked; `403`, `404`, `409`, `422` same-account |
| `POST /api/v1/transactions/{transaction_id}/reverse` | `Idempotency-Key` header; empty JSON body | Reversal transaction | Admin only; `403`, `404`, `409` if disallowed/already reversed |
| `GET /api/v1/transactions` | Optional `account_id`, `limit` (1–500), `offset` | Array of transactions | Authenticated; holder activity is scoped to owned accounts; `401`, `404`, `422` |
| `GET /api/v1/accounts/{account_id}/statement` | Optional timezone-aware `start` and `end` query values | Account ID, currency, opening/closing paise, actual ledger entries and running balances | Authenticated; owner/admin/auditor access rules; `404`, `422` |
| `GET /api/v1/audit-events` | Optional `actor_user_id`, timezone-aware `start`, `limit` (1–500), `offset` | Array of audit events | Admin/auditor only; `403`, `422` |

Financial endpoints require a non-empty idempotency key (up to 128 characters).
For a network failure or server error, the exact request and key are kept in
tab-scoped `sessionStorage`; retrying the unchanged request reuses the key.
Changing its payload is blocked until the pending request is resolved. A
successful response or a definitive client error clears that pending request.
The key is not regenerated for an ambiguous retry.

## Authentication and authorization notes

Password registration/login and Google Identity Services all require an
eight-digit email OTP before the API installs a LedgerLine bearer JWT. Google
uses the public build-time `VITE_GOOGLE_CLIENT_ID`; backend-only credentials
must never be put in a `VITE_` variable. The frontend keeps the LedgerLine
access token in JavaScript memory only; a page reload requires signing in
again. It does not use `localStorage` or claim memory-only storage prevents
XSS. All role guards in React are for navigation and user experience; the
backend remains the authorization boundary. Registration never accepts a role.

There is no raw journal-line endpoint. The app uses the account statement's
actual entries for ledger details, the transaction-history endpoint for
transaction records, and the audit-events endpoint for audit data.
Transfers accept the destination UUID returned by
`POST /api/v1/accounts/recipient-lookup`; the frontend displays only the
masked account number before confirmation. Transaction search and type
filtering are limited to the currently loaded API page; account filtering and
pagination use the API.
Admin account searching filters the account list returned by the existing
accounts endpoint.

## Separate deployment

Build the static frontend with `npm run build` and deploy `dist/` to a static
host. `VITE_API_BASE_URL` is embedded at build time and must point to the
deployed API. On the backend set `CORS_ALLOWED_ORIGINS` to the exact deployed
frontend origin(s), comma-separated; do not use a wildcard for credentialed
origins. The backend currently disables credentialed CORS because auth uses
bearer tokens. Configure the static host to rewrite unknown application paths
to `index.html`; `public/_redirects` is the Netlify-compatible rule. No
`VITE_*` variable should contain a secret.

Known limitations: there is no external payment integration, token refresh or
HttpOnly-cookie auth; public signup cannot create privileged roles; there is no
raw journal-wide entries endpoint; and transaction free-text/type searches do
not cover records outside the currently loaded API page.

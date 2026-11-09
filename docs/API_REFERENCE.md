# LedgerLine API Reference

Base path: `/api/v1` (health is `/health`). JSON validation and errors use
FastAPI/Pydantic response behavior. Authenticated endpoints require
`Authorization: Bearer <LedgerLine JWT>`. The JWT is issued only after OTP
verification.

## Authentication

| Method and path | Auth | Request / purpose | Success | Main errors |
|---|---|---|---|---|
| `POST /api/v1/auth/register` | Public | `{ "email", "password" }`; password minimum 12 characters, maximum 128 | `202`, generic `OTP_REQUIRED` challenge | `422` invalid fields; delivery/configuration failures `503` |
| `POST /api/v1/auth/login` | Public | `{ "email", "password" }` | `202`, OTP challenge | `401` invalid credentials; `403` disabled account; `429` cooldown/rate window; `503` verification/delivery unavailable |
| `POST /api/v1/auth/google` | Public | `{ "credential", "confirm_account_link": false }` | `202`, OTP challenge or `LINK_CONFIRMATION_REQUIRED` | `401` invalid credential; `503` Google config or OTP delivery unavailable; `429` cooldown |
| `POST /api/v1/auth/otp/verify` | Public challenge | `{ "challenge_id", "code" }`, code is exactly eight digits | `200`, bearer JWT and expiry | `400` invalid/expired/replayed code; `422` malformed body; `503` OTP configuration unavailable |
| `POST /api/v1/auth/otp/resend` | Public challenge | `{ "challenge_id" }` | `202`, generic resend response | `429` cooldown/hourly cap; `503` delivery/configuration failure |
| `GET /api/v1/auth/me` | Any active, verified user | No body | `200`, safe profile | `401` absent/invalid/expired/unverified credentials |

Duplicate registration intentionally returns a generic challenge-shaped
response without sending an email. This avoids account-existence disclosure;
the challenge ID in that response is not a valid new-user OTP challenge.

For Google account linking, a first request for a Google subject whose email
matches an existing account returns `LINK_CONFIRMATION_REQUIRED` and does not
send a code. A second request with `confirm_account_link: true` starts the
OTP-protected link flow.

## Accounts

`ACCOUNT_HOLDER` can create accounts and access owned resources; `ADMIN` and
`AUDITOR` can read system-wide account data. Only `ADMIN` can update account
status.

| Method and path | Role | Request / purpose | Success | Main errors |
|---|---|---|---|---|
| `POST /api/v1/accounts` | `ACCOUNT_HOLDER` | Empty/no writable fields; creates a zero-balance account | `201`, account | `422` writable fields; `503` account number allocation failure |
| `POST /api/v1/accounts/recipient-lookup` | `ACCOUNT_HOLDER` | `{ "account_number": "LL##########" }` | `200`, destination UUID and masked account number | `404` unavailable recipient; `422` invalid format |
| `GET /api/v1/accounts` | Any authenticated role | No body | `200`, list (holders see owned accounts) | `401` invalid session |
| `GET /api/v1/accounts/{account_id}` | Any authenticated role | UUID path | `200`, account if permitted | `404` missing or non-owned account for holder |
| `PATCH /api/v1/accounts/{account_id}/status` | `ADMIN` | `{ "status": "ACTIVE" \| "FROZEN" \| "CLOSED" }` | `200`, updated account | `403` role denied; `404` unknown account; `409` closed account cannot be reactivated; `422` invalid status |

## Financial transactions, statements, and audit

All transaction create/reversal endpoints require the `Idempotency-Key`
header (1–128 characters). Bodies reject extra fields and require a positive
integer `amount_paise`; currency is INR-only.

| Method and path | Role | Request / purpose | Success | Main errors |
|---|---|---|---|---|
| `POST /api/v1/transactions/deposits` | `ACCOUNT_HOLDER` | `{ "account_id", "amount_paise" }`; internal clearing-to-customer entry | `201`, transaction | `403` denied role; `404` account; `409` inactive/limit/rejection; `409` same key with changed payload; `422` invalid request |
| `POST /api/v1/transactions/withdrawals` | `ACCOUNT_HOLDER` | `{ "account_id", "amount_paise" }`; customer-to-internal-clearing entry | `201`, transaction | Above, plus `409` insufficient funds |
| `POST /api/v1/transactions/transfers` | `ACCOUNT_HOLDER` | `{ "source_account_id", "destination_account_id", "amount_paise" }` | `201`, transaction | `403`, `404`, `409` inactive/insufficient funds/idempotency conflict, `422` same account or invalid request |
| `POST /api/v1/transactions/{transaction_id}/reverse` | `ADMIN` | Original UUID and idempotency header; posts a linked compensating journal | `201`, reversal transaction | `403`, `404`, `409` reversal unavailable/already reversed/idempotency conflict |
| `GET /api/v1/transactions` | Any authenticated role | Optional `account_id`, `limit` (default 100, max 500), `offset` (default 0) | `200`, history list | `401`; ownership restrictions are enforced server-side |
| `GET /api/v1/accounts/{account_id}/statement` | Any authenticated role | Optional timezone-aware `start` and `end` | `200`, INR statement with entries and running balances | `401`, `404` inaccessible account, `422` invalid date range |
| `GET /api/v1/audit-events` | `ADMIN`, `AUDITOR` | Optional `actor_user_id`, `start`, `limit` (default 100, max 500), `offset` | `200`, audit list | `401` absent/invalid token; `403` insufficient role |
| `GET /health` | Public | No body | `200`, `{"status":"ok"}` | Does not establish database readiness |

Business rejection status codes are mapped by the service: insufficient funds,
inactive accounts, duplicate reversals, and balance limits are conflicts;
account/transaction not found is not found; a same-account transfer is
unprocessable. A same idempotency key with a different payload is `409`.
Validation errors are `422`; malformed/expired JWTs return `401`; role failures
return `403`.

Deposits and withdrawals post only internal LedgerLine entries. No external
bank/payment settlement is initiated.

# LedgerLine Project Development History

This chronology combines committed history on `main` (dated 7–9 November
2026) with the engineering notes in [`PROMPTS.md`](../PROMPTS.md). Commit
dates establish repository order, not the exact time of every deployment or
external-console action. Verification claims below are identified as
historical when they predate later changes.

## Chronological milestones

| Date | Commit / evidence | Objective and implementation | Verification / result |
|---|---|---|---|
| 2026-11-07 | `6b51d18`, `4137439` | Initialize the project, requirements, baseline documentation, and repository conventions. | Project and initial requirements recorded. |
| 2026-11-07 | `fbbb8f8`, `5f53139`, `b73db7f`; `PROMPTS.md` Database Architecture Review | Select an internal-ledger model and distinguish customer accounts from accounting ledger accounts. Create initial architecture and ERD artifacts. | ERD reviewed; later migrations and database tests provide implementation evidence. |
| 2026-11-07 | `d1e2367`, `d8a3e2c` | Establish the FastAPI modular-monolith scaffold, database setup, configuration, and environment/build-file exclusions. | Backend startup and test/dependency workflows recorded in later entries. |
| 2026-11-07 | `56e1dd1`; `PROMPTS.md` Authentication API | Add users, normalized email, Argon2 password hashing, JWT authentication, role checks, `/me`, and migration `0001`. | Nine auth tests plus health test passed in the historical entry. |
| 2026-11-07 | `c9089a9`; `PROMPTS.md` Account Management | Add customer and ledger account models, generated account numbers, integer-paise balances, ownership controls, status management, and migration `0002`. | Historical record: nine PostgreSQL account tests and 19 total tests passed. |
| 2026-11-07 | `7c549f2`; `PROMPTS.md` Financial Transaction Engine | Add clearing ledger accounts, journal transactions, debit/credit entries, audit, idempotency, statements, reversals, database validation, and migration `0003`. | Historical record: 35 tests passed, including PostgreSQL transaction/concurrency checks. |
| 2026-11-07 | `684148e`; `PROMPTS.md` LedgerLine React Frontend | Build the React/Vite/TypeScript SPA, auth pages, dashboards, account and money-operation screens, admin/auditor routes, API client, and frontend tests. | Historical record includes lint/typecheck/build and 13 frontend tests across seven files. |
| 2026-11-07 | `4284e7d` | Configure frontend/API CORS for browser integration. | A local Vite-origin preflight was recorded as passing in project notes. |
| 2026-11-07 | `8ce1511`; `PROMPTS.md` Security and Financial-Integrity Review | Address audit gaps, loopback-bind local PostgreSQL, separate runtime/migration credentials, and add migration `0004`. Add `THREATS.md`. | Historical security review and regression tests recorded; it was not a comprehensive penetration test. |
| 2026-11-07 | `8ce1511`/follow-up hardening; `PROMPTS.md` PostgreSQL Runtime Least-Privilege Hardening | Restrict runtime DB privileges and default grants, separate Alembic credentials, and add migration `0005`. | Historical PostgreSQL direct-SQL permission probes and backend tests recorded; residual runtime-role trust boundaries remain documented. |
| 2026-11-07 | `c527065` | Expand technology-stack decision records. | Documentation change. |
| 2026-11-08 | `952976e` | Prepare Render deployment and browser end-to-end validation. | E2E suite and local test procedure documented; a previous Playwright journey was reported passed. |
| 2026-11-08 | `4d0ecde`, `e8a8de4` | Correct static publish configuration and record the actual Render service URLs. | Deployment configuration commits; they do not prove current external dashboard settings by themselves. |
| 2026-11-08 | `0d8b76c` | Add recipient account-number lookup and verified-recipient transfer workflow. | Existing PostgreSQL account/transaction tests cover recipient lookup and transfers. |
| 2026-11-08 | `e3121e2`; `backend/alembic/versions/20261108_0006_google_email_otp_auth.py` | Add Google Identity Services sign-in, persistent email OTP challenges, explicit account linking, and migration `0006`; migration `0007` resets legacy verification values lacking OTP audit evidence. | Project records a live password OTP flow and Google account-link flow; migration repository head is `0007`. |
| 2026-11-09 | `0a4514c` | Replace Resend delivery with a Google Apps Script Web App/Gmail MailApp integration. Configure `OTP_MAILER_URL` and `OTP_MAILER_SECRET`; use HTTPX, timeout, redirect following, HTTP/JSON success checks. | Focused OTP/authentication/health suite: 37 passed after integration, according to the supplied verification report. The 75-test full backend suite predates this integration. Fresh registration to a different recipient remains unverified. |
| 2026-11-09 | `2030454` | Update project documentation and architecture artifacts following the mailer integration. | Latest documentation commit supplied by the owner; it is not asserted here as the current deployed backend commit. |
| 2026-11-09 | Current documentation pass | Audit tracked source/manifests, correct deployment/provider descriptions, add technical/API/environment/history references, and add Mermaid transaction/deployment diagrams because Graphviz is unavailable. Preserve the existing modified ERD image. | Documentation checks and staged-file scope are reported in the completion summary. |

## Engineering evolution

### Architecture and database model

The early design review separated customer-facing accounts from the ledger
accounts used by journal entries. Migrations `0001`–`0005` progressively
created users/accounts, financial records, nullable audit actors, and
runtime-role hardening. Migrations `0006` and `0007` add provider identities
and OTP challenges and correct legacy verification-state backfill. The
repository has a single Alembic head, `20261108_0007`.

### Financial transaction design

Transactions use integer paise and INR-only records. A successful operation
updates balances, creates a journal and debit/credit entries, stores the
idempotency outcome, and records the audit event within a database transaction.
Database checks/triggers validate account and journal relationships. Account
row locks serialize conflicting balance operations; advisory transaction
locks serialize a user's repeated idempotency key. A reversal is a new,
linked compensating journal.

### Security and operational decisions

The threat review prompted credential-free authentication/account audit
events, a nullable audit actor for anonymous events, loopback-only local
PostgreSQL binding, and a least-privilege API role separate from the migration
owner. These controls narrow ordinary runtime operations; they do not prevent
a database owner from changing the database or bind SQL to a human user.

### Authentication and email provider evolution

Password authentication predates Google sign-in. Google Identity Services
provides a signed ID-token credential to the SPA, which submits it to FastAPI
for server-side validation. Same-email account linking requires explicit
confirmation and OTP verification. OTP plaintext is emailed but only its
HMAC-SHA256 digest is stored for verification.

Resend was initially configured. Project verification reported its test sender
rejected messages to non-owner recipients. Custom-domain verification was
considered, but the owner reports that Namecheap access was unavailable and
Cloudflare nameserver activation was not completed. The project then adopted
Apps Script and Gmail MailApp without a custom sending domain.

### Deployment and current verification boundary

The repository contains Render Blueprint definitions and service URLs; the
owner confirms the frontend/backend are deployed on Render Free and the
production database is on Neon PostgreSQL. Exact current service commit,
Neon branch/compute, and external Dashboard values are not inferable from Git
alone.

Known test evidence is time-scoped:

- 75 backend tests passed before the Apps Script integration.
- 37 focused OTP/authentication/health tests passed after integration,
  according to the supplied report.
- Earlier frontend unit tests passed 16 tests across eight files; earlier
  typecheck, lint, and build results are recorded in `PROMPTS.md`.
- A previous Playwright end-to-end journey was reported passed.
- Password login/OTP and Google sign-in/account linking were live-tested
  successfully. Registration to a recipient other than the Apps Script
  owner's address remains to be verified after the mailer change.

None of these historical results is presented as a fresh run of every test in
the current tree.

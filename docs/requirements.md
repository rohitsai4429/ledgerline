
# LedgerLine — Requirements Document

## 1. Project Overview

LedgerLine is a financial transaction management
system designed to ensure secure money movement,
accurate financial records and verifiable ledger entries.

## 2. Business Objective

Build a reliable financial system that supports
deposits, withdrawals and account transfers while
preventing duplicate transactions, negative balances,
unauthorised access and ledger tampering.

## 3. User Roles

### Administrator
- Manage financial accounts.
- View system transactions.
- Review audit events.
- Perform authorised administrative operations.

### Account Holder
- View their own accounts.
- Deposit money.
- Withdraw money.
- Transfer money.
- View account statements.

### Auditor
- View financial transactions.
- Inspect ledger entries.
- Verify debit and credit records.
- Review audit history.
- No permission to modify financial records.

## 4. Functional Requirements

FR-01: User authentication.

FR-02: Role-based access control.

FR-03: Account creation and management.

FR-04: Deposit functionality.

FR-05: Withdrawal functionality.

FR-06: Internal account transfers.

FR-07: Double-entry bookkeeping.

FR-08: Idempotency and duplicate prevention.

FR-09: Concurrent transaction protection.

FR-10: Transaction history and statements.

FR-11: Audit logging.

FR-12: Ledger integrity verification.

## 5. Business Rules

BR-01: Transaction amounts must be positive.

BR-02: Account balances must never become negative.

BR-03: Every posted journal transaction must balance.

BR-04: Every financial operation must be atomic.

BR-05: Duplicate requests must not execute twice.

BR-06: Users cannot access unauthorised accounts.

BR-07: Auditors have read-only permissions.

BR-08: Posted ledger entries cannot be modified or deleted.

BR-09: Failed transactions must not change balances.

BR-10: Corrections must use reversal entries.

BR-11: All monetary values must use integer minor units.

BR-12: Account balances must reconcile with ledger entries.

## 6. Initial Scope Assumptions

- Currency: INR only.
- Transfers: Internal account-to-account.
- Overdrafts: Not permitted.
- Account ownership: Individual ownership.
- Joint accounts: Out of initial scope.
- External payment gateways: Out of initial scope.
- Foreign exchange: Out of initial scope.
- Fees: Out of initial scope.
- Reversals: Supported through compensating entries.

These assumptions must be checked against the official challenge brief.

## 7. Non-Functional Requirements

- Security
- Reliability
- Data consistency
- Concurrency safety
- Auditability
- Maintainability
- Availability
- Usability

## 8. Financial Integrity Requirements

- Debit and credit postings must balance per currency.
- Concurrent withdrawals must not overspend.
- Idempotency keys must be unique within their scope.
- Reusing a key with a different payload must be rejected.
- Posted ledger records must remain immutable.
- Cached balances must be reconcilable with ledger entries.

## 9. Acceptance Criteria

AC-01: Successful transfer updates both accounts correctly.

AC-02: Insufficient balance causes rejection.

AC-03: Repeated transfer requests produce one posting.

AC-04: Concurrent withdrawals cannot overspend.

AC-05: Unauthorised account access is rejected.

AC-06: Auditors cannot perform financial transactions.

AC-07: Ledger modifications are rejected.

AC-08: Failed postings roll back all financial changes.

AC-09: Every posted transaction has balanced debit and credit entries.

AC-10: Account statements match the ledger.

## 10. Technology Stack

Backend: Python + FastAPI

Database: PostgreSQL

ORM: SQLAlchemy

Migrations: Alembic

Frontend: React + Vite

Styling: Tailwind CSS

Testing: Pytest

Authentication: JWTf

Password Hashing: Argon2

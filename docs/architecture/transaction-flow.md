# Transaction lifecycle

This workflow describes the implemented API and PostgreSQL transaction path.
Business rejection and database failure do not produce a partial successful
financial posting. A reversal is a new linked journal entry; the original
posted transaction is not edited.

```mermaid
flowchart TD
    A[Client sends operation and Idempotency-Key] --> B[FastAPI bearer authentication]
    B --> C[Role and account ownership authorization]
    C --> D[Pydantic request validation]
    D --> E[Begin PostgreSQL transaction]
    E --> F[Acquire user and idempotency advisory transaction lock]
    F --> G{Idempotency record exists?}
    G -- Same key and payload --> H[Return prior result]
    G -- Same key, changed payload --> I[Reject with conflict and audit]
    G -- No --> J[Lock affected account rows in stable UUID order]
    J --> K{Active and sufficient balance?}
    K -- No --> L[Record rejection and idempotency outcome]
    K -- Yes --> M[Update account balance]
    M --> N[Create journal transaction]
    N --> O[Create debit and credit ledger entries]
    O --> P[Create success idempotency and audit records]
    P --> Q[Deferred PostgreSQL constraints/triggers validate]
    Q --> R{Commit succeeds?}
    R -- No --> S[Rollback financial writes]
    R -- Yes --> T[Return transaction result]
    U[Admin requests reversal] --> V[Authorize ADMIN and lock original journal]
    V --> W[Create linked compensating journal and opposite entries]
    W --> P
    W -. Original posted journal remains unchanged .-> X[Immutable history]
```

Editable GitHub Mermaid source: [transaction-flow.mmd](transaction-flow.mmd).
# LedgerLine Architecture Pack

This folder contains three complementary views of the system:

| Artifact | Purpose | Source of truth |
|---|---|---|
| `system-architecture.md` | Current GitHub-rendered system and secret-boundary overview | `system-architecture.mmd` |
| `system-architecture.png` / `.svg` | Static architecture snapshots; not regenerated in this pass | `system-architecture.dot` |
| `authentication-otp-flow.png` / `.svg` | Password + Google auth and OTP email sequence | `authentication-otp-flow.dot` |
| `transaction-flow.md` | GitHub-rendered transaction and compensating-reversal workflow | `transaction-flow.mmd` |
| `deployment-architecture.md` | GitHub-rendered deployment and secret boundaries | `deployment-architecture.mmd` |
| `erd.mmd.png` | Database entities and relationships | Existing ERD source / SQLAlchemy models and Alembic migrations |

## Important distinction

The Apps Script mailer is an external delivery integration. It does not add a new database entity, so it does not require an ERD change by itself. If a schema or model migration is introduced later, regenerate and review the ERD from the actual models/migrations.

## Regenerate architecture images

From the repository root, with Graphviz installed:

```powershell
dot -Tpng docs/architecture/system-architecture.dot -o docs/architecture/system-architecture.png
dot -Tsvg docs/architecture/system-architecture.dot -o docs/architecture/system-architecture.svg
dot -Tpng docs/architecture/authentication-otp-flow.dot -o docs/architecture/authentication-otp-flow.png
dot -Tsvg docs/architecture/authentication-otp-flow.dot -o docs/architecture/authentication-otp-flow.svg
```

Graphviz was not available during the final documentation pass. The current
system, transaction, and deployment diagrams therefore use Mermaid embedded
in Markdown, which GitHub renders without generated image binaries. The
older system/authentication PNG and SVG snapshots were not regenerated.

Never commit credentials, OTP values, Google client secrets, database passwords, or mailer shared secrets in diagrams or documentation.

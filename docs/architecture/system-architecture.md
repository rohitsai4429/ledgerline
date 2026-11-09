# System architecture

The application is a modular monolith deployed as separate frontend and
backend Render services. The FastAPI backend connects to Neon PostgreSQL over
TLS using a restricted runtime role. Schema changes use a separate privileged
migration connection. Google Identity Services supplies ID-token credentials;
Google Apps Script and Gmail MailApp deliver OTP messages.

```mermaid
flowchart LR
    Browser[User browser]
    Static[Render Free Static Site<br/>ledgerline-frontend-bmtt.onrender.com]
    Api[Render Free Web Service<br/>ledgerline-api-9dld.onrender.com]
    Google[Google Identity Services]
    Neon[(Neon PostgreSQL<br/>production)]
    Script[Google Apps Script Web App]
    Gmail[Gmail MailApp]
    Inbox[Recipient inbox]
    Repo[Private GitHub repository]
    Migration[Trusted migration process<br/>direct privileged connection]
    RuntimeSecrets[Backend-only secrets<br/>JWT and OTP HMAC keys<br/>mailer secret and DATABASE_URL]
    PublicConfig[Browser-visible settings<br/>API base URL and Google Web Client ID]
    Boundary[Internal demonstration ledger<br/>No bank/payment settlement]

    Browser --> Static
    Browser -->|HTTPS JSON + bearer JWT| Api
    Static -->|VITE_API_BASE_URL| Api
    Browser -->|Google credential| Google
    Google -->|ID token| Browser
    Browser -->|Credential + client ID| Api
    Api -->|TLS pooled runtime URL| Neon
    Migration -->|TLS direct privileged URL| Neon
    Api -->|HTTPS JSON POST<br/>follows response redirect| Script
    Script -->|MailApp.sendEmail| Gmail
    Gmail --> Inbox
    Inbox -. OTP entered by user .-> Browser
    RuntimeSecrets -. Render backend environment .-> Api
    PublicConfig -. Static build environment .-> Static
    Repo -.->|exact deployment trigger unverified| Static
    Repo -.->|exact deployment trigger unverified| Api
    Neon --- Boundary
```

The editable [Mermaid source](system-architecture.mmd) is the current
GitHub-rendered view. The existing PNG/SVG are static snapshots generated
before this final consistency pass; Graphviz was unavailable to regenerate
them. The editable Graphviz source is
[system-architecture.dot](system-architecture.dot). The
[deployment architecture Mermaid source](deployment-architecture.mmd) adds
the GitHub source boundary and explicitly notes that the current Render
auto-deployment trigger was not independently verified.

The product boundary is an internal demonstration ledger only. It does not
initiate or settle real payments.
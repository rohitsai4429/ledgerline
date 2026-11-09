# Deployment architecture

This deployment view separates public browser configuration from backend
secrets. GitHub is the private source repository. The exact Render
auto-deployment trigger is external Dashboard configuration and was not
independently verified.

```mermaid
flowchart LR
    Dev[Maintainer / Git client] --> Repo[Private GitHub repository<br/>main branch]
    Static[Render Free Static Site<br/>ledgerline-frontend-bmtt.onrender.com]
    Api[Render Free Web Service<br/>ledgerline-api-9dld.onrender.com]
    Repo -.->|exact deployment trigger unverified| Static
    Repo -.->|exact deployment trigger unverified| Api
    Browser[User browser] --> Static
    Browser -->|HTTPS JSON + bearer JWT| Api
    Static -->|VITE_API_BASE_URL| Api
    Api -->|TLS pooled runtime URL<br/>ledgerline_app| Neon[(Neon PostgreSQL<br/>production)]
    Migration[Trusted local migration process<br/>MIGRATION_DATABASE_URL] -->|TLS direct privileged URL| Neon
    Browser -->|Google Identity Services credential| Google[Google Identity Services]
    Google -->|ID token| Browser
    Browser -->|Credential + public Web Client ID config| Api
    Api -->|HTTPS JSON POST<br/>OTP_MAILER_URL + OTP_MAILER_SECRET| Script[Google Apps Script Web App]
    Script -->|MailApp.sendEmail| Gmail[Gmail MailApp]
    Gmail --> Inbox[Recipient inbox]
    Secrets[Backend-only secrets<br/>JWT_SECRET_KEY<br/>OTP_HMAC_SECRET<br/>OTP_MAILER_SECRET<br/>DATABASE_URL] -. Render environment .-> Api
    Public[Browser-visible configuration<br/>VITE_API_BASE_URL<br/>VITE_GOOGLE_CLIENT_ID] -. Static build environment .-> Static
    Boundary[Internal demonstration ledger only<br/>No bank/payment settlement]
    Neon --- Boundary
```

Editable source: [deployment-architecture.mmd](deployment-architecture.mmd).

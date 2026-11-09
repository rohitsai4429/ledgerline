# LedgerLine — Final Release & Submission Checklist

## A. Source control

- [ ] Review local `git status --short`.
- [ ] Confirm the intended OTP mailer code and its tests are present.
- [ ] Do not stage local `.env`, `.env.runtime`, credential files, private keys, or secrets.
- [ ] Preserve unrelated edits (especially `docs/architecture/erd.mmd.png`) unless deliberately reviewing and including them.
- [ ] Run `git diff --check` and `git diff --cached --check`.
- [ ] Run the complete backend tests after the Apps Script integration.
- [ ] Commit source integration, then commit documentation/architecture assets.
- [ ] Push `main` and record the resulting commit hash.

## B. Render deployment

- [ ] `ledgerline-api` deploys the final source commit and shows Live.
- [ ] `ledgerline-frontend` remains Live; confirm it still points to the intended `main` commit.
- [ ] Backend environment has `OTP_MAILER_URL`, `OTP_MAILER_SECRET`, and `OTP_HMAC_SECRET`.
- [ ] `OTP_MAILER_SECRET` matches the Apps Script Script Property `LEDGERLINE_MAILER_SECRET`.
- [ ] No secret appears in frontend `VITE_*` variables or Git.
- [ ] Health endpoint returns HTTP 200.

## C. Live smoke tests

- [ ] Fresh registration to an email other than the Apps Script owner's email: mail arrives, OTP verifies, dashboard opens.
- [ ] Password sign-in: OTP arrives, OTP verifies, dashboard opens.
- [ ] Google sign-in for a new Google identity: expected OTP flow succeeds.
- [ ] Google sign-in matching an existing password account: explicit link confirmation, OTP verification and dashboard access succeed.
- [ ] Existing transfer workflow completes and balances update correctly.
- [ ] Statements / transaction history render.
- [ ] Audit view is visible only to authorized roles and remains read-only where expected.

## D. Evidence for submission

Capture fresh screenshots from the final deployment:

1. Landing / sign-in screen.
2. Dashboard with representative account data.
3. Accounts page.
4. Transfer form and completed transfer result.
5. Transaction history / statement.
6. Audit page (with an authorized account).
7. OTP email received (hide the code and personal details).
8. Google account-link confirmation flow (hide personal information).
9. Render services showing Live and final commit.

## E. Final submission notes

- Use the deployed frontend URL: `https://ledgerline-frontend-bmtt.onrender.com`.
- Use the API URL: `https://ledgerline-api-9dld.onrender.com`.
- Include the GitHub repository URL only if the hiring team has been granted access; it is currently private.
- Describe LedgerLine as an internal demonstration ledger. Do not claim bank/UPI/card settlement, externally funded deposits, or compliance certification.
- Record the final commit hash after successful push; do not reuse the previous `e3121e2` hash as the final release hash.

# SP26 — First authorized browser final-submit path

Plan: CV-first journey P0-C and the missing one-use employer browser final click.

## Progress from SP24/SP25

SP24 fixed the first-party Komplyint OIDC browser review; SP25 reconciled submitted status with agent follow-up scheduling. The original SmartPloy SP15 system already had owner-scoped CV and application workspaces, a signed-in reviewed packet, two-person employer rights, 90-second final approval, a PostgreSQL cross-device sticky one-attempt claim and a Chrome MV3 companion. What it lacked was the first-party one-use reservation route and actual reviewed browser final-click adapter.

## Implemented path

1. Applicant selects a supported fresh Lever posting, prepares/approves CV and cover letter, records signed-in review and opens the exact employer /apply form.
2. Companion verifies review from a SmartPloy OIDC tab, fills approved fields and a verified exact PDF only after applicant consent; employer-specific questions, CAPTCHA, legal and sensitive fields stay human-operated.
3. After personally reviewing the form, applicant returns to signed-in SmartPloy and clicks Reserve ONE reviewed final click.
4. New POST /api/v1/application-workspaces/{id}/browser-final-attempt is OFF by default. When operator enabled, it requires authentic OIDC and exact Origin/user, independent reviewed employer rights scoped to that exact job and browser action, current document/job/email/CV/PDF hashes, prior review and explicit final consent.
5. Reuses PostgresEmployerFinalActionGate.approve plus consume_once_for_trusted_adapter. These atomically commit a one-attempt marker across devices; route makes NO external employer call. A broken response or browser failure MUST NOT lead to an automatic retry.
6. Chrome stores a short-lived, nonbearer fingerprint marker in session. Applicant returns to the same employer form, checks all required fields and gives an additional explicit final-click confirmation.
7. A Chrome exclusive Web Lock is acquired, a permanent browser local no-retry marker is written BEFORE employer interaction, session authorization is consumed, and a self-contained Lever-only form adapter checks exact origin/job, only one enabled final button, no CAPTCHA, required fields, CV PDF size plus SHA-256, approved name/email and cover letter when present. Then it clicks that ONE button without retry.
8. Browser click is an ATTEMPT, not a provider acknowledgement. Existing observed receipt import remains separately labeled; a real official partner API application ID is stronger proof. Uncertain outcome remains for reconciliation.

## Reuse evidence

Original first-party modules reused: employer_final_action_gate, employer_submit_claim_storage, employer_automation_rights, employer_review_intent_storage, existing OIDC signed-in request checks, immutable browser packet, application workspaces, browser companion form/attachment helpers, attempt-lock and Chrome session storage.

Extended: api.py, popup.mjs, review-bridge.mjs, popup.html, deployment Compose API-only env and contracts.

New source only: page-final-claim.mjs and page-final-submit.mjs plus signed-in Postgres and Node/DOM tests. No new dependency, browser background runner, broad host permission, web auth, personal-data storage or second employer ledger.

## Production status and safeguards

Flag SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED defaults false and exists ONLY in API container. No operator permissions were granted by this implementation; no employer application was actually sent. Only explicitly employer-authorized jobs with independently reviewed source/terms and a real applicant final click can be eligible.

Exact source must pass GitHub CI and native ObumDelivery release qualification, be deployed via the original OVH guarded backup/migrations + image identity gate and undergo two-user ZITADEL acceptance and a real partner review. Unsupported forms and ambiguous outcomes require review. This feature is NOT unattended general ATS autoapply.

## Next core task

Use the existing browser and provider integration to cover individually reviewed additional employer forms and actual provider acknowledgments. Run per-job agents headlessly for safe job matching, preparation and follow-up; do not silently claim employer submissions without acknowledgment.

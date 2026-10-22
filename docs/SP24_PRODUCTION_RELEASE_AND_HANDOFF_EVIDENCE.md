# SP24 — Komplyint production release readiness and browser handoff repair

**Date:** 22 October 2026  
**Delivery area:** SmartPloy SP21 P0-C, Agentic SmartPloy Gate 1/2 production activation, ObumDelivery independent release.  
**Current production target:** `https://smartploy.komplyint.fi` (first-party ZITADEL OIDC).  
**Important:** Checked-in documentation and passing GitHub tests do not deploy code.

## What was actually checked live

Public, unauthenticated `https://smartploy.komplyint.fi/healthz` returned:
- `ok=true`, `service=smartploy`
- `public_origin=https://smartploy.komplyint.fi`
- `storage.mode=postgres`, `storage.ready=true`
- `worker.configured=true`, `worker.ready=true`, `worker.count=31`
- `access.enabled=false`, `access.environment=production`
- `obumai_configured=false`
- `external_actions_authorized=false`

This health format did **not** provide its deployed Git commit. It cannot
prove that the SP21, SP22 or SP23 merged code is on OVH, that migrations 025/026
are present, or that application-agent wakeups are registered. The signed-in
site and independent CI service did not return accessible content from the
public read-only probe. No authenticated host or Woodpecker release session
was available to perform a controlled deploy.

## New code in SP24

A blocking browser companion defect was confirmed from source:
`browser-companion/review-bridge.mjs` and `page-review.mjs` trusted only
`https://smartploy.obumai.com` whereas the active production hostname and
issuer policies target `https://smartploy.komplyint.fi`.

The code now uses an exact closed pair of first-party origins, applies the
same first-party list in the injected self-contained page verifier, rejects
nested frames, refuses any redirected signed-in review request, and requires
the existing verified OIDC user+matching packet/hash. It does not acquire
cross-domain cookies, bearer tokens, arbitrary host permission or browser
final-submit authority. Old host compatibility remains OIDC-only.

Existing build provenance is also **reused**: `Dockerfile` already sets
`SMARTPLOY_APP_VERSION` from the 12-character checked-out release SHA.
The public `/healthz` response now exposes only that validated 12-hex
`release_revision`. The guarded OVH `deploy.sh` and
`release-evidence.sh` fail if the running public health revision disagrees
with the reviewed source and already-verified running image. A healthy
outdated container must not receive a success receipt. No secret is displayed.

## Reuse evidence vs original code

**Reused existing:** MV3 companion activeTab/isolated verifier, original
`/verify-reviewed-packet` owner/CSRF/revision checks, short-lived
`chrome.storage.session` digest, existing partner submit claim and
review-first browser policy, release Docker build tag and operation-lock /
backup / migration / rollback / image-identity scripts.

**New:** tightly scoped dual-origin OIDC handling and redirect/frame fences,
public revision fingerprint with release-script check, and synthetic Node,
Python, Docker and browser regressions. No second authentication system,
crawler, application-worker daemon or third-party dependency was added.

## Release operator execution contract (no secrets in issue or chat)

1. Qualify the latest **merged main SHA** with 5/5 GitHub checks AND native
   ObumDelivery exact-checkout positive/negative receipts where configured.
2. Use the already committed `deploy/personal/scripts/deploy.sh` on the
   original OVH server with its existing restricted private env and
   `SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc`; production requires
   `SMARTPLOY_RELEASE_APPROVED_SHA` exactly matching the approved main SHA.
3. The existing script obtains the deployment lock, creates a verified DB
   backup, applies all ordered migrations (through 026), builds/recreates
   only the required services, probes Docker health, rejects stale images,
   checks the new public health revision, and performs OIDC public acceptance.
   Never remove the PostgreSQL data volume or overwrite `deploy/personal/env`.
4. Complete signed-in two-account functional QA and test a real owner-scoped
   CV-first application + Agent Zero case. Confirm source freshness and
   opt-in auto-draft sources, then enable the optional
   `SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=true` **only if** migrations 025/026,
   loopback worker health and a real browser-closed wakeup are verified.
5. Independently capture `deployed-sha`, deployed image IDs, current source
   and selected OIDC policy, release-evidence JSON/text, actual origin, live
   signed-in acceptance, worker wake/event and previous known-good rollback
   revision. Do not write a success badge before those are independently real.

## Application and agentic product gate after this fix

- **Manual:** CV → current jobs → workspace draft → user opens/finishes the
  employer's website; applicant can self-report what happened.
- **Assisted:** same CV/job/workspace; exact owner-verified 15-minute packet,
  extension inspection, consented fill and PDF attachment, human final click,
  browser-observed receipt import.
- **Authorized Lever partner:** fresh reviewed CV, consent and employer rights
  ledger → one-shot durable claim → official provider API → independently
  acknowledged provider application ID. No automatic retry on uncertainty.
- **AutoApply fleet:** matching/drafting/agent reminders are source features.
  Fully automated browser final submission across arbitrary ATS forms remains
  **not implemented**. Unsupported sites stay at human-review handoff, not
  falsely marked submitted. No rights circumvention, anti-bot bypass or
  unattended unconsented employer contacts.
- **Next engineering slice:** link provider acknowledgments and candidate
  self-reports to accurate per-case agent wake timing; then read-only scoped
  ObumConnect recruiter matching with candidate-confirmed outcomes. Use
  ObumAI only as a budgeted, permission-bounded reasoning helper.

## Stage report

- **Done in source:** OIDC companion hostname fix; bounded public release
  fingerprint; guarded receipt mismatch check; new no-send security tests.
- **In progress:** exact-head CI, merge; coordination with ObumDelivery.
- **Blocked:** OVH release control/credentials not available from connected
  GitHub/browser session; native release approval and two-account signed-in QA
  cannot be fabricated.
- **Not started:** unauthorized universal headless final submit, production
  ObumAI send/voice or real employer calls.

**Do not interpret a GitHub commit, public health `ok`, or synthetic Docker
smoke as evidence that a new release is deployed on OVH.**

# SP52 — Authenticated Ashby partner submission through existing SmartPloy one-shot claim

**Date:** 26 October 2026 (Finland)  
**Baseline:** SP51 main `81c0fe79cb7e3985a45cd6f9f77d5670d6b53f68`  
**Plan:** SP21 P0-C automatic final submission only after individually authorized employer integration and fresh applicant review  
**Scope:** source implementation + synthetic real PostgreSQL/OIDC and provider MockTransport, **not** live employer acceptance or an authorized OVH deployment.

## Exact progress vs SP51

SP51 had an isolated, **dormant** official Ashby transport. SP52 adds the
missing first-party binding: strict employer rights, signed-in ownership,
approved current CV/job/contact, a reviewed form, fresh final applicant
confirmation, an immutable one-use claim, and a genuine Ashby application
reference stored with the original workspace. It does not create a second
submission engine or grant any source/LLM/agent the right to send.

### Reused original product code

- Original `SmartployAuthenticationMiddleware`, signed-in OIDC cookie
  and `X-Smartploy-Expected-User-Id`/same-origin mutation checks.
- Existing `smartploy_employer_automation_rights` two-**distinct** authorized
  reviewer table (separate permission evidence, terms evidence, bounded expiry).
- The original `PostgresEmployerReviewIntentRepository` has already
  implemented a domain-separated **Ashby review key**, including same-posting
  `/application` vs plain URL continuity, owner-bound reviewed CV/PDF SHA
  and 10-minute revocable review. SP52 reuses that **exact** key for
  provider-scoped rights/claim, never treats review as submission authority.
- Original `PostgresEmployerFinalActionGate.approve` + `consume_once_for_trusted_adapter`:
  independent second final consent, 90-second owner/job/approved-contact
  fingerprint, locks/rechecks owner, source-current job and unedited saved
  review, then **one sticky PostgreSQL claim in the same transaction**.
  The original Lever/browser final-click actions remain Lever-only;
  cross-provider rights are NOT interchangeable.
- Existing `make_browser_packet` private approved CV/contact hashes,
  `render_document(kind="cv",file_format="pdf")`, original workspace/
  provider-receipt transaction, and original Application Studio two gestures.
- SP51 official Ashby transport: exact published/allowed hosted job, pinned
  independently reviewed form schema, no custom/required legal questions
  or surveys, **one** multipart POST, nonblocked form response, then an
  independent read-only `application.info` lookup for actual application ID.
  Unknown response/timeout/5xx never silently creates a new attempt.

### Original SP52 work

1. New reentrant migration `024_ashby_partner_application.sql` adds
   `partner_ashby_application_form_submit` to the **distinct action-scope**
   constraints, admits `provider='ashby'` to the original provider receipt
   table, and stores the **submitted-form UUID separately** from the true
   application UUID with uniqueness and validation. No duplicate ledger.
2. Extend `employer_job_key(application_url, action_scope=...)` solely for
   this new scope, using the original reviewed Ashby domain-separated hash.
   The browser-final and Lever rights paths are unchanged and still refuse
   Ashby. A forged alternate source key cannot get a second claim.
3. Extend the same `PostgresEmployerFinalActionGate` owner-locked
   preflight with `assisted_review_only=True` **only** for the exact Ashby
   partner action. Approved employer rights are checked again inside the
   **approval+reservation** transactions. The authorization and claim
   remain unavailable to unsigned/other-user callers.
4. Reuse `PostgresPartnerApplicationReceipts` for both providers.
   Only an original reserved claim with the same verified owner, URL and
   workspace can atomically persist the two genuine Ashby IDs and change
   the original workspace to `provider_acknowledged`. No self-report
   or hiring-acceptance inference.
5. Reuse `api.py`'s exact same-origin reviewed submit logic and original
   no-retry/uncertainty branch in `_submit_to_authorized_partner`.
   Distinct private endpoints are:
   `GET /api/v1/application-workspaces/{id}/partner-ashby-readiness`,
   `GET /api/v1/application-workspaces/{id}/partner-ashby-receipt`, and
   `POST /api/v1/application-workspaces/{id}/partner-ashby-apply`.
   The **only** call to the provider transport is after a committed
   sticky claim, and only from explicit signed-in POST.
6. Reuse the existing Application Studio reviewed CV intent, separate
   human final confirmation, exact current PDF/contact SHA and once-only
   send lock. Show the actual provider and receipt; never label an Ashby
   acknowledgment as Lever or treat a form-instance reference as the
   application reference. Unsupported jobs keep the manual/handoff option.

## Proof / synthetic test coverage

- The original OIDC/PostgreSQL fixture has **two different subject/user
  identities with the same email** and a real current job/workspace/CV.
  It is reused with an exact Ashby hosted application URL, server-issued
  synthetic employer key and verified reviewed-form SHA.
- Real FastAPI signed-in acceptance verifies no rights ⇒ no transfer,
  no signed-in review ⇒ no transfer, wrong origin/user, explicit false
  consent ⇒ no transfer, then exact approved double-reviewed rights and
  final consent ⇒ one HTTPX-mocked Ashby multipart POST. A true provider
  application ID and submitted form ID persist with `provider_acknowledged`
  without any self-reported status or editable documents.
- Second request and second OIDC account cannot access the first user's
  receipts or send the same employer job; earlier source variants share the
  same hashed job claim and are read-only deduplicated.
- A 503 provider outcome returns `202 outcome_uncertain`, sticky claim,
  no receipt or false `applied`, and **zero repeat POSTS**.
- Changing reviewer identities to the same person, revoking rights,
  mismatched job/form identity and missing custom/legal/consent answers
  fail closed. Existing Lever, browser-final and Greenhouse manual paths
  must still pass their original tests.
- React tests verify an approved Ashby user can review/confirm only
  via the Ashby endpoint, not Lever, and without copied CV/PII clipboard.
- Require all five exact PR-head and independently merged-main jobs,
  including full PostgreSQL, React/MV3, Chromium and isolated Docker
  Compose smoke. CI is never a real employer acknowledgment.

## Remaining operational gates

- Obtain genuine employer-owned Ashby `jobsRead`, `candidatesWrite`
  and `candidatesRead` API permissions, independently audited posting
  and terms, current form digest and server-only key. A public job listing
  or Ashby board-read API is NOT submission permission.
- Complete authenticated, approved ObumDelivery enrollment, immutable SHA
  native CI, guarded OVH staging + production rollout with backups/rollback,
  release-revision proof and signed-in browser acceptance. The ObumDelivery
  SmartPloy inventory still has `enabled:false` and the public health
  endpoint does not attest the exact running revision.
- Verify real, consenting-employer application acknowledgment, scoped rate
  limits, legal/recruiter workflow, and special consent questions before
  claiming live Ashby AutoApply. Unsupported employers remain manual.
- Agent Zero follow-up outside app (real emails/calls), broad provider
  coverage, arbitrary CAPTCHA bypass and unattended final sends are NOT
  implemented by SP52.

**No new external runtime dependency, AI engine, credential in Git, employer
rights issuer, broad web-click adapter or unattended send task.**

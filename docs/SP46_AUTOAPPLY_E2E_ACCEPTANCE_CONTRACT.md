# SP46 — Executable AutoApply end-to-end acceptance contract v1

**Date:** 26 October 2026 (Finland)  
**Baseline:** SP45 source main `4921f26a36789935eadd5118797d2513ec8afac7`  
**Priority:** P0 true end-to-end operation, separate from production credentials

## Goal, truthful completion boundary

Prove, with ONE integrated and repeatable acceptance contract, that the
**actual original SmartPloy APIs, stored documents, PostgreSQL, source
provenance, applicant identity, employer rights and per-job agent** work
together: source-current Finnish IT job → signed-in owner uploads one CV →
approved career facts and AutoApply opt-in → private job match and draft
→ one persistent case agent → reviewed CV PDF/letter → independently
employer-authorized Lever posting → fresh explicit final applicant consent
→ **one** reviewed multipart submission → employer-provider-shaped ID
stored atomically → agent event/follow-up-ready state. No fake production
application and no new generic browser-submit engine.

This is **integration acceptance in an isolated test environment**. The
synthetic test transport is deliberately NOT proof of a real provider
acknowledgment or real production browser installation. To be considered
production-accepted, the real operator still needs authenticated signed-in
test, independent exact-job employer permission and credentials, and at
least one genuine authorized provider response, plus source/release SHA and
native ObumDelivery evidence.

## How to run (no real employer traffic)

In the same isolated PostgreSQL test environment used by current GitHub
CI (migrations and developer dependencies already installed):

```sh
pytest -q tests/test_autoapply_e2e_contract.py
```

The dedicated **GitHub Actions `AutoApply E2E contract`** step and
**native ObumDelivery/Woodpecker `python-postgres`** stage execute this
exact test, after the existing full pytest suite, on actual PostgreSQL.
No other emulator/server, external project, browser or live API credentials
are required. These three cases assert one full contract with different
external outcomes: **provider-shaped ACK**, **provider 429 uncertain**,
and **missing independently approved employer rights**.

## Actual reused, executable components

| Stage | Original running code reused | Contract assertion |
| --- | --- | --- |
| 1 — Job | `domain.normalize_observation`, direct ATS `SourcePolicy`, `PostgresJobRepository` | Fresh approved Finnish IT posting, stable exact Lever job URL; not manual/unknown source |
| 2 — Account | ZITADEL-mode `SmartployAuthenticationMiddleware`, original OIDC session, `PostgresIdentityRepository` | Authenticated principal; same email alone never authorizes another OIDC user |
| 3 — CV | `cv_import.parse_cv`, `PostgresCVRepository` | Real text DOCX uploaded through first-party API, decoded and owner-bound |
| 4 — Match | `PostgresSearchPreferenceRepository`, `search_jobs`, `auto_draft_shortlist.prepare_profile_shortlist` | Explicit personalized opt-in, source freshness, fit gates; one private draft, idempotent rerun; zero employer calls |
| 5 — Case | `PostgresApplicationAgentRepository`, original applicant case workflow | Exactly one durable Agent Zero with its first real event; NO background email/call/provider submit |
| 6 — Review | `PostgresWorkspaceRepository`, `render_document`, `make_browser_packet`, signed-in review intent | Saved revision + real deterministic PDF, approved nonbearer hashes and explicit review |
| 7 — Rights | Two-reviewer `smartploy_employer_automation_rights`, Lever registry | A configured partner key alone never grants employer submit; missing rights must deny with zero provider transport |
| 8 — Transfer | Existing `employer_final_action_gate` and sticky `employer_submit_claims`, `LeverPartnerTransport` | Separate fresh per-job user approval; exactly one same-host GET and one multipart POST only after all gates |
| 9 — Receipt | `PostgresPartnerApplicationReceipts.record`, original workspace | Provider ACK ID and `provider_acknowledged` stored together; 429 remains uncertain, NOT accepted |
| 10 — Agent | Existing `application_agents.reconcile_workspace_updates`, event history | ACK creates one `application_provider_acknowledged` event; uncertain does not; neither case sends unauthorized follow-ups |
| 11 — Safety | Same-email two OIDC principals, non-PII readiness, sticky job claim | Account isolation, exact revision/identity, no duplicate second POST on replay, no silent retry |

## Synthetic test boundaries

- Live ATS fetch: **not** invoked; fixture uses original approved source
  normalization and original Postgres jobs. Separate original public ATS
  tests cover actual response parsing and Finnish filtering.
- External employer transport: replaced ONLY within this test by a local
  `httpx.MockTransport`; the request host/URL/form/PDF still pass through
  the real production Lever transport code.
- Real candidate content: synthetic DOCX/contact/letter; no credentials.
  Employer keys and approvals are fictional and scoped to one randomly
  generated posting in the isolated test DB, never enabled in OVH.
- Browser companion: independently tested in existing real Chromium
  cases; the API partner path intentionally does NOT need it.
- Employer submission: only a genuine authorized live partner's
  acknowledgement can be called a real delivered application; a local
  mock response is a **contract test**, not a job application.

## Formal failure rules

- Job source missing/stale/untrusted, incomplete CV or unapproved facts:
  stop before private AutoApply draft. No employer action.
- Wrong user, unrelated same-email OIDC subject, request origin, stale
  document hashes, unsigned review, missing rights: fail closed, no POST.
- After a provider attempt starts: atomic cross-device claim is permanent.
  A normal provider ACK advances original workspace and case; 429,
  timeout, malformed response or uncertain result requires human
  reconciliation. A second request is denied, even if the first result
  was unknown. Never fabricate a confirmation.
- Workers and agents cannot submit, send mail, accept consents or create
  employer rights on their own.

## Real-operator acceptance after source CI

1. Merge exact green head; verify independent merged-main GitHub CI. Obtain
   a native ObumDelivery exact-SHA negative-control receipt.
2. Deploy approved SHA using original guarded OVH backup/migration/
   image/health/Caddy-companion source-equality checks. Capture
   `release_revision` and real release-evidence file. No fake deployment
   declaration from green GitHub Actions.
3. Sign in to `smartploy.komplyint.fi` with one real test owner and a
   separate second owner. Upload/review CV, search current Finland IT jobs,
   opt into drafts+agents, verify source worker's fresh actual data.
4. Pick one posting with **independently documented employer partner
   permission**. Configure exact employer job/key safely only on the API
   container; two independent reviewers attest rights. No bypassing
   employer terms/CAPTCHA or unknown screening requirements.
5. Approve exact job/CV/letter in SmartPloy; confirm fresh explicit final
   permission once; submit one consenting standard Lever job.
6. Require genuine Lever-issued `applicationId` and correct owner-bound
   source revision, no second request, no cross-user visibility, and
   agent reconciliation in the actual running worker. Test injected
   429/timeouts separately against a **staging/mock provider**, never
   deliberately error-submit real applications.
7. Separately test real Chrome companion installation + approved field
   assistance on a consenting employer sandbox. Ashby/Greenhouse final
   action remains manual until independently integrated and permitted.
8. Keep all unsupported postings in human handoff. Record resulting
   production evidence and only then advertise a functioning supported
   AutoApply integration.

**Scope still outstanding:** provider partnerships/credentials, real
production release, signed-in browser acceptance, authorized final
execution for non-Lever providers, external agent email/call/response
watching, and legal/policy sign-off for each outbound channel. Full
unattended application to every job anywhere in Finland is not claimed.

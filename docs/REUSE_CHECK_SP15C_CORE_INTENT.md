# SP15c REUSE-CHECK: exact employer final-review intent (18 Oct 2026)

DRAFT source-only, NOT an employer submission, execution lease, browser grant or deployed release.

## Existing product code verified and reused BEFORE implementation

| Origin | Inspected source blob | Reuse decision |
| --- | --- | --- |
| SmartPloy employer claim storage, PR #160 | b659a5e768f043d783cabd52688adf44987741cd | **REFACTOR/ADAPT** 73 previously implemented lines of SQL owner/quarantine/workspace/job/document/receipt/CRM checks into shared transactional verification helper. Both claim and review-intent call the same helper, not a rewritten duplicate |
| SmartPloy OIDC, tenant_context, CSRF and account-switch, PR #161 | integrated c7f9578efe79283871d7a225d67be9cffc7b76ad | **REUSE** in place for signed-in same-origin API, and web private-read/mutation checks. No replacement authentication stack |
| SmartPloy deterministic browser packet | df744c723dc5b253ac5e2af91127c089f3f1a67c | **REUSE** server-computed CV PDF SHA and immutable CV+letter hash. No new renderer or browser |
| ObumAI Agent B final preflight | b5c5e99e008162f43efa09d05582856bcf05300e | **ADAPT design**: source/doc evidence checks, no actuation; do not import 703-line engine just to duplicate SmartPloy |
| ObumAI Agent D control plane + adapter | e6259a75b3bf4aecfb514e3b9747760a5a4b2770 + 549109fb05eaa7a76a34c73042fade85de539043 | **ADAPT model**: review != authorization != execution lease, in-memory authority unsuitable for cross-device |
| ObumAI one-time OAuth state | ab9a6c96f5b2b4d73bc1259a65356488351067e2 | **ADAPT expiry/idempotency** with SmartPloy PostgreSQL instead of a second state store |
| ObumAI enterprise approval policy | 4434122ae2c842c31bae827e7eeb085e4aa1dbc0 | **REUSE refusal posture**, not broad permission to browser.submit |

Checked agent repos obumai/obumbrowse, obumai/ObumForge, obumai/ObumConnect,
obumai/ObumAICore: each currently has only 1-2 files on main, no
ready-to-use application grant bridge to adapt. Do not count as reused systems.
Prior 28 external family audit stays unchanged: **no third-party code copied**,
no new dependencies, no license bypass.

## Only genuinely new parts (from scratch)

- New employer review domain: smartploy/employer_review_intent_storage.py.
  Stores just account/profile, normalized employer job, workspace/revision,
  immutable reviewed-document hash, PDF hash, 10-minute expiry, cancelled/pending
  state. No bearer token, CV/contact text or employer site action.
- New schema: migrations/020_employer_review_intents.sql. Unique account +
  employer job intent with atomic PostgreSQL renew-after-expiry/cancel.
- Existing API, ApplicationStudio and account-erasure inventory **adapted**, not
  replaced. A user must approve an exact CV PDF/letter/job, backend recomputes
  SHA and rechecks saved owner/posting/receipt and prior immutable claim.
  A separately recorded review expires and can be cancelled.
- New synthetic PostgreSQL race/tenancy/stale-document/security tests and web
  account-switch/review action tests, reusing existing suites.

## What this does NOT prove

No final action is enabled; employer permission and terms are NOT verified.
No extension claim redemption, cross-device final click, employer-confirmed
receipt, ObumDelivery native Woodpecker product run or OVH release has occurred.
A pending review is NOT a submitted job, receipt or employer authorization.

Release HOLD. Record CI counts only after verifying exact current head.

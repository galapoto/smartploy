# SP15d: SOURCE PROVENANCE AND CORE-PROGRESS ACCEPTANCE

18 October 2026. Review-only. NO employer final-click capability. No real
applicant, employer request, new paid CI, or production deployment.

## Step 1. Existing code checked FIRST (actual file blobs, not names)

| Previously built product | Source blob or exact inherited SHA | What was reused or adapted | New code avoided |
| --- | --- | --- | --- |
| SmartPloy MV3 companion popup and strict packet validation | browser-companion/popup.mjs blob 9cb7fcdb860183a99c24781f73b7a1be4ce2fc87, logic.mjs blob aa2d77a1e302b2ff9c7aad46de53dfaf50632467 | Reused activeTab, scripting, employer host/path/TTL/privacy validation, approved field fill and reviewed PDF/question transfer. Added one first-party verification action before existing fill/attach. | No second browser engine, no content-script autoinject, no persistent host permission or background worker |
| SmartPloy cookie authentication and same-origin CSRF | smartploy/oidc.py blob 015ca5df354979b090384b5aa6efc2a3f34e2cb6, api.py SP15c blob ace27d6b66ea5755a31f9b748c4011162794edab | Reused OIDC-bound session endpoint, authenticated tenant_context, exact Origin + Sec-Fetch-Site cookie write checks and X-Smartploy-Expected-User-Id account-switch precondition | No new SSO, OAuth or CORS bypass |
| SmartPloy reviewed job and PDF renderer | browser_handoff.py blob df744c723dc5b253ac5e2af91127c089f3f1a67c | Reused deterministic v2 browser packet (15-min lifetime, exact employer, revision, PDF SHA + size and approved contact) and recomputed the full canonical packet to verify copied metadata | No second CV renderer, upload store or applicant profile duplicator |
| SmartPloy reviewed intent and sticky employer ledger | employer_review_intent_storage.py SP15c blob d187f8095b1e6df1f3d39e9c8c416679655ccfb8; employer_submit_claim_storage.py SP15c blob feeb3cee32927abd77883c8129bec1bf9a4fdf31 | Extended existing 10-minute per-owner/job intent with a read-only recheck. Calls SAME SP15a transactional owner/workspace/job/doc/receipt/CRM preflight; checks sticky prior claim and active consent. | No competing database ledger or second owner lock design |
| ObumAI Agent B and Agent D | obumellm/application/final_submit_preflight.py blob b5c5e99e008162f43efa09d05582856bcf05300e; obumellm/platform/control_plane.py blob e6259a75b3bf4aecfb514e3b9747760a5a4b2770 | Reused the evidence-before-authority model, no-action observation, idempotency/lease separation as design constraints only | NO copy of incompatible in-memory control plane or premature employer-submit lease |
| Official Chrome MV3 APIs | https://developer.chrome.com/docs/extensions/reference/api/scripting and https://developer.chrome.com/docs/extensions/develop/concepts/messaging | Confirmed activeTab-only user invoked executeScript is available and no external-connectable page or background worker is necessary for this read-only first-party verification | No unnecessary host_permissions/external messaging/broad permissions |

The previously inspected ObumBrowse, ObumForge, ObumConnect, ObumAICore
default branches contained no reusable shipping paired extension handoff. Not
counted as source systems or copied. External community/video inventories in
master project plan are unchanged; **zero third-party code imported**.
No license evasion, network scraping, CAPTCHA bypass or new runtime dependencies.

## Step 2. Genuinely NEW minimum missing application code

- NEW browser-companion/page-review.mjs: self-contained, tightly scoped
  ISOLATED-world SmartPloy-origin-only active-tab site script. It uses the user's preexisting
  HttpOnly OIDC session only on the same first-party origin and sends a
  bounded, approved-application *hash projection* to the same-origin backend.
  Returns only non-bearer review result with explicit no-submit flags.
- NEW browser-companion/review-bridge.mjs: uses original strict packet parser,
  computes a UTF-8-length-prefixed approved fields fingerprint, an exact
  employer URL hash and a SHA-only session key. Stores only the key and expiry
  in existing MV3 storage.session (up to five minutes). Requires it again
  before every employer field fill, PDF attachment, and reviewed answer fill.
- NEW backend verification route /api/v1/application-workspaces/{id}/verify-reviewed-packet:
  expands the original signed-in application API with explicit owner/account
  precondition and reuses the canonical packet renderer/claim repository.
  This endpoint verifies prior review, exact revision/PDF hash/PDF byte length,
  full approved contact/letter hash, employer URL hash, current posting,
  no receipt, no quarantine and no sticky previous employer attempt.
- Small NEW approved_fields_sha256 helper in existing browser_handoff.py:
  9 existing approved field names, UTF-8 byte-length prefixes, deterministic
  SHA in Python/JS to avoid ambiguous concatenation/canonical JSON mismatch.
- NEW Node/browser/Python adversarial tests exercise second browser's
  missing attestation, forged fields/job/CV/PDF, expired local verification,
  missing/revoked server review, account switch and no employer submit.

## Step 3. Measured core progress, not CI decoration

Before this patch: popup accepted any syntactically valid copied packet and
could fill/attach on a Lever page without checking a persisted signed-in
SmartPloy review (SP15c review was disconnected from extension).

After this patch: assisted external form edits require a signed-in,
tenant-bound exact review verified on SmartPloy's FIRST-PARTY tab. A copied
packet alone cannot trigger the companion's existing assisted fill/attach.
The bridge is strictly NON-ACTUATING for a final application submission.

**Limits and explicit blockers**: this is a point-in-time verification whose
local five-minute hashed ticket cannot be instantly revoked across browser
devices, and which must NEVER authorize final submit. True final employer
submission requires (1) documented employer automation rights, (2) second
explicit owner final approval tied to current form and reviewed PDF, (3) a
short-lived one-shot *server-held* grant that is atomically consumed by this
same companion before final click, (4) two-device signed-in race and failure
tests, (5) independently verified employer receipt. ObumDelivery native
SmartPloy Woodpecker run and owner-signed OVH staging/rollback also remain
unverified. No live customer application is made in this draft.

CI result must be appended after exact HEAD actually runs. All review-only
GitHub checks are source QA, not production deployment authorization.

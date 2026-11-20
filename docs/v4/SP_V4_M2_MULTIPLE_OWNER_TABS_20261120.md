# SmartPloy V4 — same owner, multiple SmartPloy tabs, one exact application

**Authority:** `AGENTS.md` as checked 20 November 2026, V4 §§1.1, 4–7, 9–12, 14 and `SP-V4-ONE-PROFILE-APPLY-001` steps 1–7. **Baseline:** https://github.com/galapoto/smartploy/tree/55b0878164533005c4771728af36e98e5f8ea74e. **User outcome:** an authorized candidate with two SmartPloy tabs can continue one exact employer application's reviewed CV/letter attachment and verified questions without closing unrelated tabs or weakening owner/consent checks.

## Source-diagnosed bottleneck

The actual MV3 companion `browser-companion/popup.mjs` rejects `owned.length !== 1` in `requireFreshOwnerReview`, `ownedTabs.length !== 1` in `autoAttachSavedDocuments`, and `items.length !== 1` in `signedInAppTab`. This makes the ordinary, safe act of having two first-party SmartPloy tabs block all reviewed transfers and final readiness, even when the signed-in owner and exact workspace can be established. This is a **source-level observation**, not a fabricated real-employer trace.

## Minimal adaptation

- Preserve the exact trusted first-party origin list, OIDC session, signed-in account binding, packet revision, exact employer URL, CV and letter SHA-256, saved-answer digest, one-use consent and no-retry gates.
- For **current reviewed mutation**, inspect candidate first-party tabs and accept only an owner tab whose *existing* `verifyReviewOnSmartPloy` returns the current reviewed profile and letter proof; do not transfer raw answers or files to another tab. Return the matching tab ID for the existing document reader.
- For read-only final readiness and after-claim receipt saving, select a first-party tab only if an existing account-scoped GET of the exact workspace confirms matching `workspace_id`, `revision` and `application_url`. This deliberately avoids depending on pending pre-submit review after an irreversible attempt.
- Never choose a tab merely because it is first or has the right hostname; failed, signed-out, wrong-account, stale-revision and mismatched-job tabs are rejected. If none proves ownership, stop without writing to any employer or consuming final permission.
- Do not change provider allowlists, browser permissions, final-click grants, document bytes, target selection, or adapter code.

## Reuse and provenance

- **COPIED: none.** All production code is adapted in place from first-party https://github.com/galapoto/smartploy at `55b0878164533005c4771728af36e98e5f8ea74e`, specifically `browser-companion/popup.mjs::requireFreshOwnerReview,signedInAppTab,autoAttachSavedDocuments,inspectOwnFinalActionReadiness`, `page-review.mjs::verifyReviewOnSmartPloy`, `page-document-fetch.mjs::readOwnReviewedPdf`, and existing owner-scoped `smartploy/api.py::get_application_workspace`.
- **ADAPTED / INTEGRATED:** multi-tab selection against trusted owner/workspace proof; reuse unchanged exact packet and document verification; no external code is imported, no new dependency or host permission.
- **NEW:** targeted pure browser VM regression tests and source-adaptation proof. **SANITIZED:** exact origin, ID, revision and employer-job equality; only a boolean returns from the owner workspace probe, not personal details.
- **REA_NOT_APPLICABLE:** this exact failure and all relevant source are readable, first-party and deterministic; opaque-app reconstruction would not provide better evidence. **Savings and runtime:** NOT_MEASURED.

## Qualification, release and acceptance

TDD: regression first (expected **RED** on old `items.length !== 1`), then minimal code and exact-source **GREEN**. Run Node browser companion, Chromium real popup, web type/build, Python tests, GitHub Actions and native Woodpecker. All status claims remain **NOT_VERIFIED** until returned from executed tools. Then merge qualified source, deploy immutable main SHA under existing OIDC/backup/release gates and verify public web/API and real signed-in employer handoff. A synthetic test or a passing merge is **not** proof of employer acceptance. Independent code peer review remains optional under owner supersession.

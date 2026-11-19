# SmartPloy Chrome companion v0.6.2 package pin — 19 November 2026

**Authority:** V4 production-first `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` §§1, 4–7, 12 and one-profile acceptance `docs/v4/SP_V4_NEXT_RUN_ONE_PROFILE_COMPLETE_APPLICATION_EXECUTION_20261113.md`. This is a delivery label correction for the already merged review-mode capability in PR #345 / main `370122d32be0f5f82b71bdd95843fbb568784f04`, not a second AutoApply engine.

## Why it matters

The previous hosted package used Chrome manifest version `0.6.1` even though the reviewed Chrome companion source now includes the exact Lever CV-PDF+letter-text fallback. A user comparing two ZIPs needs a monotonic release version to distinguish them. **Unpacked Chrome extensions do not automatically update** and a version label alone does not grant a managed update channel. No claim is made that the Chrome Web Store or enterprise extension distribution is configured.

## Copied → sanitized → adopted

- **Original project and source:** https://github.com/galapoto/smartploy commit `370122d32be0f5f82b71bdd95843fbb568784f04`, `browser-companion/manifest.json`, `tests/test_companion_package.py`, `web/scripts/package_companion.py`, `browser-companion/page-attachment.mjs::verifyReviewedCoverLetterText`, `browser-companion/popup.mjs::autoAttachSavedDocuments`.
- **COPIED unchanged:** none.
- **REUSED unchanged:** the original reproducible stdlib-only package builder `web/scripts/package_companion.py`, its exact allowlist, SHA256SUMS validation, existing CDN no-store and public `/smartploy-apply-companion.zip` path.
- **ADAPTED:** `browser-companion/manifest.json` patch version `0.6.1 → 0.6.2`; concise, truthful description now mentions approved letter PDF or exact text on Lever.
- **SANITIZED:** No new permissions, background scripts, external JS, update URL, employer host permissions, ATS submission rights or credentials.
- **NEW:** assertions in the existing package regression test that v0.6.2 ZIP actually contains the reviewed standalone text verifier, popup integration and restrictive final-readiness branch; new scoped governance receipt and this provenance note.
- **REA:** not needed, exact authorized complete first-party source already present; other donor **none**.

## Acceptance and remaining limits

Native CI and GitHub Actions must pass on the exact PR head, followed by merge and fresh main qualification. The trusted OVH deploy has its own exact immutable SHA, backup-first, health and public artifact parity checks. The successful public ZIP release means the **new source is downloadable**, not that any previously installed unpacked Chrome companion automatically updates or any real employer form was submitted. One real owner-authorized employer form-to-review test remains separately needed. No additional software dependencies or background automation are introduced.

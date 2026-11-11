# SP-V4-M4-SELECT-001 — reviewed native employer dropdowns

**Date:** 11 November 2026 (Finland). **Authority:** approved V4 Production-First Contract §§1.1, 4–7; [R1 sprint ledger](SP_V4_RAPID_RELEASE_SPRINT_20261111.md), M4.  
**Source baseline:** https://github.com/galapoto/smartploy @ `afba0046803047587b2c33848bdd0eea5dbad4c4`.  
**Outcome:** Applicant sees actual required ordinary employer-select options from the inspected page, selects **one exact value** after reviewing the answer, and the existing Chrome companion fills it once and checks the persisted DOM; no guessed yes/no, consent, salary, work eligibility, upload, background send or final submit.

## Research, donor/source provenance

- **Original first-party working donor (COPIED, SANITIZED, ADAPTED, PORTED):** https://github.com/galapoto/smartploy/pull/311 at pinned `5ef750d3bb5b9d333674ada30146c33db63aa682`. Exact donor paths: `browser-companion/adapters/approved-option.mjs::uniqueApprovedOption`, `questions.mjs::planReviewedQuestions,validateReviewedAnswers`, `page-questions.mjs::fillReviewedAnswers`, `popup.mjs::inspectForm,onReviewQuestions`, `tests/questions.test.mjs`, `tests/approved-option.test.mjs`, `web/browser-tests/lever-questions.e2e.ts`, `web/scripts/package_companion.py`.
- **External algorithm design donor:** https://github.com/vesaias/JobNavigator @ `623822529389d6919d86be07271e0ea94e20b514`, `extension/lib/autofill_match.js::matchOption`, MIT License Copyright 2026 JobNavigator Contributors. The original uses fuzzy/substring synonym matching and automatic boolean option inference, **not permitted here**. The first-party PR #311 had previously replaced it with exact option-value matching and unique-enabled-choice checks. Full MIT notice retained in `docs/v4/third_party/JobNavigator_LICENSE.txt` and **distributed inside the extension ZIP** at `browser-companion/THIRD_PARTY_LICENSES.txt`.
- **Same-repo already-deployed runtime reused and preserved:** `browser-companion/popup.mjs::onStartAutoApply,fillPlanned,onFill,onAttach` and `review-bridge.mjs` at `afba00468030`: authenticated reviewed packet, reactive all-prior-field 150ms fill checking, separately approved CV attachment, explicit final submit claim. Never replace these functions with the older donor popup.mjs.
- **COPIED unchanged from first-party:** `browser-companion/adapters/approved-option.mjs`, `browser-companion/tests/approved-option.test.mjs`, and the reviewed `browser-companion/questions.mjs`, `tests/questions.test.mjs` source from PR #311 before integration; full MIT LICENSE file from donor. Some files have since been further adapted; current content is authoritative.
- **SANITIZED:** no external network, model or fuzzy matching; no new host permissions, no source wildcard, no automatic yes/no guess, no consent/legal/sensitive selections, no automatic final submit, no bulk merge of older PR.
- **PORTED/ADAPTED:** `page-questions.mjs` PR #311 async current DOM select-specific native setter and 150ms settle is further strengthened with **reinspection of all previously approved fields**, borrowing the current deployed `popup.mjs::fillPlanned` principle so a later choice clearing earlier text fails closed. `popup.mjs` was adapted surgically on **current main source**, retaining the current Start AutoApply, owner/packet, upload and receipt handlers. `web/browser-tests/lever-questions.e2e.ts` copied from first-party PR #311 with native dropdown positive/negative/React reset tests plus an additional previous-answer reset test. Ashby/Greenhouse fixtures switched to the actual async function without replacing their current extension tests.
- **INTEGRATED:** current deterministic ZIP packaging and GitHub CI allowlist permit **only** `adapters/approved-option.mjs` nested module, plus MIT attribution file; manifest v0.5.5 to distinguish downloaded bundle; `popup.css` dark-theme keyboard-select/focus styling added. All existing extension permissions stay `activeTab,scripting,storage`; no new package manager dependencies.
- **NEW:** the all-prior-field reinspection function and Chromium delayed-clear regression, first-party package version/ZIP/legal tests and this acceptance receipt.
- **REA decision:** REA_NOT_APPLICABLE to readable authorized, pinned first-party and MIT donor source; no executable behavior reconstruction is needed. Claimed development time savings: NOT_MEASURED.

## Strict acceptance and release boundary

1. **Native test:** `browser-companion/tests/approved-option.test.mjs` unique exact enabled value/no guessed options; `browser-companion/tests/questions.test.mjs` questions include supported ordinary select but exclude protected, duplicate, disabled, broad/sensitive options.
2. **Actual Chromium fixture:** `web/browser-tests/lever-questions.e2e.ts`: real synthetic hosted ATS DOM and native select option; intentional later React clearing should refuse the write; previously approved text that gets cleared by a subsequent select must stop and report only currently persisted answers; no final send; salary/consent untouched.
3. **Existing cross-provider QA:** `web/browser-tests/ashby-assisted-fill.e2e.ts`, `greenhouse-reviewed-assist.e2e.ts` run real async question executor, correct URL, never auto-submit; no outside employer network traffic.
4. **Static package:** `web/scripts/package_companion.py`, CI allowlist and `tests/test_companion_package.py` verify v0.5.5; checksum and MIT notices physically inside hosted bundle. Old unpacked extensions require user update; Chrome Web Store auto-update is not yet qualified.
5. **Review and delivery:** exact-head independent code review, GitHub Actions and Woodpecker; merge as one qualified feature only after M1 independent merge, main push success, deploy exact main SHA using first-party OIDC backup/migration guard, compare public `release.json` and `/healthz`, SHA of public ZIP and real signed-in supported employer form-to-review. No employer final submission for acceptance tests.

**At authorship:** SOURCE_READY only; CI_QUALIFIED, MERGED_MAIN, DEPLOYED, USER_VERIFIED and real employer E2E all **NOT VERIFIED**. **No candidate data, credentials, or actual employer application transferred by this development run.**

## Independent review corrections

Preliminary exact head `891acd966710aab817ac05fda0819a70308ed826` passed five GitHub Actions tests but independent Codex review found:
- **P1:** a sensitive option (e.g. “Yes, I have a disability”) was silently omitted from a generic native dropdown while remaining “No/Decline” choices were exposed as ordinary. Correction: reject the **entire** select if its heading or ANY option label/value indicates self-identification, protected traits or legal topics; never merely filter the sensitive option and offer the others. Unit tests include generic “Choose an option” with visa sponsorship, and voluntary self-identification.
- **P2:** disabled `<optgroup>` options remained incorrectly available because `option.disabled` can be false when the parent group is disabled. Correction: original native inspection, eligibility enforcement and all post-fill confirmations inspect inherited `closest("optgroup[disabled]")` state. Actual synthetic Chromium Lever test ensures no select, no submit.

These fixes supersede preliminary green CI, and require fresh exact-head GitHub Actions, Woodpecker and non-author review. No release until then.

## R2 — Post-write option-drift safety closure (11 Nov 2026 EET)

**Observed source risk:** The current DOM was already checked against the entire applicant-reviewed select-option set *before* the write, but a reactive employer form could change an **unselected option** during the existing 150 ms wait and the settled-value check could still report success. The protection must apply both before writing and when reporting completion.

**ADAPTED / INTEGRATED (existing first-party code, no new engine):** `browser-companion/page-questions.mjs::fillReviewedAnswers` reuses `sameReviewedOptions` during settled verification and in the all-previous-answer persistence check. An asynchronously modified option, including a newly sensitive one, fails closed without replaying the write or initiating employer submission.

**NEW tests:** `web/browser-tests/lever-questions.e2e.ts` includes a real synthetic Chromium scenario changing an unselected option to a sensitive disclosure 25 ms after `change`, and a disabled-ancestor `fieldset` scenario. Both must remain blocked, with no final submit.

**Provenance:** `https://github.com/galapoto/smartploy` at initial candidate `daa82f023414e7ea4f0148db55933b088d273580`, same function and same Chromium fixture. Copied unchanged: **none** in this R2 hardening. Sanitized: not required (authorized first-party source). Adapted: source guards. Integrated: existing v0.5.5 companion. New: two browser regressions. REA_NOT_APPLICABLE to a focused correction of accessible owned source; time savings not measured.

**Evidence at coding time:** branch commits `5b3582b2e57e4ce61776f778be2f7a33f47e052e` and `bb804ba3a7666bdc6d26e37c111af55df671f817`; exact new-head CI, independent review, merge, main CI, OVH deployment, online evidence, and real signed-in employer acceptance remain **NOT VERIFIED** until independently observed.

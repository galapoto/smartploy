# SP V4 — exact first-party source adoption: one-click Chrome AutoApply

**Date:** 2026-11-09. **Authority:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` §§4–7 and `AGENTS.md` (REA-FIRST-001, LEAN-REA-FLOW-001, FEATURE-FIRST-001). **Target:** one user-reviewed job and candidate document packet → exact approved employer ATS tab → one **Start AutoApply** action → inspect → fill ordinary contact/letter fields → review remaining employer questions, with no final employer submission by this feature.

## Donor provenance and permissions
- **Original project / GitHub URL:** `https://github.com/galapoto/smartploy`.
- **Exact donor commit:** `21bfc699e6200482084117de01362d52d54f538e`, previously PR #315, original parent `6e536ed6825f92841c1cb2b5d5b7db2bebcf14b2`.
- **Original license/notice:** the checked first-party SmartPloy tree has no separately declared LICENSE/COPYING/NOTICE file. Do not assert MIT/Apache or an unknown third-party license. The project owner expressly authorized reuse and adaptation of their own SmartPloy and ObumAI code. This is same-owner first-party integration, not a grant to redistribute unlicensed external proprietary software.
- **REA:** `REA_NOT_APPLICABLE`; complete authorized first-party source and source commits are available directly. REA reconstruction or opaque executable analysis is unnecessary.

## COPIED, SANITIZED, ADAPTED, INTEGRATED, NEW
| Original from donor commit | Destination in this PR | Status, exact changes, reason |
| --- | --- | --- |
| `browser-companion/popup.mjs`: `onStartAutoApply`, `onInspect`, `onFill`, `onReviewQuestions` | same path | **PORTED, ADAPTED, INTEGRATED** original one-action orchestration onto merged main without replacing existing submit/receipt safety. Fixed no-contact/question-only flows and safe zero-write autocomplete continuation. No ambient employer final click. |
| `browser-companion/popup.html`: primary action and progressive details | same path | **ADAPTED** from #315 patch; retained current first-party logo header and existing controls. |
| `browser-companion/popup.css`: one-action style | same path | **SANITIZED, ADAPTED** colors from former blue/white style to current approved dark black, turquoise trace and white text with shadows; retained mobile/reduced-motion styles. |
| `browser-companion/manifest.json`: one-action description | same path | **SANITIZED** original 0.5.2 metadata into current **0.5.3** and kept all bundled SmartPloy branded 16/32/48/128 icons and minimal original browser permissions. No new host permissions, background worker or external script. |
| `web/src/ApplicationStudio.tsx`, `web/src/ApplicationStudio.test.tsx` | same paths | **PORTED, INTEGRATED** original source/UI and tests for Start AutoApply packet from the exact owner case; current main OIDC and CV flow kept. |
| `browser-companion/tests/start-autoapply.test.mjs` | same path | **COPIED unchanged initially**, then extended to cover zero-contact and upload-only cases plus real `onFill()` zero-write outcome; synthetic/test-only, no employer contacted. |
| Existing `tests/test_companion_package.py` | same path | **ADAPTED** first-party package fixture to assert one-action function and HTML and preserve 0.5.3 icon/manifest checksum checks. |

**Other copied unchanged production code: none.** The target's `.github/workflows/ci.yml` extension ZIP source packaging and browser/docker tests already exist on current `main`; they were reused in place rather than copied from the old PR. Existing `tests/test_browser_pdf_attachment_contract.py` already checks version >=0.5.1 with matching branded icons, so no duplication. **New:** targeted corrections for successful zero-write inputs and dark theme CSS. Third-party code copied: none.

## Exact acceptance and boundaries

Automated: JS syntax, native Node browser-companion tests (one Start, expired/changed packet refusal, zero-contact and actual zero-write fill, no final send), Vitest selected owner’s case, Playwright Chromium synthetic ATS, Python source/package checks, built Docker web and ZIP SHA checks, Woodpecker. Follow `PR #329` exact-head CI and independent reviewer.

This helper is a **user-installed, visible Chrome extension**, not a hosted remote browser service. It uses the candidate’s actual page after user consent; does not read passwords, bypass CAPTCHA/MFA, submit silently, or send a private CV to unrelated artifact storage. Employer button clicks and permission/receipt handling remain separately controlled by existing first-party policy. **No live applicant/employer acceptance or real submission** has been verified by this source change. GitHub `main` and OVH `release.json` must be compared after merge, exact-SHA deploy and signed-in test.

Source readiness, CI qualification, production deployment and user verification are separate. **Time savings and reuse percentages:** NOT_MEASURED.

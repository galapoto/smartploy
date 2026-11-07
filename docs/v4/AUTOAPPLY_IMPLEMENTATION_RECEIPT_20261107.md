# SmartPloy V4 - AutoApply implementation and acceptance ledger

**Recorded:** 2026-11-07 | **Workstream:** P0 AutoApply | **PR:** [#308](https://github.com/galapoto/smartploy/pull/308) (draft, base integration PR #299) | **Observed source head before receipt:** `c7684cb2fe96372b8a3c9a35e451d4d1cea95add`.

## Implementation delivered to GitHub source

| Capability | Adopted source | Implemented seam | Source state |
| --- | --- | --- | --- |
| Native employer dropdown questions | [JobNavigator MIT](https://github.com/vesaias/JobNavigator/blob/623822529389d6919d86be07271e0ea94e20b514/extension/lib/autofill_match.js), sanitized to exact match | `browser-companion/adapters/approved-option.mjs`, `questions.mjs`, `popup.mjs`, `page-questions.mjs` | SOURCE_READY |
| Correct job binding on generic employers | First-party `pathIsSameJob` reused and tightened | `logic.mjs`, `upload.mjs`, `popup.mjs`, `page-questions.mjs`, `page-attachment.mjs`, `browser-playwright/assistant.py` | SOURCE_READY |
| Delayed async form verification | First-party ObumAI-derived Playwright `_fill_one` settle-and-verify | MV3 `page-questions.mjs`; no retry after unknown employer-side write | SOURCE_READY |
| Playwright-native dropdown UI | Current `LocalPlaywrightAssist`, local bridge and question memory, not a new interface framework | `web/src/localPlaywrightBridge.ts`, `LocalPlaywrightAssist.tsx`, `local-playwright.css` | SOURCE_READY |
| Browser package parity | Existing reproducible deterministic first-party packagers | `web/scripts/package_companion.py`, `web/scripts/package_playwright_assistant.py` | SOURCE_READY |
| Chromium acceptance corpus | Existing Lever/Ashby/Greenhouse/generic synthetic tests | `web/browser-tests/*.e2e.ts`, including same-host different-job and native select reset | TESTS_COMMITTED_NOT_EXECUTED |

## Focused execution evidence - NOT native CI

A source-level V8 harness run over the exact fetched GitHub source reported **11/11** pure question/option tests, **14/14** same-job-path positive/negative assertions, **2/2** injected wrong-job action tests, **3/3** synthetic delayed persistence tests, **2/2** typed-web-bridge validator tests, and **11/11** build-time Chromium injection syntax/contract assertions. These are localized evaluations of GitHub source in an isolated JS runtime with simulated browser objects; they are **not** Node/Vitest/pytest/real Chromium tests. Source-level tests cannot prove actual employer compatibility.

New browser/Vitest test cases have been committed but have **not** been run against Chromium, a signed-in SmartPloy account, a production build, or a real employer site. Their status remains NOT_RUN until native CI and a real application journey produce artifacts.

## Qualification required before promotion

```sh
node --test browser-companion/tests/*.test.mjs
python3 -m pytest -q tests/test_companion_package.py tests/test_browser_question_contract.py tests/test_playwright_assistant.py tests/test_playwright_assistant_chromium.py tests/test_playwright_local_bridge.py
python3 web/scripts/package_companion.py --output /tmp/smartploy-apply-companion-v4.zip
python3 web/scripts/package_playwright_assistant.py --output /tmp/smartploy-playwright-v4.zip
cd web
npm ci --no-audit --no-fund
npm run test
npm run build
npm run test:e2e
```

After isolated native qualification, require **independent signed-in real-employer journeys** for extension and Playwright, with reviewed applicant facts, real observed option/field value persistence, exact approved document attachment, unknown-state recovery, and verified ready-for-review. Final employer submission remains separately authorized and cannot be inferred from field filling or a click. Record actual release SHA, CI, artifact digest, running API/UI identities, redacted case evidence, roll-back SHA and final user verification using `docs/v4/RELEASE_RECEIPT_TEMPLATE.json`.

## Blockers and release truth

- **CI:** no native Woodpecker/Chromium/Vitest/pytest evidence attached to this source branch yet.
- **Integration:** PR #308 depends on open integration PR #299 and does not independently exist on `main`. Do **not** merge unrelated draft code to ship this feature.
- **Production:** no authorized deployment or signed-in public UI proof. Real employer acceptance is NOT_RUN, not PASS.
- **Risk:** generic shared `/apply?job=...` routes now require the **exact** applicant-reviewed form URL as the saved application target; this is an intentional wrong-job protection. Do not loosen it by same-origin matching. Expand legitimate shared-site paths only through independently reviewed job identity and matched cases.
- **REA:** direct authorized source-level code inspection was used. Record REA_NOT_APPLICABLE for these small already accessible donor modules; no REA runtime or reverse-engineering validation is claimed.

**Next narrow candidate release:** Native CI/test qualification for this typed field vertical slice; after green tests and explicit release approval, expose the connected Playwright/extension path from the existing CV-first application UI, not a new mock dashboard. Work on other V4 lanes continues in their own independently qualified PRs.

# SmartPloy V4 / SP-AUTO-SETTLE-001 — exact reactive-form fill verification

**Authority:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` §§1.1, 4–7, 11–12; `AGENTS.md` REA-FIRST-001, FEATURE-FIRST-001, SMARTPLOY-V4-LOCK-001.  
**User outcome:** On the real employer form, *Start AutoApply* must not report a field successfully filled if a reactive/React employer form clears or replaces it after receiving input/change events. Stop at the first uncertain field; do not repeat a write, submit, attach or infer missing answers.

## Provenance / copy, sanitize, adopt

| Status | Original repo/source | Change | Destination | Verification |
| --- | --- | --- | --- | --- |
| **REUSED IN PLACE / ADAPTED** | https://github.com/galapoto/smartploy @ `1623f2e608cbaa5de454331ec93bb5205252da73`, `browser-companion/popup.mjs::fillPlanned` | Keep existing exact-job URL, label, DOM index, metadata and permission checks; convert user-triggered Chrome script to async, wait 150 ms after each write, re-observe URL/DOM/value and count only persistent fills | `browser-companion/popup.mjs` | `browser-companion/tests/settled-fill.test.mjs` plus existing Start/logic tests |
| **BEHAVIOR PORTED / ADAPTED** | https://github.com/galapoto/smartploy/pull/317 @ `6c49b6b8116c4a92ecde1cb9c18e9d86ff11894e`, `browser-playwright/assistant.py::_fill_one` | Adopt 150-ms settle, exact value reinspection and no blind retry *concept*. **No Python source copied into the MV3 script**, which needs its own active-tab DOM implementation | `browser-companion/popup.mjs::fillPlanned` | Delayed reset, URL change, DOM replacement, sensitive field switch and no retry |
| **REUSED IN PLACE** | `web/scripts/package_companion.py`, deterministic allowlist and first-party hosted ZIP | Keep existing packaging, checksum, icon, permission limits and strict no-background/no-external scripts | `browser-companion/manifest.json` v0.5.4; `tests/test_companion_package.py` | Reproducible ZIP, no extra host permission, exact version |
| **NEW** | No suitable first-party VM regression for the extension's awaited settled form | Create a small offline native Node VM fixture exercising the *real production source* (not a second filler) | `browser-companion/tests/settled-fill.test.mjs` | Actual serialized function on synthetic inputs |

**COPIED unchanged:** none. The relevant donor behavior was already present in SmartPloy PR #317 (not merged), and the existing production Chrome function was retained in place. **SANITIZED:** no extra browser privileges, no broad selectors, no persistent applicant data, no arbitrary JavaScript from a model, no automatic retry or final send. **INTEGRATED:** `onFill` already passes `fillPlanned` to `chrome.scripting.executeScript`, which supports a Promise result; `onStartAutoApply` only proceeds to question review after a no-blocker result. **REA_NOT_APPLICABLE:** readable authorized first-party source; reconstruction would add risk. Savings/latency not measured, except deterministic +150 ms per written field; runtime dependencies added: none.

## Shared browser direction (no premature coupling)

ObumBrowser's independent browser service is specified under https://github.com/obumai/ObumBrowser at `820f3dcb2dde3095d4328b861e33226f1d3b4cdd` (OBUMBROWSER-FINAL-002 v2). Its native extraction PR #4 is a source-ready draft, not a tested/deployed browser. SmartPloy keeps today's MV3 extension and independently reviewed packet/ATS policy; **future hosted execution** must use ObumBrowser's versioned API and never start another hosted Playwright worker within SmartPloy. This extension improvement is independently usable without the hosted service.

## Acceptance / release truth

- Synthetic VM tests: stable values persist, delayed React clear fails closed, a later field clearing an earlier verified value blocks full success, redirect/DOM/metadata mutation stops before next field, no blind retry, no automatic send, zero-contact form remains valid. Real Chromium Lever/Ashby/Greenhouse harnesses run the actual Promise-returning extension executor.
- Full SmartPloy GitHub Actions + Woodpecker exact SHA and qualified independent non-author review required before merge. Source review and CI success are not real employer completion.
- After merge main CI, deploy exact approved SHA to existing OIDC OVH stack, verify release/health and reproducible extension ZIP against source; candidate still needs to reinstall/update unpacked extension (not Chrome Web Store auto-update).
- Signed-in real employer fill to `ready_for_review` and employer-issued receipt remain **NOT VERIFIED** unless separately observed. Never send a real application for a test.

Status at authoring: **SOURCE_READY**, CI/independent review/production pending, actual employer verification pending.

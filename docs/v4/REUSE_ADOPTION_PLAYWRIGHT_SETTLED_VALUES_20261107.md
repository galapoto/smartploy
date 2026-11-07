# SmartPloy V4 — settled Playwright value verification (2026-11-07)

**Approved authority:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` §§1.1, 4–7; `SMARTPLOY-V4-LOCK-001`; `LEAN-REA-FLOW-001`. Starting integration parent `galapoto/smartploy@33cd19c5c2fcbd1b58f22d4f3605167573567763` (PR #316, which depends on #315 and #314). This is a focused child, not a wholesale merge of PR #299.

## User-visible correction

**Before:** The visible Playwright browser counted a field as successful immediately after `locator.fill`, even when a reactive employer form cleared it milliseconds later. The website could then show a misleading completion indicator.

**After:** After one explicitly authorized fill, the helper waits 150 ms, rechecks exact field identity/visibility, unchanged employer URL and the live input value. If a value fails to persist, the helper counts **zero verified** for that field, stops before the next field, never retries, and the paired UI displays a warning instead of green success. Final employer submission, credentials, sensitive attestations and document uploads remain untouched.

## COPIED → SANITIZED → ADOPTED (before new work)

| Classification | Immutable source | Destination and exact adaptation |
| --- | --- | --- |
| **COPIED / PORTED** | First-party `galapoto/smartploy@5e97e593177464e21f67b1dae3a8ea38076fa832:browser-playwright/assistant.py` function `_fill_one` (SP144 settled-value path); original proven ObumAI Playwright donor `obumai/obumellm@d682da2582ebfa3f013cf37dc542384fe605f303:obumellm/browser/fill.py` | `browser-playwright/assistant.py::_fill_one`, retained 150 ms settle, exact source selectors, field reinspection and value equality. **SANITIZED** with an extra post-fill original-URL guard. No new selectors, hidden browser or retries. |
| **COPIED / ADAPTED** | `galapoto/smartploy@5e97e593177464e21f67b1dae3a8ea38076fa832:tests/test_playwright_assistant_chromium.py::test_sp144_real_chromium_reactive_clear_is_not_counted_as_filled` | `tests/test_playwright_assistant_chromium.py`, changed test URL to an already-supported Lever form so it can run in the original SP111 executor without expanding site permissions. Synthetic intercepted employer HTML only. |
| **ADAPTED / INTEGRATED** | Existing first-party `galapoto/smartploy@33cd19c5c2fcbd1b58f22d4f3605167573567763:tests/test_playwright_assistant.py` `FakeLocator` and `FakePage` | Added actual value-read/settle simulation and a regression: late clear gives 0 of 2 verified; changed origin is not counted. |
| **REUSED IN PLACE / ADAPTED** | Existing first-party `galapoto/smartploy@33cd19c5c2fcbd1b58f22d4f3605167573567763:web/src/LocalPlaywrightAssist.tsx` and test | Existing `uncertain` warning state reused for partial or stale fills. New negative UI test; no new component, router, state store or dependency. |

**REA decision:** `REA_NOT_APPLICABLE` to existing owner-readable source and first-party exact SP144 branch. No proprietary/external donor code added, no extrapolated reuse percentages or savings (`unknown`). All code provenance above is direct first-party reuse; ObumAI origin is provenance of that existing source, not a new verbatim copy in this run.

## Honest acceptance and release receipt

- **Source:** new reviewed Python+React regression tests; bundled local helper is deterministically regenerated from the modified `assistant.py` by existing packaging.
- **Verify at exact child SHA:** `python -m pytest -q tests/test_playwright_assistant.py tests/test_playwright_assistant_chromium.py tests/test_playwright_local_bridge.py tests/test_companion_package.py`; `cd web && npm test -- --run src/LocalPlaywrightAssist.test.tsx`; full native CI, ZIP checksum and browser checks.
- **Negative acceptance:** delayed employer clearing, employer redirect, changed DOM, denied consent, no retry, no CV upload, no automatic final Submit.
- **No new dependencies, services, API endpoints or UI routes.** Bundle delta `NOT_MEASURED`; runtime waits 150 ms per attempted field (already present in upstream donor). Design scope: same lightweight flow.
- **Status at source authoring:** `SOURCE_READY` only until actual CI / staged / deployed evidence. **USER_VERIFIED: NONE** for this child; real signed-in supported ATS acceptance, independent review, exact deployed build and rollback still required.

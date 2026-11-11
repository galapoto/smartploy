# SP-CR-OBUMBROWSER-001 — hosted AutoApply browser ownership change

**Date:** 11 Nov 2026. **Decision authority:** explicit owner direction to continue SmartPloy V4 with ObumBrowser as independent hosted browser, while preserving and continuing the existing Chrome AutoApply extension. **V4 source:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md`, sections 4–7, 11–12. **ObumBrowser source:** https://github.com/obumai/ObumBrowser at `820f3dcb2dde3095d4328b861e33226f1d3b4cdd`, specification `OBUMBROWSER-FINAL-002 v2.0.0`.

## Change, impact and alternatives

- **Replace only the ownership of the V4 secure *hosted* browser executor.** Instead of SmartPloy creating a separate hosted Chromium/Playwright/noVNC/CDP service, adopt the standalone ObumBrowser versioned session, observation, approved-action, display and takeover API when it has passed its own native security and release tests. ObumBrowser remains independent of SmartPloy and Floently.
- **Preserve working delivery:** The first-party MV3 extension (currently distributed as a public first-party ZIP) and reviewed employer policy stay SmartPloy-owned; local visible Playwright candidates remain separate unmerged/independently reviewed fallback until a safe path is qualified. There is no reason to pause CV preparation, live form filling, document upload or employer-fingerprint testing while the hosted engine is being extracted.
- **Do not embed Floently runtime, cookies or browser worker in SmartPloy.** FlowReader copies and sanitizes its own existing browser implementation to independent ObumBrowser; it is not itself the future hosted endpoint. No shared secrets, Cloudflare identity, databases, worker processes or profile volumes.
- **No new hosted control on today's website:** no disabled or misleading browser button, and no new network authorization or automatic send. Users continue using working Manual/Assisted/AutoApply steps and their own browser.
- **Alternative rejected:** direct local hosted Playwright service owned by SmartPloy would duplicate worker/network hardening and create two competing browser controllers. Copying draft ObumBrowser PR #4 into SmartPloy would be speculative and violate the versioned API/independence boundary.

## First reusable adapter seam, actual code

`smartploy/obumbrowser_handoff.py::reviewed_navigation_intent` is an **internal consumer-only** source slice. It reuses the existing production SmartPloy `browser_handoff.py::review_handoff` and `_assisted_posting_url` from `galapoto/smartploy@1623f2e608cbaa5de454331ec93bb5205252da73`. After the same candidate approval, current-job fingerprint, saved CV/letter and identity checks, it returns only an exact HTTPS employer URL and explicit non-authorizations, rejecting query/fragment credentials.

- **COPIED unchanged:** none (same-repository review helpers called, not copied).
- **REUSED IN PLACE:** exact SmartPloy review, canonical job and packet guards.
- **SANITIZED:** no contact details, CV text, cover letter, PDF bytes, ZITADEL tokens, cookies, applicant ID, browser service key, direct host, file upload or submit scope in the intent.
- **ADAPTED / INTEGRATED:** internal intent uses the actual application workspace and current reviewed job; it is a contract seam, *not yet connected to an ObumBrowser runtime*.
- **NEW:** 56-line fail-closed internal module, 3 regression tests in existing `tests/test_browser_handoff.py`, and binding ownership guidance in `AGENTS.md`.
- **REA_NOT_APPLICABLE:** readable authorized first-party source and a draft remote API already exist; reconstruction would add risk. No external library, service, image, dependency or lockfile change. Performance/savings: NOT_MEASURED.

## Acceptance ledger and next integration increments

| Stage | Candidate-visible outcome / mandatory evidence | Current state |
| --- | --- | --- |
| Existing Chrome extension | Continue exact-job reviewed fill and file/consent safeguards; prove a real employer form to review | WORKING CODE / LIVE EMPLOYER E2E NOT VERIFIED |
| Internal navigation intent | Reviewed exact employer URL only; no private applicant data or accidental submission authority | SOURCE_READY; targeted Python tests added |
| ObumBrowser service | Isolated owner-authenticated browser with actual Chromium pixels/input/leases, egress and user takeover | **NOT VERIFIED / draft PR #4 only** |
| SmartPloy hosted adapter | Typed/versioned client, service identity, case/session binding, current page verification, scoped action and fresh receipt; fail closed, feature flag only after acceptance | NOT STARTED; API version not frozen |
| Signed-in hosted UI | Real noVNC session visible within Apply; Pause/Takeover/Resume/Stop controls operate on that same session | NOT STARTED |
| Consented CV upload & employer flow | Browser upload capability independently security-reviewed; exact CV digest verified and real employer form reaches `ready_for_review` | NOT VERIFIED; ObumBrowser P0 explicitly excludes uploads |

**Next smallest native integration:** after ObumBrowser's external v1 contract is frozen and a native authenticated stage is actually running, add a single server-side SmartPloy client that requests one session with its own OIDC service identity, binds it to an existing owner-scoped application case and lets the user navigate to the reviewed target without sending applicant data. Prove scope rejection, replay rejection, job URL transition, UI observation, stop and cleanup. Only then offer the user a hosted button and progressively add field actions and file upload. No shared session/CDP or duplicate browser worker.

**Status truth:** This change is not a claim that SmartPloy has connected to a running ObumBrowser. Source/diff and tests must qualify in GitHub Actions and Woodpecker; independent review, authorized merge, actual production SHA and signed-in acceptance are separate gates. Do not mark USER_VERIFIED without real browser effects.

# SP128 — Komplyint-structured, compact phone application flow

Date: 2026-11-07. Authority: SmartPloy V4 production-first contract §§4/7/14; REA-FIRST-001, LEAN-REA-FLOW-001 and FEATURE-FIRST-001. Baseline galapoto/smartploy@7ada56504cd5cd779ab95dd8151c6dbb7a956690, open CI-qualified PR #318.

## User-visible vertical slice
At 320/390px, a signed-in user reaches the original CV-first task and the same Manual, Assisted and Automatic handlers without a second full-size dashboard. The Finland/SmartPloy brand is retained. Main mode cards become compact icon/title/single-sentence/action rows; CV-first controls and protected mode lock remain in place. Secondary home panels only (profile, tools, source) are hidden, but those pages remain accessible through the original drawer. The desktop panels are unchanged. Routine release codes are hidden on phones; warnings remain visible. This is real CSS/React work, not a design mock-up.

## Provenance: COPIED → SANITIZED → ADOPTED
- **REUSED IN PLACE / ADAPTED**: `galapoto/smartploy@7ada56504cd5cd779ab95dd8151c6dbb7a956690:web/src/StartChoices.tsx`, its existing CV-first gating/mode buttons. Kept the button event handlers and applicant/employer permission boundaries, shortened descriptions.
- **REUSED IN PLACE / ADAPTED**: `galapoto/smartploy@7ada56504cd5cd779ab95dd8151c6dbb7a956690:web/src/sp127-mobile-shell.css`, `web/src/sp126-premium-dashboard.css` and `web/src/main.tsx`. Added `web/src/sp128-mobile-workflow.css` as a narrow phone-only override, not a replacement layout engine.
- **REUSED IN PLACE / EXTENDED**: same parent `web/src/StartChoices.test.tsx` and `web/browser-tests/onboarding.e2e.ts` tested synthetic fixture; new smoke for 320/390px layout, actual navigation destinations, no overflow and dark/release warning visibility.
- **STRUCTURAL REFERENCE ONLY**: public `https://www.komplyint.fi/` inspected 2026-11-07 for hierarchy; external code/assets copied: **none**. No verified source commit was available for that site. REA_NOT_APPLICABLE to readable first-party source, savings unknown.

## Qualification
Use exact child SHA full native CI, Vitest, production Vite, synthetic real-Chromium 320/390 and navigation tests, plus signed-in live mobile acceptance by authorized release operator. Parent #318 must be qualified/promoted first. No new dependency, service, API endpoint, schema, auth or external action permission. **Source authoring: SOURCE_READY; production user-verified: NONE.** Independent review, native Woodpecker, exact-SHA authorized deployment and rollback remain required.

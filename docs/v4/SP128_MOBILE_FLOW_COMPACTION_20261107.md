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

### Screenshot-directed fix

The real parent synthetic 390px browser screenshot was approximately 3 screens tall before the first job result, with another complete job search and three secondary home panels below the mode chooser. SP128 removes the duplicate `sp126-job-results` from phone **Home only** (alongside the duplicate aside), while the original `Just find jobs` button/Jobs destination/search bar remain functional. Added exact rendered 320/390px screenshot artifacts and explicit browser checks that a mobile user can still reach a concrete synthetic job listing after tapping `Just find jobs`. Do not claim a production website screenshot from synthetic CI.

### Actual Jobs-page overflow caught by chromium

A new mobile Browse acceptance test correctly found document horizontal overflow on the destination Jobs page. Source audit found the existing `web/src/styles.css` `.filter-right` is a non-wrapping flex row containing four select controls with intrinsic widths. A 390px viewport cannot display those side by side. SP128 **ADAPTED** the original controls, not replaced them, by presenting them in an explicitly bounded two-column grid at ≤630px with 14px text and 44px touch targets. An actual Chromium regression verifies all four select controls, their right edges, CSS grid and zero document overflow. Diagnostic overflow-element names are included if it regresses again. No horizontal clipping or removal of job filters.

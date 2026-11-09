# SmartPloy V4 — dark card surface and contrast adoption receipt

**Date:** 9 November 2026  
**Approved authority:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md`, v4.0, sections 1.1 (real readable UI/acceptance), 4 (UI), 6-7 (delivery/verification), plus `AGENTS.md` REA-FIRST-001, FEATURE-FIRST-001 and GALAPOTO-INDEPENDENT-REVIEW-001.  
**User outcome:** The mint/light-blue "DO THIS NEXT" notice shown on the actual dark SmartPloy page must be replaced by a dark, high-contrast, actionable card. All existing pale workflow, document and optional tool panels must use coherent dark/light theme foreground/background pairs. Cards should be beautiful without changing jobs, drafts, login or employer submission.

## Research, provenance, and reuse

1. **Destination project:** https://github.com/galapoto/smartploy at base `409313f6bf8bb84e76fac63a53ac98b03cc70052`. Existing files inspected: `web/src/sp-v4-monochrome.css` (approved black/navy/cyan typography and first-party colors), `web/src/document-coach.css` (the unhandled mint `.flow-primary-next` gradient and gray-blue copy), `web/src/document-comparison.css`, `web/src/career-atlas.css`, `web/src/styles.css`, `web/src/finland-shell.css`, `web/src/sp125-workspace-theme.css`, `web/src/sp126-premium-dashboard.css`, `web/src/sp128-mobile-workflow.css`, and `web/src/ApplicationJourney.tsx`.
2. **Adopted external design source (MIT):** https://github.com/shadcn-ui/ui at exact observed repository commit `8ab27715521cbd4f87ae6886cd989cbb678f6de7`; original module `apps/v4/registry/new-york-v4/ui/card.tsx` (blob SHA `6aebd4cf612dfa24d40ffdf357c6f6363e144d6a`). MIT Copyright 2023 shadcn. The original card uses `rounded-xl border bg-card text-card-foreground shadow-sm` and separately composed header/action/content, but depends on Tailwind and `cn`; SmartPloy does not use those packages.
3. **Comparison:** https://github.com/magicuidesign/magicui (MIT, mostly animated/interaction components) and https://github.com/DavidHDev/react-bits (animated React patterns) were investigated. They were not used: motion/dependency overhead and visual complexity conflict with SmartPloy's minimalist, low-text, fast-apply requirement.
4. **COPIED unchanged:** none. **ADAPTED:** shadcn/ui's compact card border/rounded/elevation/hierarchy principle into original CSS custom properties, retaining SmartPloy's current Lato/Manrope/EB Garamond and branded cyan. **SANITIZED:** no Tailwind/`cn`, no Radix/BaseUI, no runtime JS, no external font/CSS CDN, no glowing animations or motion that delays actions; no new dependencies. **INTEGRATED:** existing SmartPloy CSS classes continue to own actual buttons, job selection, draft editing and browser handoff; the final stylesheet is imported after legacy CSS. **NEW:** `web/src/sp-v4-card-surfaces.css` and source/Chromium regression tests. **REA:** not invoked; exact readable first-party and MIT donor source available, no behavioral recovery needed. **Performance savings:** NOT_MEASURED. Source-size delta at review: approximately 13.9 kB of uncompressed CSS source in one final stylesheet, plus tests and import; zero runtime JavaScript dependencies or lockfile changes. Transferred gzip bytes and performance gains: NOT_MEASURED.

## Exact adoption map

| Original source | Transformation | Destination | Proof |
|---|---|---|---|
| shadcn `card.tsx`: rounded, bordered, elevated card surface | **ADAPTED** to accessible dark/light CSS variables; not an import | `web/src/sp-v4-card-surfaces.css` | `web/src/sp-v4-card-surfaces.test.ts`, Chromium `onboarding.e2e.ts` |
| SmartPloy `document-coach.css`: `.flow-primary-next` mint gradient | **SANITIZED** by last-layer dark or white surface/text override | `web/src/sp-v4-card-surfaces.css` | Chromium computed background/no-gradient, title/help contrast at least 7:1/4.5:1 |
| SmartPloy `document-comparison.css`, `career-atlas.css`, `styles.css` pale panels | **ADAPTED** to one palette on existing selectors; no markup/handler changes | `web/src/sp-v4-card-surfaces.css` | Source coverage tests and existing UI tests |
| SmartPloy `web/src/main.tsx` import order | **INTEGRATED** final CSS layer after approved monochrome tokens | `web/src/main.tsx` | Source test for import order |
| SmartPloy `web/browser-tests/onboarding.e2e.ts` synthetic owner fixture | **ADAPTED** for real Chromium computed contrast and UI click | Same file | Dark desktop and phone, light contrast, real Manual job action |

## Expected UI acceptance and boundaries

- A dark-theme active application panel and its title/help must have a dark, solid surface (no mint) and measured WCAG AA text contrast; light mode must remain white with dark text.
- The original interactive Manual/Assisted/AutoApply method cards, real job selection, signed-in owner controls and review-before-submission paths remain unchanged. No fake card or decorative button should replace a working action.
- A compact black/navy surface and restrained cyan accent only; shadows, hierarchy and hover outlines give visual quality without multicolor backgrounds, spinners, or new dependencies.
- 390 px mobile has no horizontal overflow. Reduced-motion preference disables nonessential card transitions.
- Must run `npm run test`, `npm run build`, `npm run test:e2e`, existing Python CI and Woodpecker, plus independent review on exact head. A passing CI is not proof of live deployment or real employer-form fill.
- Use immutable main-branch SHA with `deploy/personal/scripts/deploy.sh` and OIDC; keep PostgreSQL backup/volume and verified extension intact. After deployment independently verify public `release.json` and `healthz` parity and signed-in desktop/mobile screenshot. Final employer submission remains separately authorized.

**Status at creation:** SOURCE_READY, CI/REVIEW pending, NOT DEPLOYED, USER_VERIFIED=NO. The prior production baseline `409313f6bf8b` was deployed via the authorized operator, with all services healthy. No new employer submission is claimed.

## Independent reviewer findings and corrections

Independent Codex review on preliminary head `55369a56e33807a51b0804a48ef6b10ae7f7d352` identified three P2 problems: disabled cards looked active; risk/error alerts lost semantic severity; selected saved cases looked like unselected hover. The follow-up CSS retains the disabled state with visible muted styling, adds tokenized high-contrast red/amber left borders for error/risk, and uses a stronger cyan selected inset marker than hover. Regressions are checked in `web/src/sp-v4-card-surfaces.test.ts` and the real Chromium mobile test. This records review feedback, not a completed approval of any later exact head.

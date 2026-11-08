# SP127 — real mobile shell, no circular startup blockade

Date: 2026-11-07. Authority: SmartPloy V4 §4, §7 and LEAN-REA-FLOW-001.
Baseline `galapoto/smartploy@37382b54ac9257298e2d32bcd1a2733b87705f60` (main). Scope is **mobile UI reliability and discovery**, not ATS sending or another application engine. Separate from AutoApply PRs #314–#317.

## Concrete source finding and correction

- Existing `web/src/App.tsx` returned a full viewport `.loading-screen` containing a rotating `.spinner` whenever `loading && !dashboard`. That early return hid the actual app layout, sidebar and header until all essential API reads completed; on error it replaced the entire app with a standalone failure screen. The application could appear to be nothing but a circle.
- Now a lightweight `StartupShell` renders immediately with an actual SmartPloy header, accessible workspace destinations, a truthful identity-verification message and an operable **Retry connection** button. No private CV/account details are shown until authenticated server identity and essential reads have completed. It is not falsely called a loaded workspace. There is **no rotating circular loader** in this path.
- Loaded phone UI follows Komplyint's observed public **persistent logo/header → clear mobile navigation → main content** structure, adapted to SmartPloy's existing CSS and feature architecture. Search occupies its own second header row at 320–850px rather than shrinking to unreadable 11px beside controls.
- The original SP129 sidebar focus-trap/scroll lock behavior is ported from first-party code, preserving Escape, modal semantics, resize behavior and return focus.
- Existing React components, CV→mode flow, Job search, Application Studio, signed-in rights, sidebar collapse and light/dark modes are preserved. No new backend, credentials, API or dependency.

## COPIED → SANITIZED → ADOPTED ledger

| Category | Exact source | Destination |
| --- | --- | --- |
| **PORTED, ADAPTED** | `galapoto/smartploy@fcdbe44fc820d40ee41572db4c3ac50ecd27c08b:web/src/App.tsx`, PR #297 SP129 mobile-menu focus+keyboard effect (first-party), based on existing App state | `web/src/App.tsx`: focus trap, Escape, scroll lock, resize close and returned focus; guard at 850px, no new state store or framework. |
| **REUSED IN PLACE, ADAPTED** | `galapoto/smartploy@37382b54ac9257298e2d32bcd1a2733b87705f60:web/src/App.tsx`, existing `NAV`, `BrandMark`, menu/route handler, `useSmartployTheme`, private identity and request-generation checks | `web/src/App.tsx`: non-private StartupShell and real phone brand, no spinner. |
| **REUSED IN PLACE, ADAPTED** | `galapoto/smartploy@37382b54ac9257298e2d32bcd1a2733b87705f60:web/src/styles.css`, `finland-shell.css`, `sp125-workspace-theme.css`, `sp126-premium-dashboard.css` | `web/src/sp127-mobile-shell.css` added as one scoped final mobile layer instead of editing application logic in many older stylesheets. Existing desktop design preserved. |
| **REUSED IN PLACE, EXTENDED** | `galapoto/smartploy@37382b54ac9257298e2d32bcd1a2733b87705f60:web/src/App.test.tsx`, `web/browser-tests/onboarding.e2e.ts` | Tests for slow/failed initial loading, 320px non-blocking shell, 320/390/768 browser layout, drawer focus, Escape, navigation and horizontal overflow. |
| **STRUCTURAL REFERENCE ONLY** | Public `https://www.komplyint.fi/` observed 2026-11-07, `kc-header`, `kc-nav`, `kc-mobile-toggle`, `kc-shell`, `kc-hero` | Conceptual hierarchy adapted; **no Komplyint CSS/HTML/asset source copied**. No source repository or exact commit of that site was accessible; do not claim a literal code port. |

Copied verbatim from external projects: **none**. Original code added: startup-shell glue and scoped responsive styles where no existing first-party function supplied those exact behaviors. `REA_NOT_APPLICABLE` for directly readable first-party source, third-party reverse engineering not performed. Savings unknown.

## Run acceptance

1. `cd web && npm test -- --run src/App.test.tsx`, `npm run build`.
2. `cd web && npx playwright test browser-tests/onboarding.e2e.ts`: responsive 320/390/768, initial loading, drawer keyboard and overflow. Synthetic fixtures only.
3. Exact-HEAD GitHub CI and required native gated checks; independent UI/privacy review.
4. Only with authorized release: inspect exact public signed-in artifact at both mobile + desktop 200/400% zoom, screenshot initial page plus logged-in Jobs→CV→Apply, verify rollback.

At source submission: status **SOURCE_READY**, `USER_VERIFIED: NONE` until exact deployed SHA, real signed-in mobile flow and rollback evidence. No employer submission done.

## Subsequent reliability hardening

The initial signed-in essential session/dashboard/search load now has an 18-second bounded connection deadline. When exceeded, the request generation is invalidated, all private state is cleared, an explicit connection-timeout error and **Try again** action are shown in the header-based shell. The deadline is cancelled when the verified essential workspace is ready; optional AI/profile responses do not extend startup. Background refresh does not take down the live shell. The deadline uses the existing request-generation/privacy control, not new fetching or authentication infrastructure. A Vitest fake-clock regression exercises a hung session.

## Exact Chromium regression from initial candidate

The full SP99 legacy browser suite caught an actual mobile-tap target issue: at 390px, the expanded 318px drawer occluded the centre of the full-screen clickable scrim (`Close navigation`). The scrim now starts immediately to the right of the drawer, always leaving at least a 28px outside tap region, and new 320/390/768 browser tests explicitly tap the uncovered scrim. This keeps the old test's behaviour intact instead of weakening its assertion.

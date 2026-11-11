# SmartPloy SP156 — Komplyint typography and simplified applicant Home
Date: 2026-11-08

## Authority and user result
Follow SmartPloy V4 final specification, with explicit 8 November instruction:
banner ONLY "Apply with confidence" (no other banner text, text-bearing images,
decorative steps); then "Start with your CV." with one instruction, then existing
CV upload/create and manual/assisted/automatic/browse flows. Existing dark
SmartPloy colors, branding and navigation stay. No employer submissions added.

## Copied → sanitized → adopted evidence
- DONOR: https://github.com/komplyint/komplyint-website
- SOURCE: exact commit 76c00948638cd2db699f78c58d6885117f676014
- ORIGINAL MODULES: src/app/layout.tsx (locally bundled font imports),
  src/design/tokens.json (typography, spacing, editorial hierarchy),
  src/app/handbook.css (EB Garamond headings; Lato body, readable sizes).
- PORTED: @fontsource/lato@5.3.0, @fontsource/eb-garamond@5.3.0 and
  @fontsource/manrope@5.3.0 with the original face weights and Latin/Latin-ext
  imports. Exact npm integrity hashes recorded in web/package-lock.json.
- SANITIZED / ADAPTED: did NOT copy the Komplyint green/crimson palette or
  its marketing layout. Scaled typography and spacing for SmartPloy's CV-first
  flow and maintained the approved black, white, cyan and navy palette.
- INTEGRATED: web/src/main.tsx, web/src/sp-v4-monochrome.css,
  web/src/App.tsx, web/package.json, web/package-lock.json.
- NEW: SP156 browser and source-level banner/text/spacing/font-loading tests.
- COPIED proprietary code: none. Fontsource packages are OFL-1.1; see bundled
  package licenses. No network-fetched fonts or new runtime auth permissions.
- No new application logic; App CV→method navigation, retries and employer
  authorization boundaries remain unchanged.

## REA-FIRST-001 outcome and footprint evidence
- **REA decision: REA_NOT_APPLICABLE.** The source is the original, readable
  first-party Komplyint repository, not an inaccessible binary or behavior
  being reverse-engineered. Direct source inspection and audited npm packages
  are safer and more accurate than behavior reconstruction.
- **Target permission:** read-only owner-authorized public first-party
  `komplyint/komplyint-website` repository and its
  `76c00948638cd2db699f78c58d6885117f676014` files.
  No access to proprietary source or production resources was requested.
- **REA tool revision:** NOT_RUN / NOT_APPLICABLE (no REA process invoked).
  **Observed evidence:** original `src/app/layout.tsx`,
  `src/design/tokens.json`, `src/app/handbook.css`; pinned
  Fontsource OFL-1.1 packages and lockfile integrity; synthetic
  Lato/Manrope/EB Garamond font-load and responsive Chromium checks.
- **Unknowns/limits:** browser-rendered measured layout is not proof of
  identical production GPU rasterization; no private Komplyint assets or
  inferred architecture were reproduced.
- **Bundle footprint: NOT_MEASURED.** The three self-hosted font packages add
  runtime font resources. No measured before/after JS+CSS+WOFF2 byte totals,
  transfer size, cache hit ratio, layout shift, or page speed is claimed.
  Before release, measure build artifact output and 390px/1440px loaded
  pages against the previous stable production build, then record actual
  deltas; do not fabricate download-time or development-time savings.
- **Release authority:** V4 paper and the user-approved simplified branding.
  Exact first-party source is PORTED/ADAPTED, not claimed COPIED unchanged;
  no unreviewed external source or REA reconstruction was adopted.

## Acceptance gates
Exact source: heading == "Apply with confidence", exactly one text-bearing banner
node, no img/other copy, CV instruction visible on 390px and desktop, original
Manual/Assisted/Automatic and Browse actions reachable, no scroll overflow at
zoom-out, actual self-hosted Fontsource families load successfully (no CDN),
high-contrast crisp text. Run npm ci, Vitest, TypeScript/Vite build, Playwright,
server Python suite, Woodpecker and production health + release-sha checks.
A successful synthetic test is NOT production verification. Deployment
and independent review remain separately gated.

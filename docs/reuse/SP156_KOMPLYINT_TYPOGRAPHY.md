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

## Acceptance gates
Exact source: heading == "Apply with confidence", exactly one text-bearing banner
node, no img/other copy, CV instruction visible on 390px and desktop, original
Manual/Assisted/Automatic and Browse actions reachable, no scroll overflow at
zoom-out, actual self-hosted Fontsource families load successfully (no CDN),
high-contrast crisp text. Run npm ci, Vitest, TypeScript/Vite build, Playwright,
server Python suite, Woodpecker and production health + release-sha checks.
A successful synthetic test is NOT production verification. Deployment
and independent review remain separately gated.

## REA-FIRST execution decision and reproducibility (review follow-up)
**Status: REA_NOT_APPLICABLE; REA_NOT_RUN.** The actual authorized first-party
Komplyint source at `komplyint/komplyint-website@76c00948638cd2db699f78c58d6885117f676014`
was directly readable at the three original modules listed above. The original
pinned Fontsource npm distributions, exact package versions, lockfile integrity
and OFL-1.1 license evidence were also available. No REA behavior reconstruction
or proprietary source recovery was needed, attempted or adopted; therefore an
REA tool revision, recovered artifact and recovered-code comparison are **not
applicable / none**. The authorized adaptation is direct first-party source
inspection and published, license-compatible font package reuse; this is not a
claim of a successful REA extraction. Direct reuse must remain pinned to the
donor/source modules and destination paths above.

## Runtime footprint and performance receipt
**NOT_MEASURED:** independent before/after built JS/CSS/font transfer bytes,
compressed payload, network requests, font render delay and LCP were not
measured against the deployed baseline. Three additional font packages and
multiple explicit subset/weight imports were introduced, so a build PASS is
not evidence of zero runtime cost. Verify actual build size and mobile font
loading on the exact release image; preserve the locally hosted/locked fonts
and allow only needed font faces if a measured regression appears. Runtime
performance impact and development-time saving: **NOT_MEASURED**. The public
site was still at release `cee0017091e5` when inspected on 8 Nov 2026; its
speed cannot be compared to an unreleased candidate by assumption.

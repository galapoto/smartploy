# SP124 — Prismatic SmartPloy task-focused design + browser first

**Source:** owner-supplied `Prismatic_Complete_Design_Kit(1).zip`,
`Prismatic_Design_Architecture.pdf` (49 pages), `AI_HANDOFF.txt`,
`data/profiles.json`, `data/foundation.tokens.json`,
`data/component-contracts.json`. Screenshots submitted 4 Nov 2026 show
white-on-white review cards, very narrow central editor at high zoom, too
many borders and large unused side gutters. Source decisions are bounded
by the existing SmartPloy authentication/application/release contracts.

## Adopted / changed
- **Identity:** Adopt the dedicated `smartploy` profile (Plus Jakarta Sans
  heading, Onest UI text, timeline/steps, 24px-style rounding and restrained
  elevation). Reuse cyan SmartPloy mark / navigation, but prioritise task
  status and contrast rather than copying the kit's synthetic data.
  Font import may fail offline; first-party system fallbacks preserve layout.
- **Navigation:** An accessible, visually distinctive 38px bidirectional
  `Expand sidebar` / `Collapse sidebar` button, `aria-expanded`,
  `aria-controls`, keyboard focus, persistent **non-personal** layout
  preference only. At first use CSS viewport <=1280px starts compact.
  At <=1000px (including browser zoom) a separate explicit overlay drawer
  replaces the permanent rail; it displays full navigation regardless of
  saved compact preference. Logo, all routes and user status remain.
  No auto-hide timer that could unexpectedly interrupt the applicant.
- **Full use of width:** Undo old 1090px application-flow and 1130px
  start-flow caps; use all parent width with clamped side padding. In
  Application Studio, task list + exact-job editor uses flexible columns.
  An inline-size container query makes the job list a horizontally
  scrollable compact strip when the *available content area*, not the
  physical device, becomes narrow. This adapts to zoom, desktop,
  sidebars and split-screen without forcing the user to zoom out.
- **Density / depth:** Flat job list, subtle raised task surfaces,
  purposeful 4px selected indicator, no repeated full-grid heavy borders.
  Do not hide sections, document history, employer boundaries or receipts.
- **Dark colour parity:** Define separate canvas, raised card, nested
  card, text and muted text roles. Apply them to original problem surfaces:
  `.studio-review-queue`, `.studio-next-action`,
  `.document-coach-checks li`, `.studio-journey`, form fields, AI,
  employer handoff, CV, letter and applicant queue. Contrast target WCAG
  2.2 AA; token pair ratio alone is not full certification. No broad
  CSS `!important` blanket.
- **Playwright first:** In the Assisted walkthrough, replace the
  copy-only packet button with a direct **Start Playwright form filling**
  action using the **existing** local browser handoff. The explicit
  reviewed packet and local pairing remain required. The browser can
  open a user-approved public HTTPS employer form outside the original
  ATS list. Field selection/upload are reviewed; it stops before
  employer Send, MFA/CAPTCHA or sensitive answers. Untrusted hosts,
  cross-origin redirects/iframes and unsupported custom widgets remain
  review/manual cases. Do not claim every arbitrary website works.
- **Package boundaries:** Keep complete real CV/letter generation, private
  profile questions, accessible notices, account verification and
  source/revision/receipt safety. No guessed private applicant details,
  actual employer send or fake positive outcome introduced.

## Reuse / evidence
First-party existing ApplicationStudio, App shell, theme mode, local
Playwright bridge, CI test fixtures and exact-source gate are reused.
REA tooling unavailable in this execution context (`REA_BLOCKED`);
no external repository copied and savings are UNKNOWN. The kit is an
architecture/design reference with synthetic records, not a working
production integration.

## Acceptance gates
1. React unit tests: collapse/expand, persistence, mobile menu, local
   component accessible labels; check semantic dark colour pairs.
2. Real Chromium synthetic acceptance: width 1540 rail expansion and
   saved state, width 850 mobile overlay and no sideways document overflow;
   actual selected application with next-action and live-writing review
   cards dark computed contrast >=4.5:1.
3. Existing Python + PostgreSQL, extension, Playwright, Compose, source
   integrity and exact-checkout release receipts must remain green.
4. Independently inspect FI/EN/SV text, keyboard/AT and 200%-400% zoom
   on the **real deployed version**, including missing/empty/loaded jobs.
5. Follow FEATURE-FIRST-001: release this as one independently reviewed
   user-visible feature; do not wait for further app redesign, but do
   not bypass protected main, Director GO, production backup or real
   authenticated acceptance. Record actual deployed SHA and rollback.
6. Test the exact user journey: uploaded CV -> Assisted -> job missing
   from imported search -> privately add HOK-Elanto TalentAdore URL ->
   Start application -> review CV/letter -> start locally paired
   Playwright -> inspect and fill permitted fields and PDF -> stop
   before employer final Send. No customer CV or external employer
   requests are included in synthetic CI.

**Release state:** SOURCE_CANDIDATE. Green GitHub CI is not production,
a generic browser cannot bypass an arbitrary employer's login/CAPTCHA,
and no applicant submission is claimed.

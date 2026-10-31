# SP91 — SmartPloy Career Atlas (product visual identity)

**Status:** implementation branch. Production is not verified until the exact approved SHA
has been deployed and signed-in browser acceptance completed.

## Product distinction

SmartPloy is an independent **job-application workbench** built for Finland.
Its interface must not be confused with Komplyint Oy's corporate site, ObumAI's
agent console, or Proctor's invigilation workspace.

- **Primary composition:** light, readable application surface and a persistent
  ink-dark navigation rail; a separate CV-first editorial entrypoint.
- **Colour:** deep maritime ink `#0b1d2b`, sea blue `#116d82`,
  navigational cyan `#04bfd0`, restrained apricot `#f3ae73`,
  and warm-light paper `#f6f8f6`. Manual, Assisted and Automatic get
  distinguishable cyan, violet and burnt-apricot accents. Colour is redundant
  to text; it must never be the only indication of a chosen mode.
- **Type:** Manrope for accessible everyday controls, Newsreader for
  short editorial headings only. Fall back to system sans and Georgia.
  Avoid tiny text in task-critical buttons; controls should have clear hit areas.
- **Wayfinding:** visible 4-stage CV → method → matches → review path;
  explicit next actions, not ornamental dashboards.
- **Evidence:** "draft prepared", "review required" and
  "actually submitted" remain distinct. A mode selection or CV upload never
  grants submission approval.

## Carefully selected Komplyint design ideas

Reused patterns: controlled white space; predictable spacing rhythm
(8/12/16/24/32px); compact but legible task cards; simple page hierarchy;
responsive layouts; visible focus; reduced motion; evidence-backed claims.

Not reused: Komplyint's forest green / restrained red corporate colours,
charcoal-first marketing composition, EB Garamond/Lato identity, service-sales
tiles, logo/video, or branded corporate language. SmartPloy's existing inline
vector mark remains the product logo.

## Scope and invariants

Changed presentation only: `career-atlas.css` loads after legacy styles.
`StartChoices` adds an identity masthead and numbered mode cards.
`ApplicationJourney` applies the same per-mode colour cues.

No new submission rights, worker execution, unreviewed answers, credential
handling, source acquisition, or account scope was introduced.

- Without a CV: show upload/create and browse, but **no mode buttons**.
- With a CV: Manual, Assisted and Automatic are separate, explicit choices.
- Manual opens only an employer website and optional private draft work.
- Assisted prepares documents and supported reviewed form handoff.
- Automatic prepares private batches; employer-authorized reviewed submission
  is a separate action with exact evidence, not a general browser auto-submit.
- Preserve previous drafts / letters and the release-parity indicator.
- Keep semantic buttons, keyboard focus and status text.
- Do not promote any empty widget or an unavailable capability.

## Acceptance plan

1. `cd web && npm run test && npm run build` (CI may perform these).
2. Check 390px, 768px and 1440px, including long Finnish job titles and
   browser zoom up to 200%; confirm no horizontal overflow.
3. Signed in with no CV: see upload/Create CV/browse, no mode buttons.
4. Signed in with CV: three mode cards, click routes to guided application;
   changing mode remains explicit, with no employer send.
5. Check keyboard focus and prefers-reduced-motion.
6. Check application review queues, release parity, sidebar/nav and
   signed-in account switching; no private data leak.
7. Deploy an **exact SHA**, run service and in-browser release checks and
   record the production acceptance receipt.

## Existing production blocker (separate from SP91)

The operator's 2026-10-31 log for production SHA
`077f0c3378b61bb0808d65652b4a9b2166636b53` reports healthy containers,
but AutoDraft acceptance remains **HOLD** with
`AUTO_DRAFT_FRESH_RUN_MISSING`. This design change cannot resolve or waive
that worker runtime gate. A new valid worker run and the corresponding
online release-evidence check are required before an AutoDraft PASS claim.

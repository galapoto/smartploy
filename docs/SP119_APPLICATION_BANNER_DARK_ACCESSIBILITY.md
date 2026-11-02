# SP119 — Job-application banner and dark-mode legibility

Status: UI implementation candidate. Not released to production until reviewed and merged by the authorized release owner.

## Why this change
Applicant-reported screenshot (3 November 2026) showed a winter landscape above the CV-first journey, while the task is applying for work. It also showed near-invisible dark-mode microcopy, especially `FINLAND · PRIVATE WORKSPACE`. Existing legacy/light-theme selectors for the masthead, progress chips, disabled method cards, status badges and long review cards were overriding semantic dark-mode colors.

## Changes
- Replace only the decorative top panorama with a first-party SVG illustrating a CV card, job matches, and an application-review checklist. No remote image, copyrighted stock art, fake match rates, applicant information or employer data.
- Keep the original fully visible SmartPloy logo, sidebar, application journey, manual/assisted/automatic choices, identity boundaries, employer submission gates and light/dark switch.
- The new banner text is semantic live HTML, not baked into the image. Decorative SVG is hidden from the accessibility tree. The CTA opens actual CV upload when no CV exists and navigates to the existing application-method page when a CV exists. No implicit application submission.
- Keep the first real `h1` in `StartChoices`; banner's display headline uses a paragraph to avoid reversing the heading hierarchy.
- Use higher-contrast dark-mode colors on status, card copy, active steps, unavailable actions, warning and private-data review panels. Use 7:1+ representative foreground/background pairs in executable tests.
- Provide keyboard focus rings, narrow-screen adaptations and reduced-motion support. No JavaScript or storage added beyond existing button action.

## Reuse / REA evidence
- Source: `galapoto/smartploy` baseline `804747bd9f01f999f9e806dcf96459bb215bb8f1`.
- Inspected and reused the existing `App.tsx`, `StartChoices.tsx`, `finland-shell.css`, `career-atlas.css`, `theme.ts`, `BrandMark.tsx` and existing React UI tests.
- Existing palette, typography, icon package and persisted theme retained; wrote only a separate overlay theme and a local SVG banner plus focused tests. No third-party source copied.
- REA: `REA_BLOCKED`, as no authenticated REA runtime or executable is provided in the current session. Visual screenshot review and code inspection are not REA runs; savings unknown.
- Expected evidence: React/Vitest, Vite build, Playwright synthetic UI checks, separate independent accessibility/privacy review and sign-in production acceptance before production claims.

## Boundaries
This is a visual/workflow clarity change, **not evidence that a TalentAdore form was filled, a CV was uploaded to HOK-Elanto, or an employer accepted a submission**. The supported real-employer automation candidate remains separate from the currently deployed build. Never convert artwork or green CI into a misleading application receipt.

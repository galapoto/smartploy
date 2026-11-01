# SP99 — Original-style SmartPloy shell: Finland panorama, complete logo and light/dark mode

## The decision

Restore the earlier, simpler **DM Sans** typography and light navigation feel
from the original SmartPloy stylesheet rather than the later Newsreader serif /
ink-dark-sidebar combination. Keep the good parts of the Career Atlas redesign:
clean spacing, readable cards, polished workflow, high-contrast focus rings and
existing functional navigation.

## Real implementation

1. **A unique Finnish image at the very top:** On the dashboard, a panoramic
   original AI-generated archipelago-in-winter composition with warm low sun,
   islands and ice-edged granite coast. The image is **artwork**, not a claimed
   real photograph of a named place; no stock-image license or external image
   host. The shipped image is a local AVIF, generated specifically for this
   design, with an original SVG illustration fallback. Compact horizontal
   aspect ratio limits the impact on the first CV action.
2. **Complete main-page logo:** The actual SVG SmartPloy mark plus visible
   SmartPloy wordmark appear in a separate page identity strip under the
   panorama, not covering the artwork. The full identity strip remains present
   in compact form on non-dashboard pages. The established sidebar and
   sidebar brand remain, with fully contained SVG sizing and no cropping.
3. **Original typography:** DM Sans for body and headings, grounded navy-blue
   light palette, white navigation rail, restrained card hierarchy, corrected
   lettering/spacing. Not a revert of the working SPA.
4. **Real light/dark control:** An accessible Moon/Sun switch in the header,
   with accurate \`aria-label\` and \`aria-pressed\`, updates the root attribute
   \`data-smartploy-theme\`, native form \`color-scheme\` and browser theme
   color. The chosen mode persists via \`localStorage\` (gracefully handles
   unavailable storage). Initial mode respects an already saved choice and
   otherwise follows the browser's dark preference. Cross-tab changes sync.
   Theme skin covers shell, sidebar, dashboard panels, application flow,
   document editors, job cards, inputs, AI comparison and modals.
5. **Mobile:** Preserved off-canvas navigation, functional menu/scrim,
   visible theme control, complete in-page mark, no horizontal overflow.

## Explicitly preserved

- CV-first upload/create → Manual / Assisted / Automatic selection and job flow.
- Complete Finnish/English cover-letter generation and review; private Ollama
  diagnostics and suggestion consent; CV edit/undo; download/export.
- OIDC identity, tenant/revision isolation, security/privacy and existing
  employer provider permission, once-only intent and receipt gates.
- Only the outdated after-CV Helsinki SVG promotional block is removed;
  it is replaced by the consistent panorama visible on initial entry.
- No new data transfer, model call, employer action, database migration,
  external font/image credential, or background task.

## Tests and acceptance

- Unit: persistence, system fallback, cross-tab updates, root color scheme;
  main dashboard panorama/logo before CV first step and theme switch.
- Chromium: exact AVIF + SVG assets served, image decodes, no cropped logo,
  desktop light/dark screenshot proofs, persistent reload and mobile sidebar
  with no horizontal scroll. Existing browser account-switch tests updated
  from the now-retired promotional tagline to the real CV-first heading.
- Full PR-head and merged-main five-gate CI, then exact approved SHA OVH
  deploy and \`release-evidence.sh --online\` with public release parity.
- Signed-in visual QA: desktop/mobile banner crop, complete logo, theme switch,
  readable candidate documents in both modes and full application journey.

## Current release status

Working branch from deployed SP98 exact SHA
\`62b46a06939bca359843f7bb5961da1702a6aaeb\`.
This document is an implementation contract, not evidence that SP99 was
deployed to production.

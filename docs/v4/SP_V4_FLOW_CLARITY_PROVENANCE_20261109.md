# SmartPloy V4 — application-flow clarity and contrast adoption

Date: 2026-11-09. Authority: `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` sections 1, 4, 6, 7 and `AGENTS.md` (REA-FIRST-001, FEATURE-FIRST-001, LEAN-REA-FLOW-001). Outcome: applicant sees only the relevant CV → method → job → document review controls, and the AutoApply safety notice is legible on the dark website.

## Provenance: explicit first-party adaptation, no external reconstruction

- **Donor repository:** https://github.com/galapoto/smartploy
- **Exact original source commit:** `ac08dbf05e8bb1bb8545e159d0f1a6dc030c9ff1` (production release before this change).
- **Source files:** `web/src/ApplicationJourney.tsx`, `web/src/sp-v4-monochrome.css`, `web/src/ApplicationJourney.test.tsx` and `web/src/sp-v4-monochrome.test.ts`.
- **Destination:** the same four files in `galapoto/smartploy`, branch `fix/v4-action-flow-contrast-20261109`.
- **Ownership/license:** authorized same-owner first-party SmartPloy code, existing source kept in place; no new third-party source, assets, dependencies or licenses.
- **COPIED unchanged:** none. **ADAPTED:** existing ApplicationJourney CV, method and job stages, existing action handlers and SP V4 palette. **SANITIZED:** removed low-contrast light notice styling, redundant inactive text and non-actionable selected-job button. **INTEGRATED:** conditional visible stages in the real source component, keeping stored job/CV scope, strict login checks and existing form/approval engine. **NEW:** small local state for explicit method editing, CSS stage and contrast overrides, targeted regression cases.
- **REA decision:** `REA_NOT_APPLICABLE` to code recovery: exact readable first-party source/history was available; no reconstruction or third-party donor needed. REA not run; claimed time savings: `NOT_MEASURED`.
- **No runtime dependency added:** CSS + JSX + tests only. No new backend, browser actor, API, permission, storage or submit path.

## User actions and acceptance

1. With no CV, show only CV upload/creation and existing primary guidance; avoid future-job and final-review panels.
2. With a CV but no method, show only Manual / Assisted / Automatic choice.
3. With method selected, show current matches and existing selectable jobs; keep completed CV actions under a compact disclosure, and allow explicit "Change method" without resetting an account or authorizing employer submission.
4. After selected automatic preparation succeeds, reveal the review handoff; no fake "review completed" progress before a draft exists.
5. Remove redundant status prose and the non-progressing "Selected job" button. Selection itself remains explicit and never creates a draft without user action.
6. Apply legible black/white guidance to all flow notices and document-journey guidance, including mobile and both themes.
7. Keep existing `onPrepare`, `onPrepareSelected`, `onOpenApplications`, employer permission gates and final-submit separation. Do not claim employer completion from a source/CI pass.

## Verification ledger

- Source transformations were checked against exact upstream strings before writing (no unbounded regex replacement).
- Vitest regressions: `web/src/ApplicationJourney.test.tsx` and `web/src/sp-v4-monochrome.test.ts`; run via existing full GitHub Actions and Woodpecker CI.
- Reviewer: independent non-author review required before main merge/deploy; project agent must seek a qualified reviewer within authorized `galapoto` repositories. The generating agent cannot self-approve.
- Status at PR creation: `SOURCE_READY`, CI and reviewer outcomes pending. `DEPLOYED=NO`, `USER_VERIFIED=NO`.
- After reviewed CI qualification, promote exact SHA with existing OIDC `deploy/personal/scripts/deploy.sh` + backup + matching public `release.json`, `healthz` and signed-in mobile/desktop journey. Real employer form not in this UI-slice claim.

# SmartPloy V4 — Rapid Release Sprint R1 (11–18 November 2026)

**Version:** 1.0.0 / 2026-11-11 09:15 Europe/Helsinki (UTC+02:00).  
**Authority:** Existing approved \`docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md\` v4.0 (§§1.1–1.3, 3–8, 11–12), \`AGENTS.md\`, \`SMARTPLOY-OBUMBROWSER-001\`. This is a dated *execution schedule and evidence ledger*, not a replacement product specification. The revised hosted-browser ownership is already approved by the user; no new hosted Chromium may be built inside SmartPloy.

**User outcome:** A candidate can use the actual signed-in production website to select their own reviewed CV, choose Manual / Assisted / AutoApply, select an exact real job, review truthful documents, observe approved fields/questions and CV being entered into the *same real employer form*, stop safely at ready-for-review, and recover accurately on refresh/disconnection. Employer submit is a separate explicit authorization and is never inferred.

## Verified baseline and definition of shipped

- **Main/production starting SHA:** \`afba0046803047587b2c33848bdd0eea5dbad4c4\`. Exact-deploy OIDC and release evidence PASS: \`/srv/obum/data/smartploy/deploy-state/release-evidence-20261111T022218Z-3534998.txt\` (reported by server operator). Public \`/release.json\` and \`/healthz\` report \`afba00468030\`, Postgres and 32 workers ready. Includes approved UI card-system PR #332, Chrome extension v0.5.4 #333, internal ObumBrowser URL-only intent #334.
- **NOT verified today:** authenticated full UI visual audit, signed-in real employer form filled *with exact CV uploaded* to review, independent local Playwright first full case, managed extension updates on another device, real ObumBrowser native service/API.
- **"Shipped" means:** exact authoritative main SHA + independent review/policy checks + GitHub Actions and Woodpecker success + exact production images/site/release-evidence + tested signed-in visible user action and real observation/receipt. CI-only, source-only, draft PR and read-only health checks are narrower evidence states.
- **Release immediately:** each qualified feature must reach main and production separately; do not wait for M6. Do not downgrade signed-in/employer acceptance when evidence is missing.
- **No universal promise:** One *specified supported employer form* to review is the first complete proof, not "all ATS sites" or unattended mass submission.

## Time-bound milestone and workstream board

Targets are **aggressive exit gates**, not guarantees. Do not reset the clock whenever a build/review fails. All dates EET, 2026.

| ID | Target | Practical implementation / reuse | Candidate-visible exit signal | Tests and evidence | State at plan creation |
|---|---|---|---|---|---|
| M0 — Lock production baseline | 11 Nov 09:15 | Verify deployed SHA, exact reviewed spec/PRs; no new code | Existing candidate website remains available | Release-evidence PASS, /healthz, /release.json, image provenance | **DEPLOYED**; full user journey NOT_VERIFIED |
| **M1 — Contrast and usability closure** | **11 Nov 12:00** | Adapt the existing final-loaded \`sp-v4-card-surfaces.css\`; remove remaining washed-out blue/mint status cards and editor panels; no framework | Readable dark/white cards and actions on home, jobs, CV/letters, Apply; phone dark/light | Computed WCAG AA ≥4.5:1 across targeted surfaces, actual 390px Chromium + UI tests + screenshots + real signed-in visual follow-up | **SOURCE_READY IN PROGRESS** at \`fix/v4-contrast-closure-m1-20261111\` |
| **M2 — Chrome extension application to review** | **11 Nov 18:00** | Use deployed v0.5.4 \`browser-companion\` + signed-in review packet, exact ATS adapter, typed questions, separate approved PDF attach; no new executor | Candidate clicks Start, sees approved fields persist, uploads exact CV with explicit approval, can inspect complete employer form; no automatic send | Lever/Ashby/Greenhouse native Chromium + real authorized employer form-to-review, observed PDF filename/hash/ack and no submit, blocked and recovery paths | Existing code deployed; **real end-to-end NOT_VERIFIED** |
| **M3 — Visible local Playwright parity** | **12 Nov 09:00** | Reconcile stacked, pending first-party PRs #315 → #316 → #317 → #320 and historical #278; extract smallest existing safe code, no new hosted browser | Visible candidate-controlled Playwright browser can inspect, fill, settle and attach reviewed CV then stop to review | Local Chromium, one-use pairing, wrong-origin/owner, exact CV digest, lost connection, zero submit, package + signed-in path | **SOURCE CANDIDATES**, not qualified/main |
| **M4 — Real form coverage and recovery** | **12 Nov 18:00** | Reuse pending PRs #311 (select), #312 (radio), #308 (bindings) in small independently reviewed slices; do not enable blanket click | Ordinary dropdown/radio and multi-step questions handled after approval; ambiguous/sensitive fields go to candidate | Cross-provider widgets, positive/negative actual DOM changes, resume/stop, no duplicate writes, explicit unsupported-site fallback | **NOT QUALIFIED** |
| **M5 — One coherent application path** | **13 Nov 09:00** | Existing Case/Packet/Observation/Receipt API; reuse CV/letter ZIP/export and responsive shell; remove dead-end controls | CV → method → chosen job → editable docs → real browser → review → persistent tracking, including mobile | Signed-in desktop + 390px mobile, light/dark, keyboard/zoom, download source hashes, 1 refresh/reopen, clear next action, receipt status | **PARTIAL FUNCTIONALITY / E2E NOT_VERIFIED** |
| **M6 — Functional scoped release candidate** | **13 Nov 18:00** | Promote separately qualified slices through first-party OIDC deploy script, owner review/QA and existing rollback | A clearly named supported end-to-end application flow is **USER_VERIFIED**; unsupported sites show Manual/Assisted handoff, not fake success | Main CI, Woodpecker, prod images/ZIP hashes, backup + release-evidence PASS, signed-in screenshots, real consented employer-to-review receipt; no unapproved final send | **TARGET / NOT_YET_QUALIFIED** |
| M7 — Managed companion + shared hosted browser | 14–18 Nov (conditional) | Reconcile PR #323 for Chrome Web Store managed updates; adapt SmartPloy's URL-only intent to *qualified* independent ObumBrowser API; retain Chrome + local fallback | Install/update extension on another device; later, authenticated shared browser viewer with live candidate takeover | Real store/package provenance; ObumBrowser native same-session pixel/control, OIDC scope, owner isolation, egress, pause/stop and versioned service receipts | **DEPENDENT** on marketplace process and independent ObumBrowser release |

**Timeline risk rule:** A missed gate does not silently become "done" or shift every milestone. Record the exact failing test or absent real-site permission, ship every independent qualified part, and replan only the affected dependency. Time targets may be renegotiated; security, no-fake-success and proper employer consent may not.

## Parallel lanes and release gates

| Lane | Immediate input | Decision / next independently ship-ready slice |
|---|---|---|
| L1 UI/UX | Main #332 and old style sheets | M1 contrast CSS + browser computed foreground/background + mobile route |
| L2 Chrome AutoApply | Deployed v0.5.4, reviewed attachment and question modules | M2 one real supported employer form through review (manual final submit) |
| L3 Local visible Playwright | Existing #315/#316/#317/#320; original ObumAI/SmartPloy donated code | M3 real local packaged browser/CV/letter + one-use bridge |
| L4 Typed form coverage | Existing #311/#312/#308 and Chrome page-questions | M4 one widget family at a time |
| L5 QA/release | CI and protected deploy/backup, user-sign-in browser | Exact-head review, producer output, release evidence, signed-in screenshots |
| L6 Shared browser | \`obumai/ObumBrowser\` approved spec and FlowReader extraction | M7 separate client adapter **after** native v1 acceptance |

No lane may wait for completion of other lanes when its smallest feature has independently passed approved tests. The only sequencing gates are where an actual user journey depends on a prerequisite capability.

## Non-negotiable acceptance examples

1. **M1:** dark theme selected surfaces have dark backgrounds, no pale gradient and readable light text; light theme is neutral/white with dark text; actual focus, disabled/warning/selected semantics preserved. No duplicate inert control. Screenshot and source SHA required.
2. **M2:** one real supported job URL remains exact after any redirect; signed-in account owns the reviewed packet; approved fields persist after reactive render; candidate explicitly approves *the same saved current CV PDF*; browser reports local placement **separately** from employer acknowledgment; form reaches observed review, not a claimed send.
3. **M3:** local helper is visible and candidate-controlled; at most one active one-use pairing; cannot use stale job/CV/answer/URL; disconnect is not an invitation to blindly repeat or send. No new hosted Chromium service.
4. **M4:** each newly supported type has legal ordinary-field policy, never clicks attestations/consents/credentials or infers sensitive answers; wrong-value/current DOM change fails closed, provider-specific regressions pass.
5. **M5/6:** original saved application case/state persists across reload, and every primary action advances the same job; signed-in desktop/mobile acceptance; public SHA + API + ZIP parity; rollback proof. Only real employer receipt merits \`confirmed\`, not merely a click.

## Mandatory run receipt to append on every implementation pass

\`RUN_ID | DATE_EET | MILESTONE | APPROVED_V4_SECTION | BASE_MAIN_SHA | DONOR_REPO_URL@COMMIT:FILE | COPIED | SANITIZED | ADAPTED | INTEGRATED | NEW | REA_STATUS | TEST_COMMANDS_AND_RESULTS | PR_HEAD_SHA | NONAUTHOR_REVIEW | MAIN_SHA | MAIN_CI | PRODUCTION_SHA | SIGNED_IN_BROWSER_EFFECT | USER_VERIFIED | NEXT_ACTION\`.

Use \`Copied: none\` when no external bytes or unchanged donor files were imported, and document why. **Never invent** provenance, actual user effects, or time savings. Exact reviewer approval remains distinct from advisory Codex comments; the project agent must proactively locate an eligible independent reviewer in the repository and then other authorized \`galapoto\` repositories if needed. Never weaken branch protection.

**Run R1 (11 Nov)** — M1 contrast closure: first-party donor \`galapoto/smartploy@afba0046803047587b2c33848bdd0eea5dbad4c4:web/src/sp-v4-card-surfaces.css\`, with shadcn/ui MIT design principles already adapted in the existing project; \`COPIED unchanged: none\`. ADAPTED final-loaded existing token sheet; NEW regression assertions. REA_NOT_APPLICABLE to readable first-party CSS. At document creation SOURCE_READY; CI/review/main/prod/user verification pending. Work is not marked released until checks and live evidence arrive.

## R1 independent review correction (11 Nov, exact-head qualification required)

Codex reviewed preliminary M1 head `b8be66519119e62fb5ff732bdb71515f80368443` and identified a genuine **P2**: unselected Applications filter buttons and numeric count badges still had old blue/white styling. The preliminary 15-surface fixture tested only a selected button without a real count span, so it missed the defect. **ADAPTED** the native final-loaded CSS to style unselected, hovered and selected filters and both badge states; **NEW** 18-surface real-Chromium dark/light fixture coverage, plus source assertions. No button action changed. The earlier green CI is superseded by the new exact-head checks; review/qualification must repeat before merge and production. The date target remains unchanged.

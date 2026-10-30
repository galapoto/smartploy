# SP69 — Explicit application method after CV connection

**Date:** 2026-10-30  
**Plan:** SP21 P0-A and P0-B (CV-first journey), Agentic SmartPloy §2  
**Baseline:** `d4684afce5509939c03bc75e121f533799a4a529` (main before SP69).  
**Scope:** Frontend behavior and synthetic acceptance only; no provider API, database schema, identity, consent, worker, source polling, CV storage or production environment change.

## Owner-reported defect

After a CV was connected/uploaded, the app opened application matching but silently treated the user as **Manual** because `flowMode` defaulted to `manual`. It was unclear whether Manual, Assisted or AutoApply would send a real application, how to proceed after CV upload, or where tracking happens.

## Decision / user journey

1. **Connect CV:** show the real uploaded filename, replace and review controls. If uploaded from outside the guided page, unset the local application-method choice. If the user previously chose a method *inside* the guided page, preserve it while uploading there.
2. **Explicitly choose method:** no implicit default; visually distinct methods with who fills, who sends, exact next action and selected state. Choice itself confers **no employer permission**.
   - **Manual:** browse CV-matched jobs, open the exact employer form, user fills and sends; a private draft is optional.
   - **Assisted:** select support level (find only, documents, or reviewed form fill), create the private exact-job workspace on a deliberate click, edit/review materials, then human send or separately authorized partner transfer.
   - **Automatic:** select exact current jobs (up to 15), prepare private drafts and per-job case agents, then review each result. **No automatic employer submit from this screen.** Provider submission requires independent employer rights, current review and one-time exact authorization; unsupported forms remain Needs Review.
3. **Choose matching job:** existing owner-only CV/current-job API, pagination, pinned selected job and search filtering continue unchanged. Matching results can be viewed even before a mode is chosen, but actions to create applications remain locked until method selection.
4. **Review and track:** original application workspace and browser/provider evidence distinctions remain the source of truth; no application is called submitted without trustworthy proof.

**Homepage:** show a connected-CV status and primary **Continue with my connected CV** action; otherwise offer **Upload CV first**. Choosing a method before upload remains valid. Account switching clears the local choice; nothing private is stored in the browser.

## Reuse, REA and build method

- **Reused as-is:** first-party `StartChoices`, `ApplicationJourney`, `App` routing, `getCVJobMatches`, `uploadCV`, `ApplicationStudio`, employer URLs, browser companion restrictions, per-job private preparation/agent queue, existing CSS system, Vitest and Playwright fixtures. No new client dependency or backend route.
- **Adapted first-party:** existing mode buttons, progress bar, upload navigation and source-current job actions. The only deliberate product behavior change is requiring a real choice after direct CV upload. All existing security gates remain intact.
- **New:** explicit selection gate, connected-CV next-action copy, mode responsibility/next steps, style hierarchy and synthetic regression cases.
- **REA status: REA_NOT_APPLICABLE to this change.** Checked canonical `morluto/rea` public documentation on 2026-10-30; REA is designed to recover behavior from binaries/third-party apps/JS bundles. The complete authorized React source, tests, routes and components were already directly available; no external unknown executable or competitor application is being reconstructed. An REA run would add dependencies and risk without recovering missing information. REA was **not installed or run**, so no recovered code or measured speedup is claimed. Continue REA evaluation for future unavailable components with legitimate authorized targets.
- **Measured savings:** unknown; no comparable baseline measured.

## Verification plan

- Vitest: CV already connected + no method chosen displays private matched jobs but **no Save draft, Prepare, or AutoApply batch controls**; choosing Assisted unlocks only its expected controls. Homepage displays the connected-CV message and upload-first CTA without an implicit employer action.
- App unit: direct upload leads to CV matching, no implicit default method or server mutation.
- Playwright: production-build synthetic browser journey **dashboard upload -> CV recognized -> method not selected -> Assisted -> AutoApply controls**, with **zero** workspace creates before explicit preparation. Existing Manual CV-first and Search-selected Assisted flows must remain passing.
- CI: exact-head web test, web production build, browser, API and deploy-contract checks in GitHub Actions. CI checks are **not** proof of OVH deployment, native ObumDelivery verification or employer acknowledgment.
- Acceptance after merge: independently confirm that a signed-in applicant sees the choice on the actual deployed `smartploy.komplyint.fi` public origin. Do not claim this until exact SHA and browser checks prove it.

## Delivery status

**Code authored on** `feature/sp69-explicit-cv-first-application-choice-20261030`, subject to PR CI review.  
**Done at source level:** dedicated CV and mode steps, no implicit choice after direct upload, truthful Manual/Assisted/Automatic language, tests added.  
**In progress:** exact-head CI and review/merge qualification.  
**Blocked / not claimed:** production rollout and signed-in user acceptance without authenticated deployment access. KEHA P67 production approval is a **separate source activation gate**, not a reason to hold this UI improvement.

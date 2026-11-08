# SmartPloy — actual-user outcome checklist
**Version 1.0 · 2026-11-08 · Canonical V4 contract applies.**

This board measures **what a signed-in candidate can actually do on the deployed public product**, not plans, commit counts, screenshots from mockups, or source-only tests. Every unchecked target is **NOT YET USER_VERIFIED**. Check off an item ONLY after real authorized production UI acceptance at the exact release SHA, with a sanitized trace or screenshot and actual backend/provider effect. Do not manually edit a box to pretend a result; PR and CI may show engineering progress in the separate source-evidence column.

**State transitions per target:** PLANNED → REUSED/BUILT → SOURCE_READY → CI_QUALIFIED → APPROVED → RELEASED → USER_VERIFIED. BLOCKED preserves the last true stage and names the owner, missing proof and required action. Only USER_VERIFIED earns the checkbox.

**Production snapshot 2026-11-08:** public `https://smartploy.komplyint.fi/release.json` and `/healthz` reported `cee0017091e5`; repository `main` was `37382b54ac9257298e2d32bcd1a2733b87705f60`. Mobile design PRs #318/#319 and Playwright-assisted CV PR #320 were CI-qualified and **unmerged** at this snapshot. Their tests are not production proof. Recheck these facts each implementation run.

## P0 — release and first-use navigation

- [ ] **LIVE-01 · Exact production release.** Operator opens the public app and its release fingerprint; `/release.json`, `/healthz`, served web assets, supported downloads and approved running image SHA agree with one approved reviewed commit. Preserve release evidence and rollback SHA. Source: existing `deploy/personal/scripts/deploy.sh` and `release-evidence.sh`. **LIVE: NOT RUN**.
- [ ] **LIVE-02 · Actual first CV.** A new candidate signs in, uploads PDF/DOCX or creates a CV, sees confirmed parse/save, refreshes and finds the CV retained. Invalid files produce clear recovery; upload alone shares nothing with employers. **LIVE: NOT RUN**.
- [ ] **LIVE-03 · One obvious mode selection.** On Home choose Manual, Assisted or Automatic after CV and see a single clear next action. CV-only browsing works with a truthful automation-limits notice; choice never authorizes employer send. **LIVE: NOT RUN**.
- [ ] **LIVE-04 · Exact job continues.** Search/filter or paste a supported real live employer job, click AutoApply and actually reach that job's applicant-specific workspace—not just a bookmark or dead end. URL, company, role, job ID and signed-in account remain identical throughout. **LIVE: NOT RUN**. Source: #314 synthetic tests.
- [ ] **LIVE-05 · Candidate reviews packet.** Applicant edits/approves factual CV and cover letter for selected job, saves exact private revision, sees available executor and a clear Start AutoApply action. Stale/changed job or document requires new review. **LIVE: NOT RUN**.

## P0 — visible employer AutoApply

- [ ] **AUTO-01 · Chrome extension works.** From the user-visible SmartPloy flow open the exact permitted employer form in Chrome, inspect, fill authorized ordinary fields, observe persisted values and stop at review-ready; no hidden final send. **LIVE: NOT RUN**. Source: #315/extension PRs, synthetic only.
- [ ] **AUTO-02 · Local visible Playwright works.** Download reviewed helper, pair once on user's own desktop, watch visible Chromium navigate exact supported ATS URL, inspect/fill and return truthful stage/progress in SmartPloy. Connection denied/expired results in actionable recovery. **LIVE: NOT RUN**. Source: #316/#317 synthetic only.
- [ ] **AUTO-03 · Correct controls and persistence.** Text/email/phone/location, native selects/radios/checkboxes, dates/numbers and React/autocomplete controls receive ONLY approved values; re-observe after async change/blur; ambiguous or sensitive answers are held for human decision. **LIVE: NOT RUN**. Source: #311/#312 partially covered, not a pass.
- [ ] **AUTO-04 · Reviewed CV and letter attachments.** Candidate explicitly approves exact fingerprinted job-specific PDF attachment; correct file field retains it and employer UI acknowledges receipt where available. Detect wrong document, hidden/duplicate field, changed URL, reset input and unknown outcomes. **Both extension and Playwright** independently qualify. **LIVE: NOT RUN**. Source: #320 successfully tested local file-input attachment synthetically, **not employer-server acknowledgement**.
- [ ] **AUTO-05 · Conditional questions / multi-step.** Detect missing required questions, ask the user only for uncertain/consent-sensitive details, save newly approved reusable facts to their profile, re-inspect dynamically added employer steps and proceed without unsafe guessing. **LIVE: NOT RUN**.
- [ ] **AUTO-06 · Pause, takeover, reconnect, resume.** Candidate can pause an active fill, personally complete unsupported fields, return to the correct job and safely resume from fresh observed state. Crashes/restarts never repeat file upload or send. **LIVE: NOT RUN**.
- [ ] **AUTO-07 · Final send and truthful receipt.** In review-ready state show what will be sent and require separate, case-specific explicit authorization for any supported automatic Submit. Confirm success ONLY from a real provider receipt. On timeout/disconnect mark UNKNOWN and reconcile, never duplicate a submission. Manual final Submit is acceptable until qualified. **LIVE: NOT RUN**.
- [ ] **AUTO-08 · Two real employer families.** Repeat the same complete approved CV→job→form→review-ready acceptance on at least two supported *currently live* ATS families using both approved executors; report exact supported/unsupported counts. Stop at the form's final send boundary unless user specifically authorizes it. **LIVE: NOT RUN**.

## P1 — documents, profile and premium UI

- [ ] **DOC-01 · Full usable CV.** Generate/edit/export a complete, factual, tailored Finnish and English CV in PDF and DOCX, with accessible layout, ATS-readable extracted text, correct diacritics and retained edits. Reopen download and verify contents, not just a link. **LIVE: NOT RUN**.
- [ ] **DOC-02 · Full usable cover letter.** Generate a complete, employer-specific, evidence-grounded Finnish/English letter; edit, download PDF/DOCX and verify exact version; no invented experience or generic placeholder. **LIVE: NOT RUN**.
- [ ] **PROFILE-01 · Reusable applicant data.** User can inspect, approve, edit and delete permanent application facts and prior question answers; each new permitted field is safely saved for later applications, tenant-isolated, with CV-only option and clear limits. **LIVE: NOT RUN**.
- [ ] **UI-01 · Minimal, beautiful, working UI.** Home/Jobs/Applications/CV/Profile have coherent action-first cards, compact copy, Finland/banner branding, expandable sidebar, no endless spinner, usable controls with light/dark and responsive 320/390/768/1440px, 200% zoom and keyboard. Verify in signed-in public app. **LIVE: NOT RUN**. Source: #318/#319 synthetic mobile Chromium pass; no public promotion.
- [ ] **JOBS-01 · Real discovery and filters.** Job cards use verified current sources, usable profession/experience/location filters and correct job detail; choosing a result resumes application flow, unsupported/expired listing is labelled. **LIVE: NOT RUN**.
- [ ] **SAFE-01 · Identity and recovery.** Different accounts cannot read each other's CVs, packets or browser sessions; denied employer hosts and sensitive attestations remain protected; production backup/rollback tested and clear error recovery observed. **LIVE: NOT RUN**.

## How to tick a box

Each acceptance PR/receipt must attach: `target_id`, V4 section/version, target actor and role, public URL/route, approved exact 40-character SHA, approved review + CI link, deployed release/extension/helper fingerprints, actual *signed-in* step-by-step before/after result, sanitized screenshot/trace/provider acceptance (no applicant PII, secrets or CV bytes), failure/negative coverage, tester/time, rollback evidence and disposition. Mark **USER_VERIFIED** and check the corresponding box only if all target-specific criteria pass. For a partial implementation leave the box empty and write `SOURCE_READY` or `CI_QUALIFIED` in its evidence record. Test providers only with legitimate candidate authorization; do not perform real submissions for proof without explicit separate approval.

## Mandatory implementation-run receipt

```text
RUN ID/date/owner:
Approved specification + section + target IDs:
Planned user outcome (specific UI click -> real effect):
Starting main/source SHA + deployed SHA:
Investigated donor order (own repo/history/PRs -> owned related repos -> licensed upstream -> REA when useful):
COPIED unchanged: URL, commit/license, source -> destination (or "Copied: none" + reason):
PORTED / SANITIZED / ADAPTED / INTEGRATED: exact source -> destination and purpose:
NEW code: exact path, reason existing code insufficient:
Actual user flow / UI route, before -> after:
Tests/negative cases, CI link, bundle/dependency delta:
Commit + PR + review decision + approved SHA:
Released? deployment command/UTC time, exact live SHA, release-evidence and rollback:
User-visible? signed-in test proof + target checklist items ticked:
Blocked/unsafe/unsupported, responsible owner and one next action:
Next implementation targets, priority:
```

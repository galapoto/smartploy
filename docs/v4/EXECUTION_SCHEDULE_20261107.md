# SmartPloy V4 — dated implementation and release schedule

**Schedule version:** 1.0, established 7 November 2026 at 15:34 Europe/Helsinki (EET).  
**Owner directive:** AutoApply first; release each smallest independently useful, qualified feature to real users immediately (FEATURE-FIRST-001).  
**Authority:** [V4 production-first contract](SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md), especially sections 1, 3, 12, 14, 15 and 18; [day-zero acceptance matrix](DAY_ZERO_ACCEPTANCE.csv).  
**Nature of dates:** Engineering targets and dependency-aware execution order, **not promises of unattended/background work**. They assume several qualified human/agent lanes and independently authorized production operation. If capacity or authorization is missing, move the blocked feature to an explicit HOLD state and continue the next unblocked slice; **never bypass security, review, CI or real-user verification to meet a date**.

## 1. Baseline: 7 November 2026

| Artifact | Verified source/review state | Current release truth |
|---|---|---|
| main | 57d261d5f2c4484b19923601d1cf48d8c85b5d55 (V4 governance merged) | **Does not** include newer V4 browser runtime; public deployed SHA not independently reverified |
| PR #299, integration/sp135-ui-and-autoapply-20261106 | Open, large integration, 107 changed files; not mergeable at last check | **Do not bulk-merge**; extract vertical features with dependencies |
| PR #311, native dropdown Chrome companion | Open, ready for independent review; 5ef750d3bb5b9d333674ada30146c33db63aa682; synthetic CI #1135 PASS | CI_QUALIFIED; not merged/deployed/user-verified |
| PR #308, broader AutoApply | Open draft, stacked on #299; 4c74e5a424d7c8d865a9984b62262e7d1c1f3c77; synthetic CI #1134 PASS | CI_QUALIFIED source only; integration and release gates outstanding |
| PR #312, radio group in both executors | Open, ready for independent review; 5e97e593177464e21f67b1dae3a8ea38076fa832; synthetic CI #1141 PASS | CI_QUALIFIED child of #308; not integrated into production |
| P0-01 through P0-14 | DAY_ZERO_ACCEPTANCE.csv still marks all **NOT_RUN** for real deployed journeys | No real signed-in full AutoApply journey or running-artifact acceptance may be claimed |

**Release truth audit must be the first observable activity:** obtain the currently running public UI/API/extension/bridge SHA and identity mode from the authorized operator, follow a signed-in account through the actual CV-to-Apply journey, and record where the UI stops. GitHub CI is not a substitute for this.

## 2. Nonnegotiable immediate implementation order

1. **Close the production/source mismatch:** verify actual deployed SHA, auth, public UI/ZIP and job/case status; assess whether PR #311 can be independently approved and promoted. This is not permission to merge without the required independent code/privacy review.
2. **Fix one uninterrupted candidate journey in the existing UI:** upload/choose CV, explicitly choose Manual/Assisted/Automatic, select/add one exact live job, generate owner-scoped workspace and reviewed packet, click Start AutoApply, open correct form, return actionable browser state. The added-job action MUST advance, not merely bookmark.
3. **Reach ready-for-review on one permitted live ATS job with both executors:** use the current ObumAI-derived local Playwright actor and existing MV3 extension, verified approved facts, controlled inputs and exact CV PDF; re-inspect changed fields, display human-only questions, never assume employer acknowledgement or final send.
4. **Release independently qualified vertical slices as soon as their own gates pass.** Do not hold PR #311 for the UI redesign or PR #299. Do not promote a source-only green CI as a shipped feature.
5. **Complete the next automation gaps in parallel:** custom portal location combobox and React persistence; conditional fields, native number/date and reviewed radio/select policies; pause/takeover/resume with durable case ownership.
6. **Ship truthful complete CV and cover-letter generation and the premium connected UI** as separate user-visible slices while the AutoApply critical-path tests continue.

### Execution board: first 7 days

| ID | Target window (EET) | Lane / accountable role* | Smallest complete user-visible result | Acceptance and release evidence | State at schedule creation |
|---|---|---|---|---|---|
| S00 | Sat 7 Nov, next 0–2 hours | A/F: release + QA | Reproduce signed-in CV → mode → job → browser action on **actual current** site; log running SHA, identity, feature flag and first failure | Sanitized signed-in replay, job identity, public release fingerprints; P0-01/02/14 assessed | NOT_RUN — requires authorized live environment access |
| S01 | Sat 7 Nov, next 0–4 hours | A/C: release + extension | Independently review PR #311 and, if approved, release reviewed **native dropdown** fill from existing extension UI | Independent approval, exact-source CI, authorized main SHA promotion, live extension ZIP digest, reversible deployment, signed-in candidate check | CI_QUALIFIED / REVIEW PENDING |
| S02 | Sat 7 Nov, next 0–6 hours | E/A: frontend + integration | CV → Manual/Assisted/Automatic → exact job → Start AutoApply **without dead ends** | Owner-scoped case and resume state, real clickable buttons, no silent send; E2E P0-01/02 | INTEGRATION WORK OPEN; extract minimal slice from #299 |
| S03 | Sat 7–Sun 8 Nov | B/F: Playwright + QA | Candidate watches visible Chromium populate reviewed ATS form and attach the exact approved CV; ends in READY_FOR_REVIEW | Real authorized employer form, correct job ID, PDF hash + observed attachment, no employer final click; P0-03/05/06 | SYNTHETIC_CI_QUALIFIED, REAL-SITE NOT_RUN |
| S04 | Sat 7–Sun 8 Nov | C/F: extension + QA | **Same reviewed job and packet** completed with MV3 browser companion, with safe manual handoff | Separate real employer/Chrome trace, correct packet, human-only questions untouched; P0-03/05/06/09 | SYNTHETIC_CI_QUALIFIED, REAL-SITE NOT_RUN |
| S05 | Sun 8 Nov | A/B/C: integration/executors | PR #312 reviewed native radio-group selection integrated into applicable executor(s) as a bounded slice; no consent toggling | Independent code/privacy approval, exact CI, real form parity and signed-in release evidence | CI_QUALIFIED / REVIEW PENDING |
| S06 | Sun 8–Mon 9 Nov | B/C: browser parity | Custom location/portal-mounted combobox and post-blur React retention, using qualified FormFilla donor rather than a new browser engine | Exact city/ID, no wrong-city selection, no arbitrary fallback; real Chromium both executors; P0-03 | NOT_STARTED |
| S07 | Sun 8–Tue 10 Nov | D: documents/profile | Full tailored factual CV and cover letter in Finnish/English; editable and downloadable PDF/DOCX, exact approved revision and hash | Non-placeholder complete outputs, ATS text extraction, diacritics/page breaks, consent-scoped facts; P0-12 | INTEGRATION EXISTS; QUALITY/EXPORT NOT ACCEPTED |
| S08 | Sun 8–Wed 11 Nov | E: connected UI/design | Premium Home/Jobs/Apply/Applications/Documents/Profile; visible mode chooser, proper collapsible sidebar, Finland Home banner, attractive responsive cards and live browser status | 320/390/768/1440 px, 200% zoom, keyboard, dark/light, focus and reduced motion screenshots; P0-13 | INTEGRATION EXISTS; PUBLIC UI NOT VERIFIED |
| S09 | Mon 9–Thu 12 Nov | B/C/A: reliability | Pause, takeover, reconnect and resume from fresh observation; browser restart does not repeat employer send or upload | Case lease, event log, no stale packet or cross-user reuse; P0-07/08/09/10/11 | NOT_ACCEPTED |
| S10 | Tue 10–Sat 14 Nov | B/C/F: employer breadth | Second real ATS family (e.g. Ashby after Lever) and conditional/multistep form, blocked unsupported controls clearly | 2 independent employer-family full cases, exact application identity, truthful unsupported share, signed-in review-ready traces | NOT_ACCEPTED |
| S11 | Thu 12–Sat 14 Nov | F/A: QA + release | Release matrix and first public supported journey declared USER_VERIFIED only when fully proved | All critical negative tests, exact deployed SHA, rollback rehearsal, real signed-in evidence, extension and Playwright parity | NOT_RUN |
| S12 | 15–21 Nov; parallel, NOT P0 dependency | Separate hosted/semantic worker + F | Per-user isolated hosted browser pilot and larger general-form corpus; no claims of universal support | Session isolation, allowed-origin tests, consent, cost controls, teardown, 30/200-case baseline with numerator/denominator | NOT_STARTED |

*Roles are **responsibility slots, not named or confirmed staffing assignments**. Integration/release = A; Playwright = B; extension = C; documents/profile = D; UI = E; independent QA/security = F. Do not claim six people are currently working.

**Critical-path sequence:** S00 → S02 → [S03 and S04 in parallel] → S11. S01 can ship independently after approval. S05–S10 begin in their own lanes without waiting for the entire critical path, but do not compete for its release-review capacity.

## 3. Feature-sized pull request strategy

- **S01 / current PR #311:** small mainline extension option support; requires independent review and actual live release evidence. No rewrite.
- **S02 / new small mainline PR:** extract existing proven CV/mode/job-to-form connectivity from #299, add true continuation and error messages, owner isolation and E2E tests. Avoid sweeping UI changes.
- **S03/S04 / focused PRs from #308:** reuse the existing local Playwright bridge, first-party companion, form mapper and reviewed packet. Keep Playwright and extension acceptance independent.
- **S05 / PR #312:** source/synthetic qualified radio group, review and integrate without weakening sensitive question handling.
- **S06 / independent donor-based PR:** evaluate AhmadHassan-BTed/FormFilla/src/content/fill/combobox-adapter.ts; copy only the qualified, licensed option/portal mechanics after sanitation, exact review and test.
- **S07/S08 / separate functional PRs:** improve existing document pipeline and React design system; no cosmetic-only success claim or new unrelated frameworks.
- **No bulk merge of #299.** Deal with its mainline conflict only through reviewed minimal patches. Every PR must record source SHA, exact change, reuse manifest, negative tests, reviewer, CI, deployment target and rollback.

## 4. Exit criteria and evidence for every schedule row

- SOURCE_READY: committed existing-source reuse/sanitized code, clear user action, unit/security tests and current reviewed SHA.
- CI_QUALIFIED: native Python/Node/real Chromium synthetic acceptance plus source-integrity checks pass at that exact SHA.
- STAGED_ACCEPTED: candidate can finish the complete promised action through an authorized isolated test environment; no invented browser result.
- RELEASED: reviewed exact SHA merged through permitted path and deployed via authorized native process, feature visibly enabled to intended cohort, rollback available.
- USER_VERIFIED: authenticated user clicks the actual production path and sees the intended outcome with the real executor and correct job/form; publish sanitized acceptance receipt.
- FIELD_VALIDATED: real employer-side evidence supports the exact advertised behaviour; never equate local field values with employer receipt or confirmed submission.

**Production per-feature proof:** GitHub/Woodpecker run; approved SHA; app, helper and extension digests; deployment timestamp; identity mode; enabled flag/cohort; user-visible navigation and field result; case/job URL and consent scope (redacted); reviewer; rollback SHA; P0 test IDs; truthful final-send state.

**Submission rule:** Never submit merely because the user selected Automatic. Final send needs separate current-case authorization; uncertain post-send state is UNKNOWN, must be reconciled and must not be blindly repeated.

## 5. Dispatch rules and daily progress

At every user-requested implementation continuation: (1) verify current source PRs and running artifact; (2) execute the highest unblocked P0 item; (3) land the smallest complete patch; (4) run actual CI and fix failures; (5) release if fully approved; (6) post SOURCE/CI/DEPLOYED/USER_VERIFIED separately and update P0 matrix. If an independent approval, real employer session, user consent or production operator is missing, mark that **exact** gate blocked and advance a parallel qualifying slice without claiming release.

Each progress receipt must include: **what became usable, where in the public UI, tested SHA/CI, real-user test result, blocker owner and next executable step**. Do not issue generic "continue implementation" status replies unsupported by work.

**No background promise:** This schedule does not create an autonomous worker, scheduled CI or standing task in ChatGPT. Activity occurs through explicit ongoing operators/agents/CI or future authorized requests, not simply because this file exists.

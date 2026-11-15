# SmartPloy V4 — binding execution: one profile → complete job application

**Directive SP-V4-ONE-PROFILE-APPLY-001 · 13 November 2026**  
**Authority:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` §§1,4–7,9–12,14, FEATURE-FIRST-001, REA-FIRST-001. This is a release-sized **implementation order**, not a replacement blueprint.

## Single user outcome (next code push, NOT postponed)

**The user supplies a truthful application profile once.** From that profile and the selected live job, SmartPloy prepares a job-specific, editable CV and cover letter and their genuine PDFs/DOCX; fills previously approved safe form data; attaches the **current exact approved CV and letter PDFs** to corresponding real employer upload fields; reuses normal employer answers when the question matches exactly; **prompts only for questions/requirements that are missing, changed, ambiguous or legally consequential**. It records observed progress and confirmation truthfully. Never silently resubmit or fabricate applicant data, document upload acknowledgments or employer acceptance.

The **next production-facing change must be this integrated path**, not another independent palette/sidebar/card/dropdown release. No competing application executor.

## Mandatory click path / acceptance

1. **Profile once:** account-scoped existing candidate facts + a signed-in “Application answers · save once” editor. Updates replace the earlier version. Unapproved or conflicting values are never transferred; sensitive/visa/EEO/pay/legal answers stay manual and profile answers are not inserted into job matching, CV evidence or AI prompts.
2. **One selected vacancy:** reuse existing exact-owner workspace and canonical employer job fingerprint. Application CV/letter are prepared through the existing `new_workspace`, existing approved-fact letter composer and the existing revisioned edit/export flow. Draft text is NEVER a reviewed document until deliberately saved.
3. **Every document prepared:** reuse `render_document` to produce four current files (CV PDF/DOCX, letter PDF/DOCX), downloadable as one owner-scoped ZIP. Both PDF SHA-256 fingerprints and byte lengths are bound to the short-lived reviewed browser packet.
4. **One Start AutoApply preparation action:** on a supported exact Lever/Ashby/hosted Greenhouse page, reuse existing `planFields` and signed-in review; read exact current PDFs from the separate first-party SmartPloy tab without persisting applicant files or requiring the user to reselect local PDFs. Check both hashes before transfer. Explicit one-time employer upload consent, then inject only into unique matching real CV and cover-letter file inputs. If the employer has a letter TEXT field and no separate file field, fill existing approved letter text. Check settled values and visible employer upload indicators; local FileList assignment alone is not server receipt.
5. **Answer memory / change detection:** only exact normalized ordinary question labels use once-approved profile answers. A new or modified question, newly restricted option, changed label/URL, disabled/hidden field or duplicate value stops and asks the applicant. No fuzzy guessing of protected or legal answers. Reusing an old answer still requires the existing user fill approval.
6. **Actual submission gate:** where the current approved V4 policy permits a final employer action, preserve independent exact-job employer permission, explicit fresh applicant review, one-use server claim, no retry and reference-bearing receipt reconciliation. Do not describe a browser click as confirmed. Ordinary unsupported ATS and CAPTCHA require an explicit user handoff, not fake completeness.
7. **Release:** run first-party Python tests, Node browser-companion tests, web type/build tests, real Chromium fixture tests, independent exact-head security review; then merge to `main` and deploy exact-SHA with rollback evidence. Complete at least one **owner-authorized real supported employer form to review** with the CV and any needed cover-letter attachment, one unchanged saved question and one new/changed prompt. Observe signed-in desktop/mobile and durable case state. Mark `LIVE_VERIFIED` only from those observations.

### Provenance and change control

**Source donor:** https://github.com/galapoto/smartploy at verified production/main commit `4bae2f79d11f3412df003ba1af3876b1dbf4a414`, original `smartploy/profile.py`, `browser_handoff.py`, `application_workspace.py::new_workspace,render_document`, `api.py`, `web/src/App.tsx`, `ApplicationStudio.tsx`, `api.ts`, `types.ts`, `browser-companion/logic.mjs`, `upload.mjs`, `page-attachment.mjs`, `popup.mjs`, `questions.mjs` and original tests. Reuse existing licensed/owned source first. No external donor code imported in this run.

- **COPIED unchanged:** none. The code was read and existing components adapted in place.
- **ADAPTED/INTEGRATED:** existing profile storage, owner-scoped job workspace, document rendering, exact job packet, Chrome inspected/fill/upload adapters and manual review.
- **NEW:** `smartploy/profile_application_answers.py`, `browser-companion/page-document-fetch.mjs`, regression tests, owner-scoped four-document archive endpoint and an answer-memory UI.
- **SANITIZED:** exact host and workspace checks, strict PDF hashes, single first-party `https://smartploy.komplyint.fi/*` extension host permission, memory-only PDF transfer with no browser extension storage of raw documents, fail-closed sensitive answers.
- **REA:** not used; exact owned source is available, REA reconstruction would introduce unnecessary uncertainty. **Savings:** not measured; never invent percentages.
- **Controlled permission change:** v0.6.0 Chrome extension needs explicit access to the fixed first-party SmartPloy origin to retrieve the user's documents. No wildcard employer host permission, external analytics, bearer token export, automatic user impersonation or hidden submit.

### Acceptance ledger

- **SOURCE/COMMITTED:** feature branch `feat/v4-profile-once-complete-application-20261113`; exact PR SHA recorded in GitHub.
- **CI:** pending until exact-head results are reported.
- **INDEPENDENT REVIEW:** request and record source findings; do not count advisory COMMENTED as formal APPROVE.
- **DEPLOYED_MAIN / ONLINE_EVIDENCE:** pending. Existing deployed baseline stays `4bae2f7` until this integrated change qualifies.
- **REAL ATS FORM-TO-REVIEW / EMPLOYER RECEIPT:** not verified from source-only tests. Do not mark complete from synthetic fixtures.
- **Scope limits:** not every employer offers a dedicated letter upload; nonstandard multi-step controls, CAPTCHA and consent cannot be guessed. Record exact action needed; never silently downgrade to “applied.”

## Next run exit condition

The next implementation/release run must focus on this *same integrated PR*, fix the exact CI/review failures and move it to a demonstrable real employer form. Do not switch to unrelated features or another paper. Every action must have a source SHA, reproducible check, owner-visible effect and truthful PASS/FAIL/NOT VERIFIED status.

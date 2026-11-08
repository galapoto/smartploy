# SP129 — port exact reviewed CV PDF attachment into current AutoApply path

**Status: SOURCE ONLY until exact-head CI, independent review, approved main merge, authorized deployment and real signed-in browser verification. No employer application sent.**

## Acceptance outcome

After user selects one exact job in Jobs, reviews the CV/letter, connects their own visible Playwright helper, inspects a supported current ATS form and fills reviewed ordinary fields, a **separate, explicit "Attach exact saved CV PDF once"** action appears only when a single unambiguous visible PDF-compatible résumé field is present. It re-downloads the saved exact revision from same-origin owner-scoped SmartPloy, checks size, %PDF header, %%EOF and SHA-256 against the signed-in applicant's reviewed packet, rechecks account/current draft and reserved employer-attempt ledger, asks for consent and sends the PDF bytes to the applicant's own 127.0.0.1 bridge via authenticated CORS with no cookies. Bridge checks same current packet, SHA, CV field identity, ATS URL and one-use ID; burns the one local attempt before calling the existing Playwright set_input_files. **No employer submit, no claim of employer upload acceptance, and no retry after uncertainty.** The candidate can finish manually.

## Real source provenance (no external source introduced)

- **PORT / SANITIZE / INTEGRATE**: `galapoto/smartploy`, PR #278 immutable source commit `0f9513b4aece9567fa437b3eb7bdae0d2fe849bf`: `browser-playwright/assistant.py` functions `choose_cv_attachment`, `validate_reviewed_cv_pdf`, `attach_reviewed_cv_pdf`, plus observed field `accept,multiple` (copied first-party functions); `browser-playwright/bridge.py` single-use HTTP endpoint and state (ported first-party file); `web/src/localPlaywrightBridge.ts` two original SHA/size-checked transport functions (ported first-party file); `web/src/LocalPlaywrightAssist.tsx` explicit approval UI (first-party port).
- **PRESERVED from NEWER code**: `galapoto/smartploy@6c49b6b8116c4a92ecde1cb9c18e9d86ff11894e` (PR #317) `browser-playwright/assistant.py` SP144 settled field read-back, `web/src/LocalPlaywrightAssist.tsx` one-use employer attempt ledger and partial-fill uncertainty.
- **PREVIOUS DONOR OF DONOR (not newly copied)**: original first-party `browser-companion/upload.mjs` and `browser-companion/page-attachment.mjs` exact-file matching and bytes-check logic; original ObumAI `obumai/obumellm@d682da2582ebfa3f013cf37dc542384fe605f303` `obumellm/browser/fill.py` and `browser/live_session.py` for visible Playwright, adopted in SP110. No new unlicensed external source and no new browser engine.
- **COPIED unchanged external: none.** Transplanted from first-party prior PR #278; behavior revalidated in this PR. REA_NOT_APPLICABLE for complete accessible source; do not claim behavior extraction.

## Scope and policy

Binding authority: V4 production-first contract §§1, 4, 5, 6, 7, 9; `AGENTS.md` REA-FIRST-001 and FEATURE-FIRST-001. Same approved ATS subset as SP110 (Lever, Ashby, Greenhouse); unsupported sites require manual action rather than a false success. Filename is a benign fixed PDF name; no CV bytes stored in the bridge. A local input FileList change can immediately cause an employer upload; applicant must acknowledge before pressing the action. Native extension attachment already exists independently and is not replaced.

Test evidence **pending actual CI run**. Real public employer acceptance **NOT VERIFIED**. The production web revision was `cee0017091e5` at last public inspection; do not state this source branch has been released. Any optional feature remains on review hold until exact commit is approved, merged to main, deployed with the existing authorized script and checked under signed-in same-account browser acceptance.

## SP129.1 — sanitation against reactive employer upload clearing

The SP112 donor previously treated Playwright `set_input_files` returning without an exception as proof of a local attachment. This was insufficient when a reactive employer page cleared/replaced its FileList on change. **SANITIZED** the adapted `assistant.attach_reviewed_cv_pdf` with the already proven SP144 single settled observation (150ms), same URL/field identity, exact FileList name, MIME and byte size. If the field was cleared, no `attached_locally` success is returned; the existing bridge burns the one attempt and requires manual inspection. Added a real synthetic Chromium regression for employer-side async clearing. Not proof of server-side file acceptance and never an employer submit.

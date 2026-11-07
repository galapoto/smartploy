# SP112 — Attach the exact reviewed CV PDF with ObumAI Playwright

Date: 2026-11-02. Scope: **Assisted**, applicant-controlled attachment on a
single reviewed job. Branch:
`feature/sp112-playwright-reviewed-cv-attach-20261102`, PR #278, based
on PR #277. SP112 does not add an unattended employer-submit engine.

## Actual reuse (no second browser engine)

- ObumAI first-party browser workflow `obumai/obumellm`, pinned in SP110
  to `d682da2582ebfa3f013cf37dc542384fe605f303`:
  existing visible persistent Playwright Chromium context and verified
  `page.locator` pattern in `browser-playwright/assistant.py`.
- SmartPloy original `browser-companion/upload.mjs`
  `chooseResumeField`, `validatePdf`, and
  `browser-companion/page-attachment.mjs` exact-field identity / safe
  PDF rules: ported narrowly into the same Python helper as
  `choose_cv_attachment`, `validate_reviewed_cv_pdf` and
  `attach_reviewed_cv_pdf`. Original MV3 extension unchanged.
- SmartPloy current `smartploy/application_workspace.py`
  `render_document` (PDF rendered with invariant=1), private
  revision-locked `applicationDownloadUrl`, and owner-reviewed
  `smartploy/browser_handoff.py` 15-minute packet with size,
  digest, revision, job and approved fields. **No new PDF writer.**
- Existing `bridge.py` one-use local pairing, strict Host/CORS,
  DNS-rebinding boundary and applicant-private ephemeral Chromium profile;
  SP112 adds only an explicit binary-PDF endpoint and applicant approval.

## Applicant-visible workflow

1. Sign into SmartPloy, prepare and save the job-specific CV and cover
   letter, select Assisted, then prepare a local no-clipboard handoff.
2. Run `python bridge.py` once on the applicant's own desktop, pair it
   in SmartPloy using the temporary code, and inspect the exact supported
   Lever/Ashby/Greenhouse form. Login/MFA remains manual.
3. When the local helper finds exactly ONE visible, empty, enabled
   PDF-compatible résumé input, SmartPloy offers
   **Attach exact saved CV PDF once**. Applicant confirms separately
   that the employer may upload immediately when its file field changes.
4. SmartPloy's existing owner-scoped private PDF GET retrieves exactly the
   saved CV revision on the **same first-party origin**. The browser
   verifies SHA-256, length (≤2 MiB), PDF header/trailer and the original
   reviewed workspace identity. A second authenticated owner/revision
   verification precedes transfer.
5. PDF bytes go to the **local** helper at
   `http://127.0.0.1:48741/v1/attach`, with no cookies, no redirects,
   no logs, no external intermediary, no user file-path disclosure.
   The helper independently verifies exact SHA/size, job URL, original
   employer form DOM and one-use attachment plan, burns the attempt
   BEFORE using Playwright `set_input_files` to populate the input.
6. SmartPloy reports **file placed locally; employer receipt NOT verified;
   application NOT submitted**. The applicant personally verifies upload,
   completes sensitive questions and legal consent, and chooses whether
   to press the employer's own Submit button. Failed or timed-out local
   actions are never blindly retried; manual attachment remains available.

This is a *separately approved PII transmission to an employer page*,
not a background task. The employer's own JavaScript may transfer PDF
bytes immediately on field change. No server-side or browser automatic
final submit, employer-account login, CAPTCHA/MFA bypass, or rights
expansion. The original Chrome extension remains a viable alternative.
If no unique supported résumé field is found, no attachment action
is offered and the applicant attaches manually.

## Safety and test evidence

- Read-only inspection includes expected file type, name, id, label,
  accept and multiple attributes. Exactly one stable résumé/cv input
  must exist. Hidden, disabled, readonly, prefilled, multiple, ambiguous,
  duplicate and non-PDF inputs are blocked. The upload call repeats
  exact original URL, all inspected field identities and PDF hash checks.
- Local HTTP rejects unauthorized origins and Host headers; binary
  transfer requires the original memory-only session bearer, exact
  one-use attachment ID, explicit `ATTACH REVIEWED CV`, short-lived
  packet and exact declared Content-Length (12 bytes – 2 MiB).
  The frontend targets `loopback` and origin-only CSP.
- No CV file saved to disk by the bridge; Playwright attaches the
  in-memory `{name,mimeType,buffer}` file object.
- Negative/replay tests: `tests/test_playwright_local_bridge.py`
  exercises bad code, wrong upload ID, malicious origin, wrong SHA/size,
  expired review, provider uncertainty, and no second attachment.
- Real Chromium tests: `tests/test_playwright_assistant_chromium.py`
  attaches a synthetic PDF to the one résumé input, never touches cover
  letter or Submit, blocks mutated DOM/invalid files, and blocks any
  external synthetic employer request.
- Vitest: `web/src/LocalPlaywrightAssist.test.tsx` exercises real
  existing CV download URL, separate consent, frontend digest checking,
  localhost-only transfer, one-use action, no employer submit.
- Existing SP111 Web, Docker/ZIP/CSP and native release gates remain
  in force. Synthetic browser or Compose evidence is **not** live
  consenting-employer acceptance.

## REA-FIRST and release gates

REA remains **BLOCKED**: on the current coding host the official REA
CLI/MCP was unavailable and npm acquisition failed DNS; original
owner-readable first-party sources were reused directly instead of
inventing a scratch automation engine. No REA reproduction trace is
claimed. Saved effort: **unmeasured**.

**NOT DEPLOYED.** PR #278 must pass exact-head GitHub CI and independent
privacy/security review, then await sequential reviews/merges
#275 → #276 → #277 → #278. Native Woodpecker/ObumDelivery proof,
post-merge exact-main CI, independently approved operator SHA,
backup/rollback and signed-in actual-applicant and consenting-employer
acceptance are still required before any production status claim.

# SP107 — Preview the exact saved CV and letter PDFs before final applicant review

**Date:** 2026-11-02. **Source baseline:** `575b827e1511161c8c9f4857baca759e775895c1`, already tested in SP106 PR #273. Proposed independent review sequence: #270 → #271 → #272 → #273 → SP107. This source-only change is not a merge or deployment.

## User journey

Manual, Assisted and Automatic applications already have complete, owner-private job-specific CV and letter editors, actual PDF and DOCX downloads and a combined ZIP export. However, a candidate checking the rendered PDF had to download it first; edited browser text can be different from a saved revision. SP107 places two explicit controls next to the ZIP download in **My applications**:

- **Preview CV PDF** and **Preview letter PDF** open the original first-party rendered, saved PDF in a separate tab, without updating anything.
- Neither link is navigable when CV/letter edits are unsaved, when a save is running, or when the selected workspace lacks download authority. The UI explains that the link shows *only the saved revision*.
- URLs include both exact owner-private workspace ID and `expected_revision`. The server returns **409** rather than silently substituting a newer saved revision after a concurrent change. The user must refresh, review and choose again.
- The route returns **inline application/pdf** for a browser PDF viewer, with a normal downloaded-file fallback controlled by the user's browser; opening it is never employer permission, an ATS submission, an AI call or a stored review intent.
- Previously acknowledged jobs may still be previewed for the owner's records; edit/send protections remain separate.

## Server security and reuse

The preview endpoint uses `tenant_context(request)` plus the owner-scoped `workspace_repository.get(profile_id, workspace_id)` and reuses `render_document(kind, pdf)`, the same renderer used for individual downloads and SP106 ZIP. No new document rendering, upload, external provider or dependency. Missing or cross-owner workspace is **404**. Invalid kind is **404**, invalid/missing expected revision **422**, and mismatched revision **409**. Error paths disclose no private document text.

Response defenses: `Cache-Control: private, no-store`, `Pragma: no-cache`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`, `X-Frame-Options: DENY`, `Cross-Origin-Resource-Policy: same-origin`, `Referrer-Policy: no-referrer`, and `Content-Disposition: inline` with the same sanitized first-party PDF filename. Frontend links use `target=_blank` with `rel=noopener noreferrer`. No PDF content or applicant details are copied into localStorage, clipboard, logs or new JS state.

## REA-FIRST-001 decision

`REA_NOT_APPLICABLE`: the original complete PDF renderer, owner/session authentication, reference-bound navigation and UI disabling design are owned first-party, readable and directly reusable. No permitted comparable opaque executable, binary, third-party app or recording to recover. Exact baseline SHA recorded above. No new dependencies. Engineering savings unknown (no timed baseline).

## Acceptance and remaining gates

1. FastAPI tests inspect full real PDF text for the current saved CV and letter, inline headers, owner-missing 404, invalid kind 404, missing/stale revision refusal, no submission counts, no mutations and no external employer activity.
2. Vitest checks exact revision URL, private, accessible new-tab links, disabled preview while dirty and refresh after revision save, and same-email account switch isolation.
3. Chromium synthetic acceptance checks click creates an exact owner/revision preview request and does not increment the application's revision or trigger employer APIs. Chromium's built-in PDF viewer, accessibility and file fallback may vary by browser; users can still download PDFs.
4. Full backend/real PostgreSQL synthetic E2E, frontend/build, browser and Compose exact-SHA CI, exact-checkout *review* receipt. No source CI check counts as production approval.

Independent reviewer sign-off, merged-main CI, native ObumDelivery exact-SHA evidence where mandated, real two-owner signed-in acceptance and operator-approved OVH deployment with backup/rollback and running frontend/API SHA parity remain mandatory. No live employer submission or actual production release is claimed.

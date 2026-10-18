# SmartPloy Apply Companion — manual, approval-gated Lever applications

This is a minimal Chrome/Chromium Manifest V3 browser extension, **not a
background bot**. Its release implements the first browser-side part of
SmartPloy's application workflow without employer API credentials. It does not
read the user's stored passwords, browsing history, or other tabs.

## Current support

- The exact Lever job and application URL under
  `https://jobs.lever.co/{employer}/{job-id}` or
  `https://jobs.eu.lever.co/{employer}/{job-id}`.
- English, Finnish and Swedish labels for ordinary name/contact text inputs,
  LinkedIn/GitHub URLs and a reviewed cover-letter text field.
- Only explicitly approved contact details copied from SmartPloy, tied to the
  exact job, document digest, revision, and a **15-minute expiry**.
- Optional **explicitly user-approved PDF attachment** to one unique visible Lever résumé input.
  The user selects a trusted local PDF up to 2 MiB and approves the exact file/employer.
  Filename/type, PDF header/trailer, SHA-256 in transit and fresh form identity
  are checked; the selected file must also match the **SHA-256 and size of the
  exact deterministic SmartPloy CV PDF export** in the v2 packet. This does not
  upload silently or submit the application.
- One optional final-submit button click **after** the user has completed
  file upload, mandatory questions and privacy/CAPTCHA requirements, rechecked
  the same employer tab and explicitly approved the single attempt.
- A local opaque SHA-256 attempt reservation prevents silent re-submission
  after ambiguous errors. It records no CV, contact values or employer tokens.
- A read-only check for a *visible* confirmation phrase **plus**
  confirmation/reference ID after the action.

**Not supported:** LinkedIn account takeover/scraping, Workday/Greenhouse
automated final-submit, password-protected forms, employer OAuth bypass,
CAPTCHA-solving, security challenge bypass, unattended résumé attachment,
automatic agreement to privacy terms, answers to unknown questions,
recurring/automatic application submission, or any service-scheduled
browser execution.

The owner may still apply manually on any employer website through the
job's original posting link, using the downloaded CV and letter.

## Load the companion on the applicant's computer

1. After the reviewed SmartPloy PR is merged and tested, obtain the repository
   locally with `git clone https://github.com/galapoto/smartploy.git`
   or download the source from your own repository account.
2. In Chrome/Chromium navigate to `chrome://extensions` and enable
   **Developer mode**.
3. Click **Load unpacked**, choose `smartploy/browser-companion`.
4. Pin **SmartPloy Apply Companion** to the toolbar.
5. Confirm it requests only `activeTab`, `scripting`, and `storage`.
   It must never ask for broad browsing-history permissions or password access.

This is an unpacked first-party extension; it is **not yet Chrome Web Store
published**, code signed, or security-audited for public distribution.
A code review and real browser QA are required before general deployment.

## Prepare each application

1. Sign in to `https://smartploy.obumai.com`.
2. In CV & profile, approve **one full name, one email address** and,
   optionally, phone and the social-profile URLs. Check that your job-specific
   cover letter has no placeholders.
3. Under Find jobs, open a verified current position and choose
   **Prepare documents**.
4. Review and save the CV and letter, then download the PDF/DOCX.
5. In Application Studio, read any handoff blockers. Click
   **Copy approved autofill packet**, confirm the transfer. The packet is
   copied to your clipboard and expires after 15 minutes. The original CV
   file is **not** copied into it.
6. Open the **same exact Lever posting** in a new browser tab and use its
   Apply link to open the matching `/apply` form.
7. Open the pinned extension, paste the packet, click
   **Inspect employer form** and review exactly which fields will be filled.
8. Click **Fill approved fields (no submit)**. Inspect every inserted value.
   Select your reviewed SmartPloy CV PDF in the companion and click
   **Approve and attach PDF (no submit)**, after confirming the file and target
   employer. The employer site may transmit immediately upon file attachment.
   Alternatively attach manually on the employer site. Answer required questions,
   accept terms only after reading them, and complete MFA/CAPTCHA yourself.
9. Click **Check required fields**. The companion will enable **Submit this
   application once** only if a unique Lever final-submit button is detected,
   required fields are complete, a labeled résumé input has a file, and the owner checks
   the per-job consent box.
10. Only if you intend to send this specific application to the employer,
    click the final button and confirm the OS/browser confirmation prompt.
    **An attempted click is not proof of successful submission.**
11. Check the employer response. If the extension popup closes when
    Lever navigates after submission, **reopen it, paste the SAME packet** and
    select **Check confirmation after a previous attempt**. The companion
    checks its existing non-sensitive one-use attempt marker and the exact
    Lever employer account before inspecting the confirmation page.
    Never click Submit again merely because the popup closed.
    A strong confirmation requires a visible reference ID and a confirmation
    phrase. Otherwise the result remains **unverified**.
12. When the companion observes a reference-bearing confirmation, it
    offers **Copy observed receipt**. This contains the receipt reference,
    sanitized same-employer URL, page-text SHA-256, original reviewed
    document revision and observation timestamp, never the raw page text or
    CV. Copy it into SmartPloy **My applications → Import observed receipt**.
13. SmartPloy verifies the owner draft, exact saved revision, document hash,
    employer host, account, reference format and recent observation timestamp.
    It saves an immutable per-user record marked **browser-observed but
    NOT independently employer-verified**.
14. If desired, separately record a self-reported application after seeing
    your confirmation. The existing `actually_submitted` metric remains
    reserved for independently verified employer evidence. An observed
    browser page does not increase that count.

## Security and implementation boundaries

- No backend can push a submit order to the companion.
- No background script/content script runs on unrelated websites.
  `chrome.scripting.executeScript` is invoked only on a user-clicked active
  tab after validating an exact HTTPS Lever host, employer, job path and
  unexpired document packet.
- Source descriptions are not instructions; they cannot grant authority.
- The fill plan excludes passwords, files, checkbox/radio answers, select
  fields, salary, unknown required fields and company/employer identity.
- PDF attachment is never automatic or unattended: a user must choose a local
  file and approve the exact target. The extension never stores the PDF bytes,
  filename or its SHA-256 in persistent storage. Employer page handlers may
  upload immediately when the file input changes. Only **local attachment** is
  observed; no employer server acceptance is inferred.
- Only one visible, empty, uniquely labeled résumé input is supported. Hidden,
  ambiguous, prefilled, non-PDF or multiple-file inputs remain manual.
- PDF header/trailer/filename/type checks are not malware scanning.
- The version 2 packet binds both the approved CV+letter text revision and the
  exact deterministic downloaded CV PDF's SHA-256/size. The companion refuses
  a selected file that differs from those bytes. The user still must inspect
  its contents, since hashes do not prove qualifications or employer acceptance.
- Applicant must read consent statements and answer employer-specific questions.
- Final click performs a last independent page-state check. An opaque
  attempt marker is stored **before** the click, so a crash does not cause
  a duplicate retry.
- Page DOM parsing uses no `eval`, `innerHTML`, or hidden requests.
  Visible text output uses `textContent`; data lives only in the popup
  until it closes. The clipboard is a sensitive ephemeral channel: never
  paste packets into logs, GitHub, chats, or unknown websites.
- A confirmation inferred from the page is **observed**, not guaranteed
  cryptographic employer evidence. A receipt should include a specific
  job/application reference and ideally a confirmation email.
- Stop use if employer terms, accessibility, anti-bot notices or security
  challenges disallow automated field entry.

## Tests before production claiming

```bash
node --check browser-companion/logic.mjs
node --check browser-companion/popup.mjs
node --check browser-companion/upload.mjs
node --check browser-companion/page-attachment.mjs
node --test browser-companion/tests/*.test.mjs
# plus synthetic Chromium fixture in web/browser-tests/lever-upload.e2e.ts
pytest -q tests/test_browser_handoff.py
```

All tests use local fixtures and **never submit a real application**. The
final acceptance still requires a user-signed-in SmartPloy browser, the
locally installed extension, and a permitted live employer form observed
and approved by the applicant. Do not label the workflow fully
operational until those checks and genuine receipt evidence pass.

## Export fingerprint and version boundary

This release upgrades the ephemeral browser handoff to
**smartploy.browser_handoff.v2**. Old packets are not accepted; copy a fresh
one from the matching reviewed SmartPloy revision. PDF generation uses an
invariant ReportLab output to reproduce identical bytes across downloads.
Do not regenerate or edit the PDF after copying the packet. Changes require
saving the revised CV and issuing a new handoff. DOCX remains for manual use;
the automated attachment in this iteration supports only the bound PDF.

## Limitations and evidence

This is still a **review-first** companion, not unattended AutoApply. The new
attachment uses the user's own PDF and an explicitly approved extension action.
A web application may hide its file input, replace the form or reject the chosen
PDF; in these cases the companion fails closed and the user must attach manually.
Synthetic Chromium cases demonstrate DOM assignment, not a real employer-side
attachment receipt. Before production claiming, a permitted live employer form
and authorized user must complete a real application, and evidence must be
independently recorded. No live submission is performed by project CI.

## Rollback

Remove or disable the extension in `chrome://extensions`. The browser
extension has no server-side worker. SmartPloy's existing manual document
preparation works unchanged. Disabling or uninstalling the extension stops
new form actions immediately.

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
- One optional final-submit button click **after** the user has completed
  file upload, mandatory questions and privacy/CAPTCHA requirements, rechecked
  the same employer tab and explicitly approved the single attempt.
- A local opaque SHA-256 attempt reservation prevents silent re-submission
  after ambiguous errors. It records no CV, contact values or employer tokens.
- A read-only check for a *visible* confirmation phrase **plus**
  confirmation/reference ID after the action.

**Not supported:** LinkedIn account takeover/scraping, Workday/Greenhouse
automated final-submit, password-protected forms, employer OAuth bypass,
CAPTCHA-solving, security challenge bypass, automatic résumé attachment,
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
   Manually choose and upload your reviewed CV from your computer, answer
   mandatory questions, accept terms only after reading them and complete
   any MFA/CAPTCHA.
9. Click **Check required fields**. The companion will enable **Submit this
   application once** only if a unique Lever final-submit button is detected,
   required fields are complete, some file is attached, and the owner checks
   the per-job consent box.
10. Only if you intend to send this specific application to the employer,
    click the final button and confirm the OS/browser confirmation prompt.
    **An attempted click is not proof of successful submission.**
11. Check the employer response. Use **Check visible confirmation** to
    inspect a visible reference number and confirmation phrase. If there is
    no strong confirmation, treat the outcome as **unverified** and never
    repeat the submit click automatically.
12. In SmartPloy **My applications**, record a self-reported employer
    application only after seeing a genuine confirmation. Copy the employer
    reference into the field. SmartPloy's existing counter
    `actually_submitted` remains reserved for independently verified
    employer evidence.

## Security and implementation boundaries

- No backend can push a submit order to the companion.
- No background script/content script runs on unrelated websites.
  `chrome.scripting.executeScript` is invoked only on a user-clicked active
  tab after validating an exact HTTPS Lever host, employer, job path and
  unexpired document packet.
- Source descriptions are not instructions; they cannot grant authority.
- The fill plan excludes passwords, files, checkbox/radio answers, select
  fields, salary, unknown required fields and company/employer identity.
- File upload is not automatic. Applicant must read consent statements.
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
node --test browser-companion/tests/logic.test.mjs
pytest -q tests/test_browser_handoff.py
```

All tests use local fixtures and **never submit a real application**. The
final acceptance still requires a user-signed-in SmartPloy browser, the
locally installed extension, and a permitted live employer form observed
and approved by the applicant. Do not label the workflow fully
operational until those checks and genuine receipt evidence pass.

## Rollback

Remove or disable the extension in `chrome://extensions`. The browser
extension has no server-side worker. SmartPloy's existing manual document
preparation works unchanged. Disabling or uninstalling the extension stops
new form actions immediately.

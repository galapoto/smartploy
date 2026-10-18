# SmartPloy Apply Companion — reviewed Lever form assistance

> **SP15d REVIEW-VERIFICATION BRIDGE, DRAFT ONLY (18 Oct 2026):** The automated final
> application click is intentionally disabled until a signed-in, owner-scoped
> server claim can be consumed atomically across separate browsers and devices.
> No local checkbox, popup preflight or old packet is a substitute. The companion
> can still assist with reviewed fields, permitted local PDF attachment and
> human-only employer submission. This document supersedes older descriptions
> below that referred to a one-popup final click.

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
- **No automatic final-submit click in SP15b.** The employer must be submitted
  manually by the applicant on the real employer page until the authenticated
  cross-device server claim and browser redemption protocol is security reviewed.
- The previous browser-profile attempt key and Web Locks helper are retained
  solely for old-attempt observation and future audited reuse. **They are no
  longer used to click Submit.** The separate PostgreSQL employer ledger tracks
  owner + actual Lever employer/job across devices and source URL variants, but
  a read-only server status is **not a final-click grant**. New packets are
  refused after a server reservation and applicants must reconcile uncertain
  outcomes. No raw CV/contact data is stored in the claim ledger.
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
6. Back on the signed-in SmartPloy tab, use **Record exact CV and job review
   (no submit)** and confirm. The owner-scoped review lasts at most ten minutes.
   While staying on that SmartPloy tab, open the pinned Chrome extension, paste
   the same packet, and click **Verify review on signed-in SmartPloy**.
   This runs a same-origin, credentialed first-party check against the saved
   current job, CV PDF, letter and approved contact field fingerprints.
   It does not create a final-click token.
7. Open the **same exact Lever posting** in a new browser tab and use its
   Apply link to open the matching `/apply` form. Reopen the pinned extension,
   paste the SAME packet, click **Inspect verified employer form (no submit)**,
   and review which fields will be filled. The temporary review fingerprint
   expires after at most five minutes; repeat signed-in verification if it
   has expired. This is a separate user gesture, not unattended automation.
8. Click **Fill approved fields (no submit)**. Inspect every inserted value.
   Select your reviewed SmartPloy CV PDF in the companion and click
   **Approve and attach PDF (no submit)**, after confirming the file and target
   employer. The employer site may transmit immediately upon file attachment.
   Alternatively attach manually on the employer site. Answer required questions,
   accept terms only after reading them, and complete MFA/CAPTCHA yourself.
9. Click **Check required fields**. Resolve all outstanding field and PDF
   requirements. The companion's automatic Submit button remains disabled;
   checking a box never supplies cross-device authorization.
10. If you decide to apply, click the actual **Submit application** button on
    the employer website yourself. This is outside SmartPloy's automated
    submission flow. Inspect the result before deciding on any next step.
11. Save any genuine employer confirmation email/reference. Do **not** retry
    an uncertain application. If a prior release of the companion had already
    reserved a local attempt, **Check confirmation after a previous attempt**
    may still inspect that earlier employer page. A current manual submission
    does not generate a new SmartPloy companion attempt marker.
12. For a prior eligible browser-observed confirmation only, the companion
    may offer **Copy observed receipt** with a reference and page fingerprint.
    Import this in **My applications → Import observed receipt**. For a new
    manual application, use SmartPloy's **I applied on employer site** flow.
13. SmartPloy keeps browser-observed evidence and applicant self-reports
    distinct from independently employer-verified acceptance. Neither is
    cryptographic or authoritative proof the employer received an application.
14. The existing `actually_submitted` metric remains reserved for
    independently verified employer evidence; no local click or page text
    increments it.

## Review employer-specific questions (SP14)

After filling the approved contact fields, choose **Review unanswered questions**.
The companion lists only required, empty, ordinary text/textarea questions
eligible for your own answer. Type or paste a *truthful, personally reviewed*
answer (including a checked draft from ObumAI), then choose **Approve and
fill reviewed answers (no submit)** and confirm the transfer. The employer
website may transmit answers when the input/change events fire, even though
the companion does not submit an application.

Salary, immigration, work authorization, EEO, gender, legally protected
personal information, privacy/consent, signature, criminal/background and
other sensitive questions stay manual. So do select, radio, checkbox,
file, password, hidden and ambiguous controls. A reactive form that moves
fields mid-fill stops the assistant; re-inspect before trying to finish.
No answer is saved in browser extension storage. Review the actual employer
form before preflight. Actual employer submission is manual until secure cross-device authorization is integrated.
## SP15b authenticated attempt status

The **Application Studio** now reads a server-authenticated, tenant-owned
POSTGRESQL employer claim status at
`GET /api/v1/application-workspaces/{workspace_id}/employer-attempt`.
This endpoint is **OIDC-cookie-only**, no CORS credential forwarding, no write,
and no source/email/claim ID in its response. Unavailable persistence returns
503 rather than pretending the account has never tried this employer job.

If a prior claim exists for this applicant's actual Lever organisation/job,
the handoff readiness and future packet generation are blocked until operator/
human reconciliation. The web UI disables another packet and shows uncertainty.
Assisted field filling and PDF attachment on the employer site now require
verification of the current packet on the signed-in SmartPloy tab first.
Historical receipt inspection is still available; no automated final-click
path exists in this branch.

**Next necessary work:** security-reviewed, per-job employer permission source,
signed-in same-origin final user intent, an opaque one-use authorization
delivered without exposing any account bearer token to employer DOM or
clipboard, atomic server consumption by the existing MV3 companion, and
two-device synthetic browser acceptance. No live employer actions in this patch.

## SP15d first-party review verification: reused secure transport

The same existing user-clicked Chrome MV3 popup briefly runs a
first-party-only script on exactly the HTTPS SmartPloy tab, after verifying the
tab URL. It fetches the user's OIDC-bound first-party session and sends
only document, CV PDF, employer URL and approved-contact-field **hashes**,
PDF size and revision to the same-origin verify-reviewed-packet API.
The server recomputes each value from its canonical saved workspace, approved
profile, live job and 10-minute review record under the existing PostgreSQL
owner/workspace/job locks. The site login cookie and account ID **never leave
the first-party webpage**; the injected function returns only boolean status,
expiry and explicit non-authority flags.

The extension retains a **non-bearer SHA-256 fingerprint and maximum five-minute
expiry** in chrome.storage.session, which is ephemeral and not available to
the employer page. Every assisted field fill, PDF attachment and ordinary
answer fill rechecks the fingerprint. No secret or raw CV is persisted.
This is a security gate for *assisted form preparation*, **not** an employer
submission lease. Its state is a point-in-time observation: cancelling a
review or switching accounts after verification cannot revoke an already
recorded local fingerprint immediately. It MUST NEVER be relied upon as
current consent for a final-click operation. The future final-action flow
must redeem a server-held one-shot claim atomically immediately before a
click, with proven employer automation rights and a separate last-minute
owner action.

The Chrome extension uses only its original activeTab/scripting/storage
permissions, with no permanent host permissions, content scripts, service
worker or long-lived browser authority. Local synthetic Chromium tests and
Node contract tests validate request isolation and denying forged packets,
but **signed-in physical Chrome extension installation and production
ObumDelivery native CI are still unverified**.

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
- **Automatic final click remains disabled.** An older Chrome-profile
  attempt marker may still be inspected, but is never an executable server
  authorization or employer receipt. No automatic retries are available.
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

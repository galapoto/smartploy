# SP13 — Lever PDF attachment reuse, completeness and safety check

**Date:** 18 October 2026. **Status:** implementation proposed in review branch only.  
**Approved strategy:** [reuse-first master plan PR #150](https://github.com/galapoto/smartploy/pull/150).  
**Base:** existing [SmartPloy integrated draft #149](https://github.com/galapoto/smartploy/pull/149), source SHA ca56d17a06741f5d8f61b7370391abed1373cba9.

## Why this feature, and why it is an augmentation

The existing SmartPloy Chromium companion already validates a short-lived applicant packet, confines its field actions to one HTTPS Lever posting, fills approved contact/letter fields, reserves final submission once, and saves a browser-observed but explicitly unverified receipt. ObumAI already has application drafting, evidence, live Playwright session and final-action preflight code. Replacing that with a different external bot would duplicate work.

The **missing specific capability** was putting an applicant-selected CV file into the genuine browser form while retaining explicit document-transfer consent. We added a narrow, first-party bridge rather than a new model, a new browser agent, a second resume library, a new application database or unapproved website automation.

## Code systems checked before writing

| Source and pinned snapshot | Actual functionality examined | Decision |
|---|---|---|
| SmartPloy first-party browser-companion/logic.mjs and popup.mjs at ca56d17a | Packet expiry, exact job, owner-reviewed fields, final-submit one-time reservation, receipt inspection | **Reuse unchanged foundations**, extend their popup |
| SmartPloy smartploy/browser_handoff.py and smartploy/application_workspace.py at ca56d17a | Approved CV/letter text fingerprint, exported PDF and DOCX | Keep existing renderer. No new CV builder. Selected PDF **not yet cryptographically bound** to the packet's text digest |
| ObumAI obumellm application and browser modules, inspected main 2026-10-18 | Evidence vault, form mapping, browser session, final preflight, local **staged-only** file upload | Keep these behind ObumAI typed API; **not a functioning live file upload to copy** |
| [ApplyAI Lever detector, d4a97b](https://github.com/muhammad-saadd/applyai/blob/d4a97b5643aa219592883a43b068fc18dff94678/content_scripts/lever.js) | MIT. Form labels/fields and page selectors | Compared; no third-party browser package introduced. Its default use of OpenAI would require consent and egress review |
| [Yaima Lever/Ashby/Greenhouse workflow, e5061bc](https://github.com/Yaima/agent-apply/blob/e5061bc0455ea61b75b59edbe73296ab5bbe03ca/agent/forms/apply.py) | MIT. Blocking login/CAPTCHA, human final approval, fallback | Keep SmartPloy’s already-implemented one-click review boundary; do not duplicate the Python runner |
| [career-ops ATS autofill, 9e4326b](https://github.com/career-ops-hq/career-ops/blob/9e4326b35a8ee716081b9169f44e83d232a99289/docs/APPLY_AUTOFILL.md) | MIT. Lever captcha/checkbox exclusions and form-specific changes | Follow its conservative stop rules. It expressly never auto-submits |
| [neonwatty policy, 370204c](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job_apply_policy.py) | MIT. Campaign limits, claims, replay, no hidden authority | Retain native SmartPloy one-attempt reservation. Evaluate its campaign pattern for later standing-approval work, **not this feature** |

**License and provenance:** This feature imports no external source files. It relies on SmartPloy's existing first-party code and standard Web File, DataTransfer, SubtleCrypto and extension APIs. External MIT sources were inspected to avoid duplicated capability and to decide negative-case behavior; they were not pasted as modules. No code from missing-license, GPL, AGPL, Commons Clause or no-commercial-use repositories was modified to evade licensing.

## Specific safety and completeness checks

1. Scope remains **user-clicked activeTab only**, with no Chrome host permissions, background process or content script auto-injection.
2. Revalidate the same 15-minute packet, exact Lever employer and job ID, actual /apply form, current active browser tab, existing one-time attempt reservation and selected PDF before any data leaves the extension.
3. Reject unknown, hidden, multiple, prefilled, changed or unsupported upload inputs. Never attach to an unrelated cover-letter, photo or passport field.
4. Owner chooses one reviewed PDF <= 2 MiB; check filename, MIME, leading PDF signature, terminal EOF marker and full SHA-256 over bytes before transfer and again in the tab. **Not a malware scanner** or CV truth attestation.
5. Show a second confirmation with company, position, filename, byte count and digest; explain that employer-side JavaScript may begin uploading immediately after input/change events.
6. Do not store bytes, filename or hash persistently. Do not call fetch, submit, CAPTCHA solver, credentials, third-party AI or other site.
7. Submission remains separately authorized once; preflight must see a file in a **labeled résumé field** rather than an arbitrary file upload. A browser page success remains **browser-observed**, never independently employer-verified.
8. Synthetic Chromium and Node tests must cover valid/invalid file, changed domain/job, form drift, hidden/occupied inputs, no submit click, no outside network, and failure states. Plus Python source contract checks.
9. Do not merge or deploy until security/license review and exact-commit CI acceptance. Testing mock HTML proves browser behavior only, not an employer API accepting bytes.
10. **Implemented improvement:** Stable PDF output uses ReportLab's invariant mode, and the user-selected PDF must match the exact rendered CV SHA-256 and byte count from the v2 short-lived handoff. This still does not prove that the employer accepted the upload or permit unattended submission.

## Verifiable delivery states

- **Source proposed:** feature code is in this branch and review PR only.
- **CI:** must be rerun on exact feature SHA; a historical success on another commit does not validate this patch.
- **ObumDelivery:** independent worker run not claimed.
- **Production:** existing OVH checkout and website remain unchanged.
- **Real applicant:** no applicant data uploaded or sent; no employer application submitted.
- **Future expansion:** document-binary fingerprint integration, user-approved conditional questions, additional allowed ATS providers and durable per-user queue; reuse evaluated first, not wholesale imports.

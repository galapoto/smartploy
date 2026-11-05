# SP114 — Reuse Chrome employer question review in local Playwright

**Date:** 2026-11-02. **Branch:** `feature/sp114-playwright-review-questions-20261102`.
Depends on SP113 PR #279, plus #275 → #276 → #277 → #278.
**Not merged or deployed. No automatic employer submission.**

## Reuse-first architecture

The original SmartPloy Chrome companion already implements sophisticated,
tested employer-question classification and reviewed answer filling:

- `browser-companion/logic.mjs` — identifyField; prevents filling ordinary
  contact answers into salary, visa, GDPR and unrelated controls;
- `browser-companion/questions.mjs` — planReviewedQuestions and
  validateReviewedAnswers. At most 12 uniquely labelled required, empty
  text/textarea questions; salaries, citizenship, work rights, consent,
  protected traits, dates, radio/select/file controls and duplicates stay
  manual. No inferred or model-generated claims;
- `browser-companion/page-questions.mjs` — fillReviewedAnswers
  checks exact Lever/Ashby/Greenhouse application URL, form input identity,
  stable label/id/name/maxlength, dynamic form changes and unique
  questions; uses original browser native setter/input/change;
- `browser-companion/popup.mjs` — inspectForm extracts the original
  full form including textarea/select with visibility/required flags.

SP114's `reviewed_questions_script` **recompiles these exact four
first-party sources at build time** into one deterministic, self-contained
`questions-review.js` ZIP asset. It removes only ESM `export`/the one
original `identifyField` import, scopes the originals in independent
closures to avoid helper name conflicts, and adds the minimal Playwright
operation dispatcher. It uses the **same SP110 ObumAI first-party visible
Chromium**, the existing SmartPloy applicant-private localhost helper and
the owner-reviewed v2 handoff packet; no second browser agent or form
policy is added. The entire original source is tested for byte parity.
No REA execution or cost savings are claimed.

## User experience and behavior

1. After opening the exact employer form and optionally filling reviewed
   contact fields, press **Review unanswered employer questions**.
   This is read-only and does not transfer private applicant answers.
2. SmartPloy shows eligible unanswered required text questions and a
   separate **Answer personally on the employer website** list for
   legal/EEO/visa/salary and other fields requiring manual decisions.
3. The applicant **writes the answers themselves**, accurately and
   truthfully; no AI-generated guesses. They may leave a question empty
   for manual handling.
4. Press **Fill my reviewed answers once (never submit)** and approve
   the separate explicit warning that employer input/change events may
   transmit these answers immediately. The local helper rechecks the
   original packet, exact job, DOM/plan and original Chrome restrictions.
   It burns the single attempt BEFORE modifying any employer field.
5. If the site changes or partially accepts answers, report only a
   bounded non-PII result, leave remaining fields for manual completion
   and NEVER retry blindly. Applicant reviews the real employer form
   and personally presses Submit if they choose. SP113 then optionally
   observes a visible reference-bearing confirmation as unverified.

## Privacy/safety

- Uses one signed-in applicant's short-lived packet, exact owner/workspace
  revision and non-reserved employer attempt check prior to action.
- Local HTTP remains `127.0.0.1:48741`, exact Origin and Host,
  memory-only token, JSON request body ≤32 KiB, no cookies, no PII logs,
  no server-side employer/browser actions, CAPTCHA/MFA bypass or consent.
- Original question planner returns only labels and field metadata;
  values remain in temporary local app state until explicit user click.
  The only answer transfer is to the applicant's localhost helper and
  then to their visible reviewed employer input after separate approval.
- Only one one-use fill per application. On browser/network uncertainty,
  fail closed, no automatic repeat. Existing Chrome companion remains.
- Read-only receipt observer (SP113) and server-backed manual receipts
  unaffected; nothing marks an application employer-acknowledged.

## Test and release gates

`tests/test_playwright_assistant.py`: exact original module extraction
and deterministic ZIP parity; `tests/test_playwright_assistant_chromium.py`:
actual original Chrome question planner/answer filler in synthetic real
Chromium against required ordinary, protected, changed and wrong-job
fields; `tests/test_playwright_local_bridge.py`: bearer, Origin, job
review, expired v2 packet, one-use and uncertain-outcome HTTP contract;
`web/src/LocalPlaywrightAssist.test.tsx`: applicant-written answers,
separate consent, manual-sensitive labels, reserved employer claim gate.

**RELEASE HOLD:** independent privacy/security review, exact current-head
GitHub and native CI, approval/merges in dependency order #275 → #276 →
#277 → #278 → #279 → #280, immutable operator-deployed backed-up OVH
release with rollback and signed-in consenting employer pilot.
REA official CLI is unavailable here; first-party source reuse is
direct and parity tested, with `savings=unmeasured`.

# SP121 — One reviewed Chrome extension for custom public employer sites

**Release candidate:** first-party reusable Chrome MV3 Apply Companion 0.7.0. Companion
reuses applicant-approved SmartPloy packet, short-lived same-account review, one
visible browser tab and the existing DOM safety/field/question/PDF primitives.
Not a Web Store install, unattended bot or automatic universal submission.

## Owner request / acceptance
User needs CV → Manual/Assisted/Automatic → find or privately add any job →
Start application → reviewed job CV + cover letter → **one obvious next action**
→ Playwright on desktop OR same browser's companion → ordinary safe fields,
reviewed optional ordinary questions, and exact CV PDF attachment →
applicant manually resolves login, complex controls, consents and final submit.

SP120 delivered the job/search continuation and generic first-party Playwright
forms (same user and public HTTPS hostname). SP121 closes the mismatch where
the Chrome companion only accepted hosted Lever, Ashby, Greenhouse, and
TalentAdore and where TalentAdore's injected question/PDF functions still
refused that ATS.

## Reused / minimally extended
- `browser-companion/logic.mjs` packet schema, immutable review, approved fields,
  field classifier and no-auto-submit flags — **not a second engine**.
- `browser-companion/upload.mjs` public hostname normalization, exact ATS URL
  matching, CV field choice, SHA-256/PDF format and max 2 MiB.
- `browser-companion/popup.mjs` one-user-click activeTab, scoped injection,
  same-tab URL recheck, review digest and final-action separation.
- Original standalone `page-attachment.mjs` and `page-questions.mjs` now
  recognize exact TalentAdore forms plus public HTTPS user-reviewed *same
  hostname* forms. They are self-contained because Chrome serializes the
  functions; duplicated URL checks are deliberately tested for parity.
- `web/scripts/package_companion.py` is unchanged: exact allowlisted
  ZIP, no persistent host permissions, no background script or remote code.
- The paired local `browser-playwright/bridge.py` continues as the alternative
  for users preferring a separate visible Playwright browser.

## Non-negotiable controls
1. Generic site is chosen by the applicant in an exact reviewed SmartPloy
   workspace, not scraped or silently upgraded to a verified ATS provider.
2. The URL must be public HTTPS hostname with a nonempty path or query,
   no credentials, fragments, reserved/private suffix, IP literal, unusual
   port or cross-host redirect. Known ATS hosts retain their exact job paths.
3. Form is inspected by an applicant click and same tab/URL checked again
   immediately before fill. Any cross-host redirect, cross-origin iframe,
   changed form, ambiguous or sensitive field requires manual assistance.
4. Contact/cover-letter fields are matched conservatively; no empty required
   immigration, salary, EEO, consent, legal, identity or security questions
   guessed or checked. Answers supplied by the user are separately approved.
5. PDF bytes must match the reviewed per-job digest, be at most 2 MiB, be
   rechecked against the unique visible résumé input, and be attached only
   after a separate explicit applicant confirmation. The employer may
   upload on the browser change event; never claim an employer receipt.
6. The companion's automatic final browser submit remains Lever-only with
   independent employer authorization, verified signed-in review, and a
   one-attempt claim. **Generic sites and TalentAdore can never use this final
   action**. Applicants use the visible employer Submit button themselves.
7. Nonstandard, iframe-only, MFA/CAPTCHA and custom controls are not claimed
   to be filled automatically. A change of employer hostname needs a new
   applicant-reviewed link/packet.
8. The known-provider confirmation observer is not extended generically;
   unknown sites and TalentAdore use applicant self-report plus employer
   confirmation email. No false submitted status.

## Verification
- Node unit regressions: public HTTPS same-host versus cross-host/IP/port/
  username/ATS path; no final-submit rights; privacy/packet scope unchanged.
- Real Chromium intercepted synthetic custom-employer DOM: ordinary fields,
  deterministic reviewed PDF + question fills, wrong host blocked, no submit.
  Real Chromium intercepted synthetic TalentAdore form: PDF fix.
- Existing backend Python/PostgreSQL, React/Vitest, Chrome and Python
  Playwright CI, isolated Compose + exact source inventory.
- Release QA: independent security/privacy review, protected main merge,
  product owner Director GO, ObumDelivery/Woodpecker, immutable production
  deployment and two-user signed-in OIDC acceptance.
- Real employer data or applicant CV is **never included in CI**. Signed-in
  TalentAdore or arbitrary-host employer form behavior remains UNVERIFIED until
  allowed live QA is recorded.

## Public UI
The companion ZIP is available through **My applications → Download Chrome
companion ZIP** only after the code is deployed. Desktop Chrome/Chromium users
extract ZIP and use `chrome://extensions` → Developer mode → Load unpacked.
While on signed-in SmartPloy, paste reviewed packet and Verify review; open
the same exact employer host/form and use Inspect → Fill reviewed fields.
For the separately installed Python bridge use **Start application with
Playwright**, pair loopback code, inspect and fill. Both stop before final submit.

## Reuse/REA accounting
First-party SmartPloy/ObumAI-source functionality reused; no new external
binary acquired and no vendor source copied. Official morluto/rea CLI remains
REA_BLOCKED in this execution environment. Savings UNKNOWN; do not claim
verified REA outputs.

**Status:** source release candidate only; no production login or employer
submission asserted. CI receipt is not Director/independent authorization.

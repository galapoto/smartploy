# SP118 — TalentAdore reviewed application automation, HOK-Elanto Junior Analyst

**Public job:** Duunitori listing `20690122`, HOK-Elanto Junior Analyst (Helsinki), advertised 29 October 2026, deadline **15 November 2026**.
**Exact, tracking-free employer form:** `https://ats.talentadore.com/apply/junior-analyst/m6rpoy`.
**Source base:** SP117 draft PR #283, commit `abc120740c3967ae504afd5803b7c597571dbd8e`.
**Status:** source candidate with synthetic browser acceptance; **NOT deployed and NOT a real employer submission**.

## Applicant experience
1. Sign in and open CV-first Manual / Assisted / Automatic. For this employer the supported mode is **Assisted**; choosing Automatic cannot grant TalentAdore final-submit rights.
2. Save this vacancy as a private job using the exact tracking-free TalentAdore link (not the Duunitori link and not a URL containing `?source=duunitori`). Keep HOK-Elanto, Junior Analyst, location Helsinki and the *real* employer advert text.
3. Upload/review the real applicant CV, approve owned profile name/email/contact facts, save the tailored CV and Finnish cover letter with a new revision. The reviewed handoff is bound to the owner, exact document SHA/PDF and 15-minute expiry.
4. In My applications, select **Prepare Playwright handoff**. Pair the existing first-party, localhost-only visible browser helper. It opens the exact TalentAdore posting. Click the site's **Hae tähän työpaikkaan** (start application) yourself and inspect the now-visible form. If the employer shows a custom or changing layout, SmartPloy fails closed instead of guessing.
5. Review the list of uniquely matched *ordinary* Finnish/English/Swedish contact fields and explicitly approve **Fill reviewed fields once**. The original ObumAI-derived Playwright locator revalidates DOM identity before each write. Employer pages can transmit inputs immediately.
6. Separately approve the original revision-locked, SHA-checked PDF attachment only if exactly one visible unfilled PDF-compatible CV input is discovered. This employer may upload on file-change; no retry after uncertain outcomes.
7. Review unanswered ordinary questions in the already reused Chrome question classifier. Safe, directly observed prompts can be remembered in the SP116 private profile only when the applicant chose Guided mode. Truthful answers require separate user approval. Salary, immigration/work rights, EEO, legal/GDPR consent, protected data, conditional/custom selections and CAPTCHA/MFA remain manual.
8. The applicant **personally** reviews the whole employer form, clicks final Submit on TalentAdore and checks the employer confirmation email. SP118 does **not** recognize TalentAdore confirmation pages; it must never call them provider-acknowledged receipts. If the user submitted, use the original manual self-report in SmartPloy.

## Source reused, not replaced
- Original `smartploy/browser_handoff.py` owner/revision review, packet and PDF digest.
- `browser-playwright/assistant.py` reuses ObumAI `locator.fill` executor, strict form identity, first-party Chrome questions and exact CV upload policy.
- `browser-playwright/bridge.py` uses applicant-local `127.0.0.1` session and explicit pairing.
- `browser-companion/logic.mjs`, `upload.mjs`, `popup.mjs` add only exact TalentAdore hosted URL/form scope; **no** Chrome host permissions or broader domains.
- `web/src/ApplicationStudio.tsx` and `browser-playwright/INSTALL.txt` explain site-specific limitations.
- All existing Lever, Ashby, Greenhouse partner and employer-rights boundaries remain unchanged. TalentAdore is **reviewed form assistance only**, not an approved submission API.

## Automated evidence and limits
- Python negative tests: exact host, slug+id, port, fragment, query, duplicate/wrong-job, stale revision, owner review and no submit grant.
- Original Chrome JS negative tests: exact URL matching, rejected cross-job queries/hosts, final click denied.
- Real Playwright Chromium **synthetic employer**: navigates the exact HOK-Elanto URL **intercepted entirely in memory**. Forms use test-only names/email and mock HTML, never a real applicant or employer request. It fills ordinary labels, leaves salary, visa and GDPR unchecked, attaches only the fake digest-checked CV PDF and asserts Submit count remains zero. A second test injects a conditional field and verifies fill stops after DOM drift.
- Browser evidence screenshot (if CI passes) is at `web/browser-evidence/sp118-talentadore-synthetic.png` in the GitHub Actions synthetic browser artifact; **not** a screenshot of the live employer form.
- Real TalentAdore form field names, customized employer questions, CV upload control and login behavior are **not independently verified**. Do not extrapolate synthetic success to real submission.
- No real applicant CV, phone, email, credentials, residence details or employer application were uploaded to GitHub. No production credentials or actual browser navigation executed during this source change.

## REA and release safety
REA_BLOCKED: official REA CLI is unavailable here. Only original readable, first-party owned source was adapted; no new browser engine or external code. Cost/time savings unknown.
**Production HOLD:** exact-head synthetic CI, independent privacy/security review, approved dependency merge chain #281 → #282 → #283 → SP118, original native ObumDelivery/Woodpecker, Director GO, backed-up immutable production operator deployment, signed-in two-account checks and applicant-consenting **live TalentAdore acceptance** are all separate gates. Do not merge or deploy an incomplete candidate.
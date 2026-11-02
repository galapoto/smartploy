# SP120 — From private saved job to supervised Playwright application

**Status:** implementation review candidate; NOT merged, deployed or independently
verified against a real employer. All browser and identity fixtures synthetic.

## Original user failure and acceptance
User uploaded a CV, selected Assisted / Help fill supported forms, searched
"HOK-Elanto Junior Analyst" (no current source result), then manually saved the
vacancy, and could not proceed. Saving only bookmarked the vacancy; the
ApplicationJourney searched the public ATS database only.

A working Assisted path MUST offer:
1. Existing signed-in CV, Manual / Assisted / Automatic selection and readable
   application dashboard (unchanged).
2. When a vacancy is missing, "Add employer link & start Assisted"; and for
   existing user-saved vacancies, a distinct "Start application" button.
3. A confirmed owner-scoped POST creates/reuses a **private** job-specific
   CV and complete cover-letter workspace, jumps to My applications, and
   displays next actions. No shared source mutation, employer send, rank
   fabrication or source approval.
4. User checks CV, employer and letter, saves reviewed revision and approves
   one name/email fact. The existing explicit "Start application with
   Playwright" button prepares a 15-minute owner- and revision-locked packet
   in tab memory. A paired local helper opens visible Chromium, inspects
   ordinary contact fields, then a new explicit click fills them. A separate
   click can attach the exact reviewed PDF if the employer has a unique
   suitable input. Employer CAPTCHA, login, salary, work permit, GDPR/legal
   consent, complex dropdowns and final Submit remain visible human steps.
5. Unknown employer sites may be assisted through a public HTTPS address,
   even without independent employer API integration. The same-origin
   public-host policy rejects localhost, private/loopback literals,
   credentials, suspicious schemes, ports, fragments and reserved TLDs;
   different employer origins require a newly reviewed job URL. Known ATS
   hosts keep exact job ID/path checks. Generic form route can progress to
   a different path on the same reviewed hostname; applicant sees and
   inspects fields prior to one-use filling.
6. Final automated submission **not** granted to arbitrary sites. Standard
   local Playwright helper does not click Submit or repeat uncertain actions.
   After applicant submission, only genuine confirmation evidence should
   create any status; never call a saved draft "submitted".

## Source / REA
- Baseline: galapoto/smartploy cumulative SP118 commit
  `31bef0a7b4c4f94325b97b73a77f38f19b5bbb66` and the already
  existing first-party ObumAI-derived Playwright actor and local bridge.
- Reused: `private_saved_jobs.py` owner repository,
  `application_workspace.py` draft and PDF logic,
  `browser_handoff.py` reviewed packet and contact facts,
  `browser-playwright/assistant.py` DOM-review and fail-closed fills,
  `ApplicationStudio.tsx` and `LocalPlaywrightAssist.tsx` existing
  paired browser panels, `ApplicationJourney.tsx` CV matching,
  profile/OIDC and audited employer rights.
- Wrote: one owner-scoped private bookmark-to-kit API, one candidate
  resolver for applicant-owned kits, user-visible buttons and messaging,
  narrow public-domain generic assistance, additional regression tests.
- REA: `REA_BLOCKED`; authenticated morluto/rea CLI not available in this
  execution session. No claim of code or savings proven by REA; savings unknown.
- Tests: Python/real PostgreSQL, React/Vitest, synthetic Chromium with
  full intercepted network requests, two distinct account principals,
  source manifest checksum. **No live employer credentials or personal CV
  data are included in the source or tests.**

## Production and acceptance requirements
- Review generic employer policy, private DNS/redirect cases and
  browser startup threat model, normal accessibility and dark-mode contrast.
- Verify user-added link and imported source job paths converge into
  the SAME applicant-facing document/browser sequence.
- Confirm a persistent application after logout/login, two-user isolation,
  revision invalidation, change-in-tab and one-use upload protections.
- For an actual HOK-Elanto pilot: first-party OIDC signed-in applicant,
  exact TalentAdore job, real user-approved CV and name/email, real form
  opened with reviewed Playwright, confirmation from actual employer.
- Independent privacy/security review, protected main, native CI,
  Director exact-SHA GO and immutable backup/release evidence before
  public production deployment. **No employer application is sent by
  compiling or merging SP120.**

## Known prerequisite
A normal website cannot automatically spawn an arbitrary executable on
the applicant computer. The existing helper is downloaded and started
by the applicant once, and paired using a one-time code. Future
productized helper installation / one-click browser runner is a separate
platform task. Until paired, the application workflow must show the
reviewable next step, never pretend a browser session has started.

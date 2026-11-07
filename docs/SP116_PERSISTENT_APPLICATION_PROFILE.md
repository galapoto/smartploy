# SP116 — Persistent applicant profile and privacy-respecting CV-only mode

**Date:** 2026-11-02. **Base:** SP115 consolidated PR #281 (review-ready,
unmerged). **Branch:** `feature/sp116-durable-application-profile-20261102`.
**Stage:** implementation/CI candidate — not production deployed.
**Owner goal:** the applicant's SmartPloy profile accumulates relevant
details during applications so subsequent forms require less repetition.

## Four parallel, non-conflicting implementation lanes

| Lane | Owner/source reused | Implemented behavior |
|---|---|---|
| A — private persistence/API | original per-tenant profile ID, FastAPI OIDC middleware, original Postgres migration runner, original workspace revision | `migrations/030_application_profile_questions.sql`, `smartploy/application_question_memory.py`, owner-bound GET/POST/PUT/DELETE API; exact question key, pending prompt, CAS reviewed answer, GDPR/visa/EEO/salary exclusion, no browser or employer rights |
| B — comprehensive profile and CV-only | existing approved `ProfileFact`, CV repository and private parser | standard applicant field taxonomy (contact, experience, education, skills, languages, portfolio, availability, preferences; salary, references, work rights remain manual-only), applicant-requested deterministic CV suggestions always unapproved; durable `guided` or `cv_only` mode |
| C — user experience and browser | existing CV-first `App.tsx`/Profile UI, existing SP114 original-Chrome policy and ObumAI Playwright | profile completeness card home/apply/profile, explicit CV-only warning, pending questions and re-usable answers, account-checked Playwright question observation and answer recall (exact question only), separate applicant confirmation before profile save and before one-shot local browser field change |
| D — privacy/QA/release | original PostgreSQL, API two-user OIDC tests, Vitest and Chromium acceptance, original immutable Git source gate | sensitive questions rejected by backend even if browser says eligible; same-email cross-user isolation, deletion, CAS, CV-only opt-out, employer-submit zero, read-only release HOLD |

### Normal applicant experience

1. Sign in. Upload/edit a CV and choose Manual, Assisted or Automatic
   as before; **profile completion is not required** to browse jobs,
   prepare private drafts or use Manual mode.
2. SmartPloy offers **Guided reusable profile** by default. The applicant
   can deliberately choose **Use CV only**, a PRIVATE PER-ACCOUNT setting
   persisted in PostgreSQL. SmartPloy warns that ordinary employer fields
   and legal forms may need more manual work and that provider-authorized
   AutoApply cannot be promised.
3. On Profile, review categories across contact, work experience,
   education, technologies, certifications, projects, languages, links,
   preferences and individually chosen manual-only categories. Approved
   career facts continue to use the existing original
   `smartploy_profile_facts` storage and owner-reviewed approval model.
4. Optionally press **Find reviewable facts in my CV**. The original
   stored private CV text is scanned locally on the SmartPloy server for
   explicit email/phone/HTTPS profile URLs and literal known skill tokens.
   No identity, qualifications, years of experience, salary, medical,
   immigration or criminal answer is inferred. Proposed facts are
   **unapproved**; the applicant checks/approves them individually.
   Repeated parsing does not demote or overwrite old approved facts.
5. During an **Assisted** application using the paired local Playwright
   flow, clicking **Review unanswered employer questions** reuses the
   original SmartPloy Chrome companion safe-question classifier. SmartPloy
   *also* posts those exact fields, with owner/user and current document
   revision, to its private API. The backend independently rejects all
   consequential/sensitive labels and identifies permitted prompts by
   normalized SHA-256 identity. New prompts persist as **needs answer**.
   This happens without applicant answers or any employer action.
6. Applicant can answer later under My CV & documents. Answers are
   permanently saved only after an explicit truthful review and with a
   version lock. Exact matching **approved reusable** answers appear as
   editable suggestions on subsequent forms, not as automatic sends.
   Job-specific questions remain manual-only. Any change requires new
   applicant confirmation before a one-shot local fill.
7. In CV-only mode, no new prompts or answers are persisted. The existing
   Manual/Assisted employer workflow remains; the applicant fills missing
   fields directly. Existing saved answers are not re-used.
8. Applicant can remove a question and its answer from their profile.
   The existing account-erasure inventory includes BOTH new owner tables.
   No claim of completed backup/provider erasure is made.

### Security and safe defaults

- New endpoints use the original first-party OIDC owner binding and
  expected user-id header, strict same-origin mutation policy and
  `Cache-Control: private, no-store`. No employer ATS request, real user
  session, external AI inference or browser write is initiated by
  profile APIs. All work remains inside existing first-party SmartPloy.
- New table stores only profile ID, safe normalized prompt, user-written
  answer, version, scope and timestamps. **No employer URLs, cookies,
  browser tabs, CV text, access tokens or captured form HTML are stored**
  in the question-memory table.
- The Chrome extension remains usable as previously tested but DOES NOT
  yet sync a newly observed question to the server directly. This
  release automates question capture through the **paired Playwright**
  assistant only. Never claim otherwise.
- A private profile answer does not grant employer automation permission,
  legal consent, job-fit verification or provider acknowledgment.
  Sensitive profile fact types are excluded from default generated AI
  evidence; sensitive employer form fields remain manual-only.
- The original single-use employer submit claims and separate
  application final-action approval are unchanged. **Full unattended
  final Apply/Submit is not implemented or authorized**.

## REA-FIRST-001 reuse record

**REA_BLOCKED:** official `morluto/rea` was researched in SP110, but
executable CLI/MCP remained unavailable in this environment. Instead
reused existing source `smartploy/profile.py`,
`smartploy/profile_storage.py`, `smartploy/api.py`,
`smartploy/application_workspace_storage.py`,
`browser-companion/questions.mjs`,
`web/src/LocalPlaywrightAssist.tsx`,
`web/src/App.tsx`, `web/src/api.ts`,
`smartploy/account_erasure.py`, and original OIDC/production-release
checks. New code is limited to the owner-private question table,
question repository and CV suggestion parser plus UI/tests. **Savings:
unknown**; no made-up REA trace or estimated speed multiplier.

## Exact release gate

**Production HOLD:** do not deploy branch/PR code or bypass original
`deploy/personal/scripts/deploy.sh`, `check-approved-source.sh`,
ObumDelivery/Woodpecker, independent privacy/security review, Director
GO, immutable postmerge `main` SHA, predeploy backup/rollback, OIDC
release-evidence.sh --online, complete signed-in UI check, profile
cross-user/erasure QA, browser source parity and real permitted applicant
acceptance. GitHub synthetic CI never proves live employer integration.
SP115 PR #281 and this SP116 PR are dependent; ensure one reviewed merge
route and never deploy incomplete branches.

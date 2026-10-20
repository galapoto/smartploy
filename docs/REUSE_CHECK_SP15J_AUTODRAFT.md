# SP15j — automated IT discovery to persistent, reviewable applications

## Actual product gap closed in source
Original SmartPloy polls current jobs through three independent source adapters
(Job Market Finland, Kuntarekry and configured authorized read-only ATS feeds),
then scores personalized matches, but preparation was one-job-at-a-time:
the candidate had to click **Prepare documents** for every job. ObumAI's
older bulk preparation worker was correctly disabled in production because
a global switch could not prove per-user data-processing consent.

**SP15j adds the missing safe end-to-end local connection**:
- A verified ZITADEL/OIDC user chooses personalized IT role targets in the
  existing onboarding and approves career facts or uploads a CV.
- On Find jobs or Settings, the user explicitly enables **Find IT jobs and
  prepare drafts automatically**. This saves a revocable, bounded per-account
  setting (minimum search alignment and maximum 1–10 new drafts per cycle).
- First scan runs immediately; the original continuous source worker keeps
  current permitted listings fresh and on a bounded cadence automatically
  scans ONLY consenting active accounts even with browser closed.
- Uses the ORIGINAL personalized search_jobs ranking and documented reasons,
  only the recommended lane, current listing, HTTPS employer link, no explicit
  preference mismatch, no seniority mismatch, and approved private CV/facts.
- Reuses ORIGINAL new_workspace deterministic approved-fact-only CV and
  cover-letter skeleton, and original owner-scoped unique create_or_get; no
  duplicate on repeated scans/devices. All documents remain private for
  individual applicant review. Public listing match is NOT qualification proof.
- Source API, approved search criteria and browser companion remain unchanged.
  NO AI-processing request, no Cloudflare/browser automation permission,
  no employer form interaction, no final Submit and no fake actual submissions.
  Official Lever partner application remains separately gated by the existing
  SP15f-i employer rights and explicit per-application final approval.

## Reuse audit performed BEFORE writing code
- **Direct reuse** of existing source polling, scheduler and concurrency:
  smartploy/worker_runtime.py original blob 8e2abf5da0,
  smartploy/worker_schedule.py e5353d1e6f,
  existing smartploy/sources.* adapters and canonical deduplication.
  No new scraping/browser agent, unsafe paid feed or job-site permissions.
- **Direct reuse** of complete private personalized preference matching:
  smartploy/search_preferences.py dd5a1ab3e3 (search_jobs/recommendations/
  mismatched_fields/reasons, never a verified job qualification score),
  smartploy/search_preference_storage.py 61c50a5cbd.
  No new scoring model or invented suitability number.
- **Direct reuse** of approved user-owned CV and applicant-specific docs:
  smartploy/application_workspace.py 049b4b82af (new_workspace, _cover_letter),
  smartploy/application_workspace_storage.py 804e736a06 (idempotent unique
  create_or_get), smartploy/cv_storage.py, smartploy/profile_storage.py,
  smartploy/identity.py 4be837ddfa. Never fabricate candidate facts.
- **Adapted in place** original FastAPI app with account-bound OIDC/CSRF,
  tenant_context and search-results routes (api.py original 863a2fbb87);
  original Application Studio/App.tsx c8a62b5250 and shared TS fetch helper
  web/src/api.ts 7228284a24; original worker/runtime Compose, erasure
  quarantine/owner tables and worker test suite.
- **Rejected unsafe reuse** of legacy auto-prepare ObumAI sender. That
  global operator toggle intentionally fails closed in production; it cannot
  become permission for all accounts. New local-only worker uses individual
  explicit enabled settings. No external open-source copied or license bypass.

## Genuinely new minimum missing code
- smartploy/autodraft.py: per-account settings repository, optimistic revision
  check, source alignment → review-only draft bridge, account/source/CV
  validity gates. PostgreSQL/memory stores share one contract.
- migrations/024_automatic_it_drafts.sql: owner-scoped revocable settings
  only; **no applicant CV, job text, tokens or employer credentials**.
- web/src/AutoDraftPanel.tsx: live signed-in switch + immediate scan + pause
  and open private drafts. No UI control that claims to send applications.
- New unit, PostgreSQL, authenticated API and React component tests.
  Original modules and deployment were adapted rather than rewritten.

## Required release acceptance
Exact-head GitHub CI must pass all Python/PostgreSQL, React, Chromium, Node,
Compose migrations/restore and immutable source checks; examine failed tests
and rerun final SHA. Native ObumDelivery exact-SHA plus deliberately RED
probe and owner-approved staging deployment still required. The public
website still cannot apply automatically until protected main/OVH and ZITADEL
release is verified. Per-user toggle is OFF by default and browser-assisted
employer final Submit stays disabled unless genuine independent rights,
approved posting/form, user final approval and provider receipt are proven.
No real user opt-in or employer application is recorded by these synthetic tests.

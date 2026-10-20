# SP15j — IT job discovery to private application drafts: reuse-first delivery proof

**Goal:** SmartPloy finds suitable IT jobs on its existing source polling
schedule and creates a small number of **local, account-owned** reviewed
application drafts, without needing a user to paste vacancy links. It does
NOT pretend to have sent these drafts to employers.

## Verified ORIGINAL code reused before adding orchestration

- `smartploy/worker_runtime.py` blob
  `8e2abf5da04cde58588d9e7506908b4fa5553596`: existing public
  source pollers (Job Market Finland, Kuntarekry and verified public ATS
  tenants), persistent `WorkerTaskSpec` registered into the existing
  lease-based `ContinuousWorker` scheduler. Kept source fetching intact.
- `smartploy/search_preferences.py` blob
  `dd5a1ab3e32452c2ca5e8c57820fd2e2b4173c42`: existing
  Finnish/English title equivalents, location, job-language, seniority,
  keyword scoring and current-posting filter; `search_jobs` reused
  unchanged for recommendations. A title-only overlap or keyword-only
  match is NOT automatically drafted.
- `smartploy/scoring.py` original deterministic
  `score_candidate` and APPROVED evidence fit scoring: not the
  self-declared search skills and not an LLM's guessed qualification.
  Explicit unmet mandatory requirements block automatic drafts.
- `smartploy/application_workspace.py` original blob
  `049b4b82afef494ea650dd710c01a7467ddb601c`, method
  `new_workspace`, original private CV repository and tenant-scoped
  original `PostgresWorkspaceRepository.create_or_get` blob
  `804e736a0662760fb1a77eb4856e6aef0b25f264`: current vacancy,
  original uploaded CV / approved profile facts, editable cover letter,
  stable per-owner canonical-job key and PostgreSQL ON CONFLICT duplicate
  protection. **No second CV composer, new ORM or parallel draft table**.
- Existing owner-specific `search_preference_storage.py` blob
  `61c50a5cbd315c5065e4f5bf8bad9239874bddad` persisted criteria
  in JSONB with revisions. Reused that table and strict session-scoped
  `tenant_context` and original React `runPrivateMutation` before/after
  account verification. No new permissions service or access token.
- Existing vetted `SearchSetup.tsx`, `SearchResultsPanel.tsx` and
  `App.tsx` used in place; continued general search without a CV.
- ObumAI per-job processing consent and SP15a-15i eventual employer
  submission are **left untouched**: automatically creating a draft is
  not consent for model processing or employer communication.

## New code only for the previously missing gap

- `smartploy/auto_draft_shortlist.py`: small deterministic orchestration.
  It requires explicit per-user opt-in, personalized target roles, approved
  career facts, title relevance, no explicit location/seniority mismatch,
  preference alignment >=70, approved factual fit >=60 with no known
  mandatory qualification gaps, and a current HTTPS employer link.
  It rechecks the original job record and original saved criteria
  immediately before using `new_workspace` and original idempotent
  `create_or_get`, with <=3 drafts/user/cycle. No calls to external AI,
  browser, ATS APIs or employers.
- Adapted original existing `SearchPreferences` and JSONB repository:
  `auto_draft_enabled` defaults FALSE, explicitly chosen by the user,
  cannot be set in General search or without targeted job titles.
  For production the worker queries only ACTIVE, non-quarantined,
  opted-in owner IDs (no emails) and uses PostgreSQL
  `SELECT ... FOR SHARE OF p,u` around each draft insert.
  A completed revision-based opt-out blocks later draft creation after
  the update commits, including an overlapping worker operation.
  No database migration or new private-PII table.
- Adapted existing worker scheduler with
  `application:auto-draft-shortlist` task, 600-second default; the
  task is local-only and respects individual user opt-in.
  The operator toggle is independent of the old unsafe global
  `SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED` remote ObumAI flag,
  which remains OFF in production. Compose enables only the safe
  local task after this source is approved for deployment.
- Adapted original same-origin private API with
  `POST /api/v1/auto-draft/prepare`: requires the actual verified
  account, expected-user precondition and origin/CSRF, returns only
  bounded counts and clearly states no employer or model actions.
- Adapted original Job Setup (one-click IT starter roles, optional
  checkbox), Search Results (prepare-now CTA) and existing application
  workspace tab. Existing React before/after account switch defense
  and general search remain intact.

## Safety and customer truth

This is local application PREPARATION, not end-to-end unattended
submission. No provider sends/CV transmission/captcha bypass/no
interview answers are authorized merely from search settings.
The configured sources must already work and show current valid jobs;
the user must sign in, approve career facts, opt in and inspect
CV/letter prior to any eligible employer's separate final consent.
A submitted application is recognized only via a genuine provider ACK,
as handled by existing SP15f–h partner workflow.

**Required release acceptance:** exact-head source CI with real
PostgreSQL and React plus original Chromium/Node/Compose run; native
ObumDelivery exact-SHA and deliberate negative run; release gates and
signed-in live domain; actual source feed and user opt-in test;
explicit employer rights on any real provider call. Do not report
production readiness from a GitHub PR.

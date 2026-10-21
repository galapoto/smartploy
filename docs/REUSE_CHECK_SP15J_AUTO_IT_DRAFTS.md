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
  The initial SP15j required no migration. SP15k adds only a non-PII
  last-scan timestamp to this existing table for fair scheduling.
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

## SP15k continuation — fair account scanning and failure isolation

**Observed core flaw:** Sorting enabled profiles by `updated_at` reselected
the same first 100 accounts each cycle, starving newer opted-in owners.
One invalid CV/profile also aborted the remaining scheduled accounts.

**REUSE FIRST:** Adapted SP16 draft PR #172's already-implemented
`last_run_at ASC NULLS FIRST` scheduling idea from its
`migrations/024_auto_shortlist.sql` (blob
`5bd86db2ba4bc7719780cb9d2d3cf9bc0dbf0e66`).
Did NOT copy its redundant opt-in settings table or rival matcher.
Kept existing SP15j JSONB opt-in/revision guard, PostgreSQL owner/erasure
filter, actual source pollers, `search_jobs`, `new_workspace`,
unique account+job workspace insertion, and original leased worker task.

**NEW GLUE:** Migration 024 adds one non-PII last-checked timestamp/index
to the existing preferences table. The queue sorts least recently checked
first, resets on every user criteria change and only marks a matching
opt-in revision (never a replaced/disabled revision). A failing user
scan is contained, subsequent users are attempted, and the scheduler
reports `degraded` with aggregate counts, no user IDs or CV details.
Added real PostgreSQL rotation/revocation and synthetic worker-failure
regressions. No new scraping, model, browser or employer submission engine.
No new external dependencies.

**Still blocked from production:** original signed-in/OIDC, native
ObumDelivery exact-SHA/negative test, external source readiness and
reviewed OVH deploy; final employer submissions remain independent.

## SP15k UI truth: app opt-in is not operator deployment

**REUSE FIRST:** The original `dashboard.worker.tasks` already exposes
the durable registered task ID, enablement and last_status; no new
status API or monitoring service was built. Added a derived status prop
to the existing `App` / `SearchResultsPanel`. Before this correction,
the form checkbox alone caused the UI to claim the app was checking
jobs in the background even when the independently-controlled worker
flag remained disabled.

**NEW GLUE:** Three honest user states: background task registered
(not a proof of completed runs), task degraded, or background not
confirmed. The existing explicit user-run button remains available.
Three Vitest cases cover all states and direct action wiring.
No user/job data sent outside SmartPloy and no invented employer receipts.

## SP15l — truly immediate first-run IT application preparation

**Observed UX/core gap:** Previous SP15j required a user to save their
opt-in setting and then separately discover/click "Find and prepare".
Unattended scheduling might be disabled for safety, so users could
enable automation without a single application draft being created.

**REUSE FIRST:** Reuses original `POST /api/v1/auto-draft/prepare`
and `prepareMyMatchingDrafts`, original `App.tsx`
`saveSearchPreferences` session/expected-account checks, original
`ApplicationStudio` for saved document review, and the original
opt-in revision. No new endpoint, worker, employer submitter, browser,
credential, model, or permission. This first scan is only triggered
after the server confirms the user's new explicit opted-in preference.

**NEW GLUE:** The existing Settings/first-use flow immediately runs
one consented private scan on the first transition OFF -> ON.
If drafts were saved, it opens the existing My Applications editor;
if approved facts are missing, it routes to the existing profile editor;
if no current safe matches exist, the Jobs panel remains available;
if the optional scan fails, the saved search preference is retained
and the user gets a retry direction, without exposing backend errors.
Before publishing any private counts or navigating, the existing
verified account is checked again. No browser-closed processing or
external submission is falsely implied.

**Tests:** Four React/Vitest first-use/account-switch/failed-scan
regressions on the actual App integration, not a stub duplicate UI.
Full exact-HEAD CI and live authenticated OVH acceptance still required.

## SP15m — avoid wasted drafts for expired or retargeted employer jobs

**Exact underlying code inspected before writing:** Original
`domain.JobRecord.deadline`, original `search_preferences._published_order`
ISO date handling, existing `browser_handoff._posting_url` HTTPS /
no-IP / credential policy, original `description_fingerprint`,
`PostgresJobRepository.get`, `auto_draft_guard`, `new_workspace`,
and the existing private job/workspace storage. These components remain
the engine; no duplicate scrapers, CV composers or submitters.

**Core defect fixed in product code:** An active source row may advertise
an expired deadline, and its apply URL, job title, location, or mandatory
requirements could change between initial candidate ranking and durable
workspace creation without changing the description fingerprint.

**New narrow glue:** `_deadline_open` keeps an absent deadline valid,
accepts an unexpired ISO/Finnish calendar date or timezone-explicit
ISO timestamp, and excludes malformed/ambiguous deadlines from *automatic*
drafts (still available for manual review). The existing URL safety check
now also rejects raw IPv4/IPv6 and local pseudo-hosts.
`_same_reviewable_posting` rechecks role, employer, job link, deadline,
location, languages, work mode, requirements, question/documents,
and fingerprint inside the original owner opt-out guard immediately
before the existing `create_or_get` write. A changed listing waits for
a later matching cycle rather than using stale eligibility.

**Scratch vs reused:** Three tiny first-party validators and local checks
are new; job ingestion, ranking, eligibility engine, persistence, native
PostgreSQL tests and browser handoff policy are reused. Added deterministic
Finnish/ISO date and current-deadline tests, private-IP link rejects, and
six post-ranking employer mutation regression cases. **Never claims a
provider application was submitted.** Release still requires ObumDelivery,
signed-in user acceptance and independent OVH deployment proof.


## SP15n — reject stale source snapshots before creating real-user drafts

**Problem proven from existing source code:** Original
`smartploy/storage.py` deliberately preserves `JobCandidate.source_current=True`
during public ATS polling failures. The original `poll_public_ats`
records a failing source in source health, but does *not* retire jobs
from the last successful snapshot. This is correct for general browsing
and recovery, yet unsafe as evidence that an employer is still
accepting applications. The last cache may be many days old.

**Reuse before writing:** Directly reused existing
`JobCandidate.last_verified_at` and `last_seen_at` source observation
timestamps (never `posted_at`), `merge_candidates`/
`PostgresJobRepository.upsert` refresh behavior, original same-account
`auto_draft_guard`, original Postgres `get` re-fetch and workspace
`create_or_get`. Reused `SourceHealth` and the five reviewed Finland
public ATS pilot as operator-controlled ingestion; **no new scraper**,
credential, provider adapter, LLM model, or source-access right.
Reused the existing `prepareMyMatchingDrafts` API, React
`SearchSetup` and signed-in `App` identity guard.

**New first-party glue:** Small `_recently_verified` validator rejects
missing, timezone-naive, invalid, future, and over-48-hour verification
timestamps. On initial ranking **and again inside the existing
revocable account guard after a database re-read**, stale candidates
cannot create private documents, even while `source_current=True`.
Response has only aggregate `stale_skipped` and
`needs_source_refresh`; no applicant identities or employer URLs.
UI now explains a source freshness blocker instead of claiming
a background scheduler definitely continues. If the user chooses
keyword-only personalization but enables auto drafting, the original
backend requires explicit target roles: UI now explains this **before**
the server save. Keyword-only search without drafting still works.

**New tests:** Original Python synthetic candidate timestamps now derive
from UTC current time to avoid a timebomb after 48 hours. Added fixed
clock validator boundaries, old-cache exclusion + successful fresh
poll recovery, and a changed-cache race inside the per-account
guard. Added one frontend test for keyword-only consent validation
and two actual App tests for stale-source first scan and direct
manual rescan.

**Security and release:** No employer POST, credential, browser action,
external AI call, CV forwarding, or claim that an application was
submitted. Deployment remains blocked pending live source ingestion,
OIDC, native ObumDelivery proof and OVH exact SHA validation.
The operator-controlled `config/finland_public_ats_pilot.json` and
`scripts/configure_finland_ats_pilot.py` existed already; this change
does **not** silently enable those source hosts.


## SP15o — reviewed-source-only AutoApply and reusable Finland feed activation

**Concrete core issue:** Before this change the auto-draft engine could draft
applications from an imported `manual-import` listing merely because its
`source_current` flag was true and its observation timestamp was recent.
That timestamp verifies only when SmartPloy saw *some input*, not that
the employer itself still advertised the vacancy. User-added job links
and unreviewed search/browser outputs may not be promoted into
unattended job preparation.

**Reused from original product, checked first:**
- `domain.SourcePolicy.normalized/allows` and
  `normalize_observation` attach independently stored
  `job.raw.source_class/source_mode`,
  `candidate.metadata.source_class/source_mode` and source IDs.
  The built-in eligible policies are those issued by
  `PublicATSAdapter.policy` (`direct_employer_ats/api`),
  `JobMarketFinlandAdapter.policy` (`national_job_market/api`)
  and `KuntarekryFeedAdapter.policy` (`public_sector_jobs/feed`).
- `domain.merge_candidates` deduplicates sources. Its merged metadata
  may come from the newer source while its longer job body comes from
  the older source. The auto-draft guard therefore requires both
  provenance copies to agree, the source ID set to match `job.source`,
  and *all* constituent source IDs to be approved provider families.
  A manual/unknown source merged with a valid ATS cannot borrow the
  ATS authority.
- Existing `job_repository.get`, exact role/requirements checks,
  recent-source verification and `auto_draft_guard` are still run
  **after ranking and inside the owner-scoped write guard**.
  The same original `new_workspace/create_or_get` generates documents.
- Existing five reviewed boards in
  `config/finland_public_ats_pilot.json`, the original
  `PublicATSAdapter/poll_public_ats`, Docker `COPY . /workspace`,
  and existing worker `SMARTPLOY_PUBLIC_ATS_SOURCES_FILE` config.
  Instead of creating another crawler or a new database table,
  a **new installation's example environment** sets that file path
  to `/workspace/config/finland_public_ats_pilot.json`.
  Existing private environment files are untouched, and no employer
  submission or external CV forwarding is enabled.

**New scratch code strictly limited to missing glue:**
`_approved_source_for_auto_draft`, the aggregate
`needs_trusted_source/unverified_source_skipped` result, frontend
first-use and manual-retry guidance, and the reviewed file path in
`deploy/personal/env.example`. No copied/unlicensed third-party
code, new SaaS dependencies, worker algorithm or employer POST.
This gate is stricter than accepting every manually discovered vacancy;
manually saved jobs remain available for user review and direct
human-selected document preparation.

**Tests added:** Known official/ATS provenance allowed; recent manual
and unreviewed sources rejected; merge of good+manual sources in both
orders rejected; mismatch between body/source metadata or source IDs
rejected; provenance changed between scoring and the final database
read rejected; frontend no-false-success messages; and a worker
integration test proving the sample profile registers **five existing
Finland sources plus only the local per-account draft task** without
OBUMAI/partner submission. Test runs are synthetic, not claims that
the five employer feeds were confirmed live on OVH.

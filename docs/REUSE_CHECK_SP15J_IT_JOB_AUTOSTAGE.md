# SP15j — automatically find strong IT job matches and create real drafts

**Status:** source implementation in a draft branch. GitHub CI must pass at
the final exact SHA. No employer submission, no paid CI, no new third-party
dependencies, no CV/PII sent to a recruiter or cloud model.

## User's core requirement

An applicant who has no particular job posting can ask SmartPloy to
**continually find IT jobs matching their chosen roles/locations/languages
and prepare the applications** instead of manually pasting links.
Employer application submission is another controlled step; merely liking
or matching a job must NOT authorize a final employer POST or browser click.

## Reuse-first survey before a line of implementation

- The existing source worker `smartploy/worker_runtime.py` ORIGINAL
  blob `8e2abf5da04cde58588d9e7506908b4fa5553596` already pulls
  public Job Market Finland, Kuntarekry and allowed public ATS feeds with
  an existing durable scheduler `smartploy/worker_schedule.py`
  blob `e5353d1e6faea95c8dd2a616fd35ebf3e53416a8`. **Reused
  this worker and its source entries**; NO new job scraper/provider.
- Existing per-user bilingual title/location/seniority preference matcher
  `smartploy/search_preferences.py` original `dd5a1ab3e32452c2ca5e8c57820fd2e2b4173c42`
  and original persisted `smartploy/search_preference_storage.py`
  `61c50a5cbd315c5065e4f5bf8bad9239874bddad` already
  provide precise opt-in account criteria, revision protection, and
  preference explanations. **Extended in place** with a strict default
  false `auto_stage_drafts` Boolean in existing JSON (no new table).
- Existing original `smartploy/scoring.py` verifies user-APPROVED
  skills against mandatory employer requirements, with evidence/gaps.
  Reuse it to reject stated mandatory gaps rather than assume
  search keyword matches prove that applicant qualifies.
- Existing `smartploy/cv_storage.py` and
  `smartploy/profile_storage.py` load only owner-scoped approved
  evidence. Existing `application_workspace.new_workspace` original
  blob `049b4b82afef494ea650dd710c01a7467ddb601c` drafts the
  CV and cover letter without AI or network. Its original PostgreSQL
  workspace repository `804e736a0662760fb1a77eb4856e6aef0b25f264`
  uses the exact (profile, job) unique key to survive concurrent
  runs without duplicating. **No duplicated document generators/CRM**.
- The original SP15a employer submit claim ledger is queried
  READ-ONLY before creating drafts. A previously reserved/uncertain or
  submitted canonical employer job cannot be resurrected as a draft
  by the worker. SP15h submitted status and official receipt are preserved.
- Existing first-party signed-in OIDC identity/account-bound
  `tenant_context` and `signed_in_employer_review` are reused for
  the on-demand click path, including exact Origin and expected stable
  user ID; no new credential service or authentication endpoints.

## Minimal new vs adapted functionality

**One new first-party code file:** `smartploy/auto_stage_matches.py`,
pure owner-scoped `stage_owner_matches` and a bounded PostgreSQL
`stage_matched_drafts_once` entry. It reuses `search_jobs`,
`score_candidate`, `new_workspace`, persisted owner prefs/CV,
existing employer claim table, and original workspace repository.
Maximum THREE newly created review drafts per owner per cycle; narrow
current-source + verified HTTPS target, >=60 search-preference score,
no stated preference mismatches, no unmet explicit mandatory
requirements, and owner approved CV evidence. Idempotent
profile+canonical job keys. Response aggregates only status/counts,
never CV, email or owner IDs. No AI, employer click or app transfer.

**Adapted existing originals:** search preference model/persistence
strict Boolean opt-in (false by default, forbidden in unprofiled
General mode), first-party POST `/api/v1/job-autopilot/stage`
for a signed-in applicant's immediate on-demand run, and a
production-worker task `application:stage-matched-drafts` only
when an explicit operator flag is true. Even the operator flag
cannot stage for any user unless that user's private persisted
preference is true. Worker metadata contains no applicant data.
Existing SearchSetup setting explicitly states *review-only drafts*
and no employer data transfer. Existing App presents a
"Find matches and prepare drafts now" button and opens the
original Application Studio; resumes the same account-bound
UI session checks and existing pipeline.

**Only new CI code:** tests/test_auto_stage_matches.py for
real workspace creation, exact source data, idempotency,
seniority/claimed-job/mandatory gaps/invalid links, no CV
invention, default opt-out, tenant isolation and actual
Postgres active-identity persisted opt-in. The old
search/worker/React test files are augmented in place
rather than replacing their fixture suites.

## Critical boundaries

- Source fetching was ALREADY scheduled; worker cadence and
  source-specific terms/permissions remain untouched.
- Search scores indicate **preference alignment, not qualification**;
  missing mandatory evidence is a reason to skip, not a licence
  to invent missing skills.
- Draft CV retains exact uploaded text or only user-approved
  profile facts. Local cover letters contain review placeholders.
  The applicant MUST read, edit and approve each document.
- The automatic staging flag and per-user selection do NOT permit
  ObumAI data dispatch, Lever API applications or employer browser
  final-click. Real official partner submissions still require
  independently reviewed employer API rights, separate signed-in
  final user confirmation, original sticky one-shot claim and
  provider application ID receipt. Unsupported ATS remain manual
  submit after guided autofill.
- Multiple worker machines use the ALREADY implemented leased
  scheduler and idempotent workspace creation. Deleted drafts
  can currently be recreated on future cycles while the user
  remains opted in, unless a permanent employer attempt exists.
  A **user-controlled dismiss/snooze state** is therefore the
  next needed product capability; don't promise it yet.
- This source PR is not deployment, nor proof of live job feeds,
  native ObumDelivery acceptance, actual CV data, live sign-in,
  actual employer application or job offer. Keep release hold.

## Rollout controls

The worker flag defaults to FALSE:
`SMARTPLOY_WORKER_MATCHED_DRAFTS_ENABLED=false`.
When the latest source is accepted, a release operator can enable
the existing worker setting after native CI and owner-approved
OVH rollback acceptance. The individual applicant can
independently opt in/out under Personalized Jobs settings.
The on-demand first-party POST also needs a genuine signed-in
ZITADEL OIDC session and live approved CV facts; the user
does not need to paste the particular job URLs.

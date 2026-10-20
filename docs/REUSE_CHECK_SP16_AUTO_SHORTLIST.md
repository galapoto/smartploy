# SP16 — reusable automatic IT-job discovery and local draft pipeline

## What becomes usable after release

SmartPloy's original continuous source pollers already discover employer
vacancies. The user explicitly enables private local auto-drafting after
configuring personalized IT job titles/locations, seniority and keywords.
The UI immediately runs one safe cycle, with a separate optional recurring
worker task. This uses the exact existing source-current jobs and the
existing search_jobs preference ranker; it excludes known mismatches, weak
overlap, under-threshold scores, retired and non-HTTPS jobs. Match scores are
preferences, NOT verified qualifications.

For each high-alignment job, the original approved career evidence and
original CV are used by the existing new_workspace CV/cover letter generator,
and persisted by the original PostgresWorkspaceRepository.create_or_get
(unique owner/profile+job). No draft is overwritten, a maximum per cycle is
enforced, and incomplete template language MUST be reviewed by the applicant.
The existing Application Studio, Lever partner permission, final applicant
gesture, sticky submission protection and provider receipts remain separate
from this local job-preparation cycle. Neither the LLM nor an employer site
is contacted. No false actually_submitted count.

## Reuse FIRST — exact inspected existing sources

- Original source pollers/worker_runtime.py blob 8e2abf5da0, lease-based
  worker_schedule.py blob e5353d1e6f, PostgresJobRepository blob 38f00821b0.
  These are adapted rather than creating more scraping/scheduling engines.
- SearchPreferenceRepository blob 61c50a5cbd and original search_jobs /
  bilingual seniority and freshness ranker blob dd5a1ab3e3, NOT a new model.
- Original PostgresProfileRepository blob 5aedb03e7a, existing CV storage,
  application_workspace.new_workspace blob 049b4b82af, original unique
  PostgresWorkspaceRepository.create_or_get blob 804e736a06.
- Existing original verified account/CSRF/private profile boundary in api.py
  blob 863a2fbb87 and App.tsx account verification.
- Existing account-erasure quarantine and source worker per-owner isolation.
- No outside source was copied, no license workaround, no model-based factual
  fabrication, no new browser adapter, identity system or submission ledger.

## Genuine missing code and adapted pieces

- NEW migration 024: durable default-disabled account opt-in, conservative
  threshold/quota, revision, last-run aggregate status; no new CV storage.
- NEW auto_shortlist.py: approved owner/consent-lock persistence, score
  selection composed from original search_jobs, original safe CV builder and
  existing unique application storage; aggregate-only reporting.
- ADAPTED worker_runtime.py with optional application:local-shortlist
  task, separate from globally unsafe auto-ObumAI preparation. Worker
  operator switch defaults FALSE; user opt-in independently defaults FALSE.
- ADAPTED first-party API to GET/PUT account option and POST on-demand
  local draft cycle, requiring verified same-origin user cookies/expected ID.
- NEW AutoShortlistPanel with opt-in, disable, minimum score, cycle limit,
  immediate safe draft preparation and navigation to existing My Applications.
- ADAPTED account-erasure to revoke local scheduling, list new owner table.
  ADAPTED Compose/env.example only for worker operator configuration.
- NEW unit/real PostgreSQL OIDC race and React component/worker regression
  tests reuse prior fixtures and reject account switching, duplicate drafts,
  nonexistent CV/evidence, stale jobs, revoked status and external actions.

## Production reality and strict boundaries

This enables automatic selection and local application preparation from
continuously ingested IT jobs AFTER release, NOT arbitrary unattended final
employer submission. Unsupported employer forms and unanswered screening
questions still require applicant-led review; official partner submit is
independently gated and returns provider confirmation only when real.
Operator must separately verify active OIDC, native ObumDelivery exact SHA,
controlled negative RED, source feed health, owner-approved rollback and
OVH deployed SHA, then enable worker flag. Applicant must individually opt in.
No live employer action or deployed product claimed by this source PR.

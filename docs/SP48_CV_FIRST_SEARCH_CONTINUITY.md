# SP48 — CV-first nationwide job list continuity (source implementation)

**Date:** 26 October 2026 (Finland)  
**Baseline:** SP47 main `f5b0540d2b3a29526f7a6109a989a9fecc6daaf6`  
**Plan:** SP21 P0 CV-first discovery → selected-job review → AutoApply case  
**Scope:** source/CI; no claim of an OVH deployment or employer application.

## Problem

The actual signed-in CV-first UI displayed only the first **80** combined
recommended/broader job rows, and its original read-only API returned at most
**120** rows in each category. A text filter ran only on the already-returned
subset. A user choosing a genuine current job from the Search screen could
land on the Apply screen without seeing that job if it fell outside either
initial API window. This blocked the intended CV → select job → review flow.

## Changes to existing components, without a new engine

1. Reuse `cv_job_matches`, the original owner-scoped stored CV,
   `SearchPreferences` scorer and source-current job ledger. Add two
   independent bounded offsets, a page size, and a title/employer/location
   text query **after ranking the complete current ledger but before paging**.
2. Reuse the exact `canonical_key` from the selected Search job to include
   one **current** selected-job card independently of the two page windows.
   An arbitrary submitted key cannot change job data or authorize draft
   creation. Missing, retired, unknown or mismatched keys are not pinned.
3. Reuse the existing signed-in `GET /api/v1/profile/cv/matches` endpoint.
   New optional query values: `limit` (1–100, default 40),
   `recommended_offset` and `other_offset` (0–100000),
   `query` (up to 120 characters), and `selected_job_key` (up to
   160 characters). The original no-parameter response remains valid.
4. Return `recommended_count`, `other_jobs_count`, and
   `current_jobs_count` separately from page slices, plus `selected_job`
   or null. Keep `qualifications_verified: false` and
   `employer_actions_performed: false`, no-store, and strict account scope.
5. Reuse `ApplicationJourney` and the existing API client; replace
   `jobs.slice(0,80)` with deduplicated current pages, a Load More control,
   and a short-debounced, server-side query. The chosen exact current job is
   displayed first and never lost merely because it was not in the first
   page. The original private document preparation and per-job Agent Zero
   entry points remain unchanged.
6. Protect delayed first-page and next-page responses with request epochs
   and a fresh account check. A stale user/CV response cannot repopulate
   the private match screen. CV replacement clears selected job checkboxes.

**Reuse-first proof:** all discovery, profile ownership, matcher, ranking,
application drafts, queueing and agent tracking components are original
SmartPloy modules. No new database table, ATS scraper, model, library,
CI framework, external code dependency, or employer-submit route was built.

## Safety and boundaries

- This makes **all current jobs in the existing database reachable** via
  pages and filters; it does **not** establish that every job advertised in
  Finland has been ingested. Improving approved source coverage remains a
  separate workstream.
- Exact-job pinning is read-only. The existing private workspace API still
  validates ownership, posting identity, source freshness, permissions and
  user review before any later application action.
- This work does not start agent emails/calls, submit employer forms, use an
  LLM, bypass an employer login/challenge, or turn browsing into consent.
- If the live feed changes between requests, later pages may shift.
  Duplicate display rows are hidden and a repeated-only page prompts the
  applicant to refresh; stable cross-refresh snapshot pagination is not yet
  claimed.
- The separate authorization / genuine employer-acknowledgment / native
  ObumDelivery / OVH release barriers documented in SP46–SP47 remain.

## Acceptance checks

- Python pure matching with 175 synthetic source-current jobs proves
  >120th ranked job pages are reachable, a page-8 Search job is pinned,
  full-ledger filtering finds a late title, and retired jobs are refused.
- No-recognized-signal cases prove >120 unranked jobs remain reachable.
- Negative tests cover invalid limits, offsets, input lengths and control
  characters; same-owner CV constraints and no employer actions remain.
- FastAPI test uses the **actual original** application API, source ledger
  and uploaded synthetic DOCX; verifies bounded query, true counts,
  exact job pin, no-store and 422 for invalid pages.
- React tests exercise real UI Load More, an out-of-page selected vacancy,
  full-ledger remote search and rejection of a delayed next-page response
  after the signed-in identity changes.
- Require GitHub real-PostgreSQL, React/Vitest, actual Chromium and isolated
  Compose smoke on the exact candidate head, then independently on merged
  main. These are source tests only, never production acceptance.

## Delivery state

Production commissioning remains blocked until the authorized operator
enables SmartPloy in the running ObumDelivery controller with the required
two-control exact SHA checks, and an authenticated approved OVH rollout.
A public health HTTP 200 without a verified `release_revision` is not proof
that SP48 is running. Do not mark live AutoApply available based on this
source-only change.

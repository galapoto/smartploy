# SP49 — Failure-tolerant selected AutoApply batches and private agent continuity

**Date:** 26 October 2026 (Finland)  
**Source baseline:** SP48 `main@2e3b5e3eab8efc6dd6165205ebe3495eae7638fd`  
**Plan:** SP21 P0-B user-selected per-job private draft/Agent Zero flow; SP21 P0-C correct application continuity  
**Boundary:** source code and synthetic test evidence, NOT live employer submission or production OVH activation.

## Production-relevant defect

The original `App.onPrepareSelectedJobs` loop prepared selected postings one at
a time but called `break` on its first ordinary failed job. Choosing 15
freshly discovered vacancies and encountering one retired, unavailable or
temporarily unprepared posting at position 1 silently starved jobs 2–15.
All selected checkboxes remained checked, and the user saw no per-job result
or progress. This contradicted the one-independent-agent-per-application
design even though each underlying SmartPloy workspace was already
idempotently persisted.

## Reused runtime components; new original glue

- Reuse existing signed-in OIDC `runPrivateMutation` before-and-after
  identity verification, same-origin/expected-owner API request guard and
  original `POST /api/v1/jobs/{canonical_key}/application-workspace`.
- Reuse `new_workspace`, original workspace `create_or_get`, optional
  explicit `start_private_agent + confirm_in_app_tracking_only`,
  `PostgresApplicationAgentRepository.create_or_get` and existing Agent
  Zero worker. No new agent, executor, provider adapter, database,
  dependency, browser permission or AI client.
- Replace the old **stop-on-any-error** client loop with an ordered,
  **bounded maximum 15** independent per-job loop. Only authenticated
  account/identity changes are fatal across the batch; ordinary
  job-specific failures are recorded and do not starve later jobs.
- Preserve the first successfully prepared workspace for existing
  My applications navigation. Keep the Apply screen open when at least
  one exact key failed. Only keys that failed remain checked for an
  explicit subsequent Retry; prepared keys are removed from the retry
  selection. Existing server create-or-get remains idempotent if a
  network response was lost after a draft was actually saved.
- Show processed/total progress and exact **private draft** outcomes.
  Distinguish stored agent `active`, `paused`, `closed`,
  `unavailable`, instead of counting all non-active as unavailable.
- Replace the old boolean in-flight guard with one per-run token, so an
  old account's delayed `finally` cannot unlock a new account's
  batch after sign-out/sign-in or private workspace reset.
- Scope delayed UI outcomes to user ID plus CV SHA; no old batch restores
  selection state or success notifications for another account/CV.

## Acceptance contract

1. Test three synthetic selected vacancies: #1 cannot be prepared,
   #2 yields original saved workspace and original active Agent Zero,
   #3 cannot be prepared. Verify all **three** original API calls occur.
2. Verify #2 is unchecked after success; #1/#3 remain selected and
   the UI offers **Retry 2 failed jobs** and **Open prepared applications**.
3. On explicit retry, only #1/#3 are passed through the same original
   private API (not #2). Return one paused and one unavailable agent;
   neither is represented as active. Final successful batch navigates
   to the existing review workspace.
4. Reverse/control test changes the active OIDC principal to a different
   subject sharing the same email while #1 is pending. The original
   `runPrivateMutation` fails closed and **never attempts job #2**.
5. The component-only tests verify actual progress, exact-key retry
   selection, and duplicate-click resistance. No employer send, form
   submission, private employer contact, or fabricated receipt is
   tested or implied.
6. Existing GitHub Python/Postgres full and AutoApply E2E suite, React,
   Chrome companion, Chromium and isolated Docker smoke remain required.
   Require all five checks green at the exact PR SHA and independently
   after merge.

## Limits and next critical deployment step

This improves **preparation reliability**, not automatic final submission.
Actual employer submission is still limited to the separately authorized
one-shot Lever partner path; other employer flows still require human
review and action. Nothing in this change bypasses employer terms,
CAPTCHAs or a real user's fresh submission decision.

The live site on 26 Oct returned healthy PostgreSQL and worker
status but did not expose `release_revision`; ObumDelivery source
inventory still has `galapoto/smartploy enabled: false`, and public
controller access requires authentication. Source CI is NOT an OVH
deployment or native Woodpecker receipt. A release requires approved
controller enrollment, exact-SHA native quality gate, guarded OVH
backup/migration/recreate, public SHA and companion proof and signed-in
real-browser acceptance. Never treat a green PR as proof of a delivered
application.

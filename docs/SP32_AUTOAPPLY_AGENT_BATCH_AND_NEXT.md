# SP32 — AutoApply selected-job agents and the next-application review queue

**Plan:** SP21 P0-B single guided application journey and Agentic SmartPloy
master plan Gate 1 (one real application → one durable per-job agent).
**Baseline:** SP31 merged at `main@c32935e76604e747bfbe505ba223cfe1f6074a31`.
**Production caveat:** source code and GitHub CI do not prove a running OVH
release, independent ObumDelivery qualification, or real employer sending.

## Core user-visible change

The original AutoApply selection loop saved CV/letter workspaces but did **not**
create durable per-job agents. Applicants had to visit each saved job and click
*Start tracking this application* a second time. Also the Application Studio
repeatedly selected the originally focused workspace on refresh, even after
the applicant had explicitly opened another queue item. There was no
Next-application action in the editor.

**SP32 now:**

1. Applicant chooses **AutoApply**, uploads one CV and selects current jobs.
   The queue button explains that each selected job will receive a **private,
   in-app-only** tracking agent, and no employer will be contacted.
2. The existing workspace endpoint accepts an *optional* strict opt-in
   `start_private_agent=true` together with
   `confirm_in_app_tracking_only=true`. **Both must be present** for case
   creation. The old manual and assisted POST with no body stays unchanged.
3. The endpoint checks the already bound user's identity, expected initiating
   user ID, exact same origin, and `Sec-Fetch-Site` before the explicit
   agent opt-in can create an application case. Unknown body keys, string
   booleans and missing acknowledgement are rejected.
4. The original `new_workspace` plus `workspace_repository.create_or_get`
   saves/reuses one per-user/job workspace. Then the **original**
   `PostgresApplicationAgentRepository.create_or_get` binds one idempotent
   logical agent with an immutable event history. This does not wake the worker
   immediately, call ObumAI, send email or execute an employer submission.
5. Response `agent_tracking` is structured and truthful: an active/paused/
   closed case is distinguished from `unavailable`. If migration or durable
   agent storage is unavailable, **the saved draft remains usable** and the
   UI explicitly reports that tracking is unavailable. A previously closed
   agent is never silently reopened.
6. Application Studio uses the existing saved owner-scoped workspace list
   to offer a **Next application** button; it visits other draft items in
   queue order, skipping personally reported/applied and provider-acknowledged
   outcomes, and wraps to remaining drafts. Existing `pick` prompts to
   protect unsaved CV/letter edits. Selecting Next is not a new employer
   action or a new saved application.
7. Refresh now preserves the applicant's current selected draft instead of
   jumping back to the first focusId, reducing wrong-job editing risk.

## Reuse and original code

**Reused (no duplicates):** `new_workspace`, original
`PostgresWorkspaceRepository`, `PostgresApplicationAgentRepository`,
per-case event ledger and SP31 deterministic agent identity, original OIDC
session / CSRF middleware, `api.ts` expected-user private mutation boundary,
`ApplicationJourney` and `ApplicationStudio` UI, original dirty-state
confirmation, original worker (opt-in) and familiar test fixtures.

**New glue:** one optional, strict request model and guarded in-app agent
binding on the existing workspace creation route; one boolean opt-in in the
explicit batch queue; truthful aggregate tracking result; Next draft
selection and focus-refresh correction; focused React + OIDC/Postgres
regressions. No new database migration, browser submitter, external package,
agent process, authorization, or independent storage model.

## Security and expected limits

- No agent is created from general browsing, CV upload, manual/assisted job
  preparation, search preferences or background model access alone.
- Every explicit AutoApply case is tied to the original signed-in user and
  existing per-job workspace. Duplicate batch selections are idempotent.
- The agent state `active` describes a **stored logical case**; it does
  **not** prove the OVH worker flag is enabled or that browser-closed wakeups
  ran. `worker_wake_verified=false` remains explicit.
- No employer submission, browser final click, email, phone call, external
  AI processing, partner API approval, or new persistent CV copy happens.
- An unavailable agent never causes the backend to claim tracking success;
  the applicant's existing draft is preserved and editable.
- Closed agents cannot silently be restarted by AutoApply.
- The Next button never visits another account's data, sends a job
  application, or silently discards unsaved edits.

## Tests to run

1. Real Postgres/OIDC synthetic two-subject test: old request leaves agent
   absent, missing consent/extra key/string boolean and wrong-origin denied,
   explicit queue request creates exactly one agent/event, repeated request
   reuses it, zero employer attempt claim, same-email different owner denied,
   durable-agent repository unavailable reports `unavailable` without losing
   the existing draft.
2. Frontend API test: old manual POST has no body, AutoApply POST has exact
   two true opt-in fields and the original initiating user ID.
3. App/React test: selection only, queue creates agent, and unavailable
   tracking is reported honestly without losing application draft.
4. Studio/React test: Next application opens correct saved draft, refresh does
   not reset it, unsaved edits are protected, completed applications skipped.
5. Run complete exact-head GitHub tests (Python/PostgreSQL, Vite/React,
   Chromium browser, Docker fixture, immutable review receipt), then merge
   only if green and repeat on `main`.

## Progress

- **Done in source:** strict opt-in case binding, no-send safeguards, queue
  progression and corresponding tests.
- **In progress:** exact-head CI, merge, merged-main CI.
- **Blocked (independent):** native ObumDelivery exact-SHA qualification, OVH
  exact running image/health release revision, ZITADEL two-account sign-in,
  actual worker wakeup proof.
- **Not started:** permissioned arbitrary ATS employer final action and
  external recruiter follow-up delivery; these remain separate releases.

A successful GitHub Actions `deploy-stack` CI job is a **synthetic Docker
build/smoke**, not evidence of deployment to OVH. Feature flag
`SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED` stays OFF unless individually
approved and deployed through its existing rights gate.

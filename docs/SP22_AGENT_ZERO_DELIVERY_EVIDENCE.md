# SP22 — Agent Zero: First working agentic application case

**Project gate:** Agentic SmartPloy Master Plan Gate 1 / P0-A  
**Date:** 22 October 2026  
**Status:** Implemented on feature branch. Main, ObumDelivery and OVH status require separate exact-head proof.

## User-visible outcome

In the existing **My applications → Application Studio**, the owner opens a job-specific
workspace and selects **Start tracking this application**. SmartPloy creates or
reuses one persistent application agent for this workspace and shows its
lifecycle, in-app activity timeline, last reminder and next-step controls.

The agent remains a lightweight PostgreSQL identity when the browser closes.
The current shared worker can wake due cases, record one owner-scoped reminder,
and schedule its next review one day later. This is an in-app event only:
**no email, calendar event, voice call, employer outreach, web browsing,
AI-processing or employer submission occurs.** The applicant can pause, resume
or permanently close the case. Deleting an application workspace automatically
deletes this case and its events. Account-erasure quarantine blocks agent access
and wakeups.

## Exact code reused instead of rebuilding

- `smartploy/application_workspace.py`, `application_workspace_storage.py`,
  `migrations/011_application_workspaces.sql`: existing approved CV/facts,
  canonical job and one-per-owner/job workspace, including durable PostgreSQL.
- `smartploy/worker_schedule.py`, `migrations/006_worker_tasks.sql`: existing
  lease-based `ContinuousWorker` scheduler, retry/backoff and fixed job
  registry. SP22 appends one optional batch task, not one process per agent.
- `smartploy/api.py` and `smartploy/oidc.py`: first-party tenant binding,
  account identity, same-origin and expected-user request guards.
- `web/src/ApplicationStudio.tsx` and `web/src/api.ts`: existing authenticated
  application editor/account-switch safety and centralized typed HTTP wrapper.
- `migrations/018_account_erasure_quarantine.sql`: preexisting erasure
  quarantine guard, reused in every case write/read/wake.
- `obumai/obumellm/docs/agents/AGENT_JOB_RUNTIME.md` (read and reviewed):
  bounded durable event/run semantics and external-actions-disabled precedent.
  No ObumAI runtime file copied or external calls authorized yet.
- The [reuse audit](AGENTIC_SMARTPLOY_REUSE_AUDIT_20261022.md) inspected
  career-ops, open-apply, Paperclip and agent/browser frameworks. Those third-party
  runtime packages are **not imported into SP22 Agent Zero**, because that would
  duplicate existing scheduling, CV or storage. Their reviewed patterns inform
  follow-up and agent-fleet gates only after pinned source/license evaluation.

## Built from scratch only where absent

1. `migrations/025_application_agent_zero.sql`: case and immutable per-agent
   revision-sequenced event ledger, with FK cascading to workspace.
2. `smartploy/application_agents.py`: owner-scoped atomic case create,
   optimistic lifecycle transition, paginated events and SKIP LOCKED due
   claims. The case holds NO duplicated CV, letter or recruiter mailbox.
3. `api.py`: create/list/get/pause/resume/close API entrypoints. All outputs
   explicitly state zero employer actions; POSTs require verified user headers.
4. `web/src/ApplicationAgentCard.tsx`: opt-in case card embedded within the
   existing studio, refreshed through the established account-verification
   callback; a missing Postgres deployment never pretends to be durable.
5. PostgreSQL and React regression suites for owner isolation, concurrent
   create, idempotent wake, quarantine, stale revision, same-email account
   switching, no-origin cross-account mutations and no external effects.

## Safe migration and activation

Migration 025 is included automatically in the existing `apply_migrations`
ordered runner. The production release must apply it using its existing,
guarded migration process **before** enabling the optional worker task.

The global worker flag defaults to off:
`SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=false`.

After verified DB migration, independent CI review and OVH release receipt,
the operator may set it to `true` in the existing private runtime config and
reconcile the existing service stack. Supported bounded settings:
- `SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS`: default 60, max 86400.
- `SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT`: default 20, max 50.

No user CV or SMTP/provider token is passed into Agent Zero. This opt-in task
cannot send outward even when enabled. If the task is disabled the case and
timeline remain durable but no automatic scheduled wakeups are executed.

## Backend API contract

- `POST /api/v1/application-workspaces/{workspace_id}/agent`: explicit create/get
  (201 created or 200 reused), only owned existing workspace, fail 503 without
  Postgres; no body identity or unverified job target.
- `GET /api/v1/application-agents`: current owner's cases only.
- `GET /api/v1/application-agents/{agent_id}?after_sequence=N`: owner-bound
  case and up to 100 in-app events; no CV or applicant contact information.
- `POST /api/v1/application-agents/{agent_id}/pause|resume|close`: JSON
  `{"expected_revision":N}`; cross-account 404, stale version 409, closed
  terminal. Same-origin verified user header is mandatory.

## Definition of complete for this gate

- Exact source HEAD: Python/PostgreSQL tests, React, browser, and deploy stack
  pass; signed review receipt on same SHA.
- Single candidate can create case and revisit after browser closure and
  worker restart; in-app event is present and in-app only.
- Simulated same-email independent account cannot list/read/update case.
- Concurrent case create yields exactly one case and one event, and stale
  workers do not duplicate reminder effects.
- Pause, close and erasure quarantine prevent agent wakeups.
- No employer submission/email/voice and no fake application status count.
- Main merge, independent ObumDelivery gate, migration, OVH exact SHA, actual
  signed-in acceptance and native service worker tick are reported separately.

## Next incremental gate

Adapt only the **missing** follow-up-cadence, recruiter-reply classification and
outcome fixtures from career-ops (MIT, pin commit+license) and open-apply (MIT)
to the existing SmartPloy case. Add an opt-in read-only scoped mailbox bridge
through ObumConnect, then human-reviewed outbound draft and real provider
send receipts as a distinct permissioned feature. Do not widen Agent Zero's
in-app-only authority accidentally.

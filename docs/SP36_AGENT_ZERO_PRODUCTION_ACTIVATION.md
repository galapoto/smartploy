# SP36 — Make Agent Zero really activatable in the OVH worker

**Date:** 25 October 2026  
**Plan area:** SmartPloy SP21 P0 agentic application lifecycle; Agentic
SmartPloy Gate 1; independent production acceptance; native ObumDelivery.

**Before SP36:** SP32–SP35 implement private CV-first drafts, one durable
per-job Agent Zero, opt-in background case creation, candidate-initiated
check and an Agent Inbox. The Python scheduler already has the feature
flag `SMARTPLOY_WORKER_AGENT_ZERO_ENABLED` and a shared Postgres
`application:agent-zero-reminders` task. **However, the production
Docker Compose worker never passed this flag or its cadence and batch
options into the container.** The host-only private env file had no
documented Agent Zero flag either. Even setting it to `true` on OVH
could not have registered that task in the actual worker container.

**Public read-only observation on 25 October 2026:** The endpoint
`https://smartploy.komplyint.fi/healthz` returned an OK service, ready
PostgreSQL and worker infrastructure with 31 tasks, no ObumAI and no
external actions. However, it had **no `release_revision` field** even
though reviewed SmartPloy source since SP24 includes the exact build
fingerprint. This means public health does not attest that later GitHub
main code is running on OVH. The signed-out dashboard returned 401 and
`/auth/login` redirected to ZITADEL's login. These are **public**
observations, not owner-authenticated E2E proof or deployment receipts.

## Actual implementation

1. `deploy/personal/docker-compose.yml` now explicitly carries the
   existing `SMARTPLOY_WORKER_AGENT_ZERO_ENABLED`,
   `SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS` and
   `SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT` **only in the worker**
   service environment. The default remains `false`, 60 seconds,
   batch 20. Nothing is added to API, web, Postgres or client JavaScript.
2. `deploy/personal/env.example` documents the default-OFF operator
   decision and correct worker-only private settings. Do not commit a
   private `deploy/personal/env`, replace its DB password or enable
   global ObumAI submissions.
3. The existing `preflight.sh` and
   `smoke-env-boundaries.sh` verify these 3 names are actually present
   in the intended container, not allowed in API/web/postgres, and have
   strict literal boolean and bounded integer values. Preflight runs
   before any database backup/migration or Docker recreation.
4. The small read-only
   `smartploy.agent_zero_runtime_acceptance` module queries the
   **existing** `PostgresWorkerTaskRepository.get` and checks original
   task kind, enabled state, in-app-only/no-external policy metadata,
   `last_status`, `last_completed_at` and zero recent failures.
   When release acceptance requests a fresh run, it verifies the
   completion happened **after the current worker container started**.
   It cannot accidentally count a historical task from an older image.
   There is a bounded 100-second retry, not an indefinite background
   process or synthetic in-production task.
5. `deploy/personal/scripts/assert-agent-zero-worker.sh` is a
   **read-only operator gate**. It reads only the flag from private host
   env, validates the rendered Compose worker-only scope in memory,
   obtains the current actual Docker worker `StartedAt`, and invokes
   the module **inside that worker**. If enabled, it demands a recent
   healthy scheduled task run after current container start; if
   disabled, it demands the task is absent or explicitly disabled.
   Its output is a fixed non-sensitive receipt (status/booleans only).
6. The existing guarded `deploy.sh` now calls the gate **after**
   migrations and image-health checks but **before** writing the
   `deployed-sha` success marker. An enabled but nonfunctional agent
   scheduler cannot be marked as a successful SP36 deployment.
7. The original `release-evidence.sh` also checks the task and
   includes only safe fields:
   `agent_zero_mode`, `agent_zero_operator_enabled`,
   `agent_zero_scheduled_run_verified`,
   `agent_zero_candidate_reminder_verified=false`, and
   `agent_zero_employer_contacts_authorized=false`. A task run
   processing zero candidate cases is **not** proof that a real
   applicant received a notification.
8. GitHub's **synthetic Docker/PostgreSQL** CI turns on Agent Zero only
   in its temporary fixture, uses 5-second cadence and 16-claim
   batches, requires a real task cycle and explicitly checks a RED
   negative control using a future timestamp. The immutable release
   evidence must contain the task proof. The separate real Postgres
   tests cover one per-case event, crashes, concurrent scheduling and
   account isolation. This does not submit an employer application.

## Reused vs new and time-saving proof

**Reused:** original shared source-worker main loop, registered task ID
`application:agent-zero-reminders`, existing `WorkerTaskSpec`,
`PostgresWorkerTaskRepository`, `process_due`, account-safe immutable
events, migrations 025–027, production private env allowlist,
source-admission/lock/backup/migrate/restart/release evidence,
image SHA gate and isolated GitHub Compose fixture. No second agent
runtime, scheduler, task table, API, database migration, external
dependency, model forwarding or employer integration.

**New:** three explicit Compose environment fields, private example
comments, bounded task attestation module, compact read-only host gate,
small preflight/boundary assertions, CI freshness negative control and
regression tests. Engineering elapsed-time savings were not measured;
reuse avoids maintaining a second scheduler/ledger.

## Operational gate sequence (not performed by this source PR)

1. Owner/ObumDelivery operator confirms native Woodpecker
   `galapoto/smartploy` exact-SHA positive/negative test receipts
   and exact source. GitHub 5/5 is separate and insufficient.
2. Independently approve one **exact main ancestor SHA**; choose the
   existing `runtime.oidc.production.env` profile. Preserve the current
   untracked `deploy/personal/env`, database volume and backups.
3. Keep `SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED=false` unless a
   separately rights-approved one-use Lever job exists. Keep
   `SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED=false`.
4. If the owner approves *in-app-only* scheduled case reminders, set
   `SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=true` privately with bounded
   cadence/batch. This **does not** grant application submission,
   recruiter email, phone calls, external AI or ObumAI tool actions.
   Existing per-user agent choices remain separate.
5. Use the original exact-SHA `deploy.sh` with the existing service
   lock, preflight, backup, migrations and full restart. It now
   rejects missing enabled-worker task acceptance before recording
   the deployed SHA. If flagged off, a healthy stack with no agent
   task may still release truthfully; it cannot claim background
   reminders active.
6. Independent live acceptance: verify public health
   `release_revision` matches the reviewed 12-hex SHA, real
   container image IDs match full exact Git SHA, signed-out API
   responds 401, public ZITADEL redirect is trusted, and authenticated
   two-account CV-first review is isolated.
7. To prove true **browser-closed per-case wake**, one consenting
   test applicant opens a private real application case and agent,
   closes the browser, and later confirms one saved in-app event
   with the original agent timeline. A recorded generic worker task
   run alone does not satisfy this owner-level requirement.
8. Finally, independently permission a single real employer
   Lever partner or browser final action with exact posting rights,
   current applicant consent and one-use attempt. Never equate a
   private event or observed employer page with a verified ACK.

## Status/limits

- **Done in branch:** worker-only activation wiring, fail-closed
  runtime proof and exact-source tests (receipt links required after CI).
- **Not automatically enabled on OVH:** code changes cannot mutate the
  untracked private production env or deploy themselves.
- **Blocked:** no authenticated OVH shell/native Woodpecker production
  connection within this ChatGPT session, no two-user signed-in QA and
  no actual scheduled applicant event.
- **Not started:** unattended final submissions on arbitrary ATS forms;
  those require per-provider rights, user review and real confirmation.

Source-level syntax/CI must pass *before* merging. GitHub's
`deploy-stack` job uses a temporary test database and **never
deploys OVH**; do not claim release readiness or employer ACK from it.

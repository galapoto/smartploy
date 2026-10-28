# SP59 — Attest the actual automatic draft worker, not generic health

**Date:** 28 October 2026 · **Plan subpart:** SP21 P0-C AutoApply background worker + Agentic SmartPloy production acceptance.
**Baseline:** SP58 `6911f18e18fd3e77808e0cb43aa4cf01d8236168`.

## Proven problem and user impact

SmartPloy could report `/healthz.worker.ready=true` with dozens of scheduled
tasks even when **no `application:auto-draft-shortlist` task was enabled or
running**. The user wants the original job-source→private draft automation to
work unattended after opting in. A healthy generic worker, an enabled setting,
or a saved draft from an older release is NOT proof that this release's AutoApply
worker actually ran.

Another defect: the shared Compose file set `SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED`
to **true when the host setting was absent**, contrary to the original Python
worker default `false` and candidate-controlled privacy policy. An absent
operator setting therefore silently enabled local CV processing.

## Reuse-first implementation

**Reused existing first-party product code and contracts:**

- `smartploy.worker_runtime.build_worker_task_specs` and the existing
  `application:auto-draft-shortlist` task; no new scheduler, crawler,
  ranking engine, agent, database migration, user table or AI model.
- `PostgresWorkerTaskRepository.get`, the original persisted task status,
  120–86400-second cadence, `private_opt_in_required=true`,
  `processing=local_only`, and `external_actions_authorized=false`.
- Agent Zero SP36 read-only acceptance pattern and its already-tested UTC
  validation/ISO timestamp parsers, Docker worker start-time check, immutable
  selected identity policy, private Compose boundary and release-evidence lock.
- Existing SP57 exact public release SHA, the approved production deployment
  script, and existing isolated Docker CI fixture.

**New missing glue:**

1. Small `auto_draft_runtime_acceptance.evaluate` that denies absent/
   disabled or wrong-kind tasks, tampered privacy metadata, errors, stale or
   future timestamps, and cycles completed before the **current worker
   container started**. With explicit operator opt-in `true`, it requires
   a successful recent scheduled run; `false` requires the task disabled.
   Its output contains fixed booleans and states only, **no CVs, account IDs,
   employer/job listings, raw errors, credentials or DSN**.
2. `assert-auto-draft-worker.sh` reuses the existing worker and Compose
   policy, fails closed on duplicate/invalid opt-in flags or wrong container
   scope, then verifies the real scheduled task in the actual worker using
   a bounded read-only command.
3. Compose's **missing-flag** default is now `false`. The existing
   `deploy/personal/env.example` expressly sets the flag to `true` for
   reviewed, opted-in pilots, so a configured operator deployment can still
   activate private review-only background drafts at normal cadence.
4. The original guarded `deploy.sh` checks this task before recording
   `deployed-sha`; `release-evidence.sh` records
   `auto_draft_mode`, `auto_draft_operator_enabled`,
   `auto_draft_scheduled_run_verified`, and explicit **no candidate draft
   or employer contact proof**. A passing task run with no opted-in users is
   not evidence a specific applicant's CV was drafted.
5. GitHub's original isolated production Compose smoke runs a positive
   receipt and deliberate future-time RED control, verifies the captured
   release artifact fields. The fixture explicitly opts in to private
   AutoDraft and uses synthetic PostgreSQL; no OVH data or credentials.
6. Unit and static contract tests cover default-off, invalid/tampered flags,
   wrong task type, privacy policy mismatch, missing/failed/degraded/future
   or stale runs, actual current-worker-start bound, and metadata nonleakage.

## Delivery and outstanding approval

- Use exact-head PR CI, then independent merged-main CI as source proof.
  The source test's four services are **isolated** and are not the live OVH
  worker.
- Live `https://smartploy.komplyint.fi/healthz` still returned no
  `release_revision` at the last public probe. There is no evidence this
  code or SP58 is deployed; native ObumDelivery remains
  `inventory/projects.yaml: enabled=false`, awaiting owner admission.
- This code neither switches on any live worker nor changes any user
  opt-in, connects ObumAI, sends a CV externally, authorizes a partner
  application, contacts employers or confirms any actual candidate drafts.
  Operator-controlled exact-SHA deploy and live account acceptance remain
  separate REQUIRED gates. Evidence is a **read-only worker-cycle fact**, not
  release approval or an employer receipt.

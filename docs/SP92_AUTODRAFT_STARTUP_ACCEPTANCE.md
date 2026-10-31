# SP92 — AutoDraft restart acceptance without bypassing the original worker

## Observed issue
Two production deploy attempts (31 October 2026) built and started healthy services
but stopped at the unchanged **AutoDraft post-restart freshness gate**:
`AUTO_DRAFT_FRESH_RUN_MISSING`.

The authoritative existing Compose default is 600 seconds for
`SMARTPLOY_WORKER_AUTO_DRAFT_CADENCE_SECONDS` (the sample private env
uses 120 seconds). The actual operator-private override is not known here.
The release gate waits only 110 seconds, while
`PostgresWorkerTaskRepository.register()` deliberately preserves durable
`next_run_at` during restarts. An unexpired prior lease can delay a task
even further. Previously completed work must *not* be accepted as a new run.

## Safe fix
Only the existing source worker, on startup (not the `--once` command), does:

1. Register original task specs using the existing `ContinuousWorker`.
2. If the **operator-enabled** `application:auto-draft-shortlist` spec is
   present, request a single warm-start of its existing PostgreSQL task.
3. PostgreSQL updates *only* `next_run_at` if all of these are true:
   - the task is the exact original AutoDraft name and kind;
   - it remains enabled with the exact local-only/private-opt-in and
     no-external-action metadata policy;
   - it previously completed successfully with zero failures;
   - its prior completion is older than this startup timestamp; and
   - no unexpired lease is present.
4. If accepted, the original worker attempts a **targeted, leased claim**
   of that task. This uses the same `claim_due`, `complete`, runner and
   per-user consent rechecks. It does not call a second task engine.
5. Normal scheduling continues thereafter at the configured cadence.
   Initial installations without prior completion still use the original
   source-first ingestion order; failed tasks keep their backoff.

## Prohibitions
- No creation of draft receipts without a real successful execution.
- No synthetic/forced `last_completed_at`, fake healthy status or
  disabling `--require-run --not-before` in release acceptance.
- No removal of DB leases or stealing an active lease, even if this leaves
  the release gate in HOLD.
- No enabling CV processing without operator and per-account opt-in.
- No employer send, provider automation or external network call in this fix.
- No revealing candidate data, application URLs, credentials or profile IDs
  in the startup log. The log reports fixed aggregate booleans only.

## Verification
- PostgreSQL fixture tests prove cadence preservation, startup target claim,
  disabled/wrong-policy/failure/lease refusal, no duplicated automatic run
  and first-boot source-first behavior.
- All other backend, browser and web CI gates must remain green.
- The live operator must deploy a **new immutable SHA** through the normal
  reviewed OIDC production script and confirm the post-restart evidence gate
  returns PASS. A happy-path CI test does not attest to the live worker.
- The subsequent `release-evidence.sh --online` must independently confirm
  the same API, static and deployed release SHA.

## Remaining distinction
A successful local AutoDraft scheduler cycle can create **zero** candidate
drafts. Even a PASS here does not attest a candidate-specific private draft,
nor is it proof of a submitted employer application. These remain separate
review and external submission acceptance tasks.

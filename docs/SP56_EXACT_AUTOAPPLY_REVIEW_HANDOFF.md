# SP56 — Exact prepared-job review handoff after AutoApply batches

**Date:** 27 October 2026, Europe/Helsinki  
**Plan:** SP21 P0-B (CV-first user review queue) and agentic SmartPloy case handoff.  
**Baseline:** merged and five-job source-CI-passing SP55 main `11f6de9f96afa90d73ac552d6ba9dfbe0505ac6f`.

## Core gap verified from original source

SP49/50/55 safely prepared up to 15 selected owner-bound jobs, and SP55 preserved successes after a later access denial. But the UI's **Open prepared applications** ignored which newly created job actually succeeded: Application Studio could select the earlier cached/default workspace (or the first of its 100 listed cases). In a partial batch, the applicant could review the wrong employer/job. This breaks CV → match → prepare → review → submit/handoff.

## Reuse-first change

**Reused:** original signed-in `runPrivateMutation`, exact canonical job keys, existing idempotent `startApplicationWorkspace` API response, original PostgreSQL workspace and per-job Agent Zero, SP49–55 partial retry handling, original Application Studio `focusId` plus owner-scoped GET for a case outside the first 100. The same Application Studio performs current account verification and retains existing reviewed document/partner/browser handoff safeguards.

**New:** the private batch outcome carries only `canonicalKey` and **server-returned** `workspaceId` for each successfully prepared selected job, merged by canonical key across deliberate subset retries. **Open prepared applications** targets that exact saved case, and an optional collapsed list offers one direct Review button per successful job. No browser-local storage of this mapping, CV text, new backend engine, provider permission, external request, runtime dependency, database migration, ATS adapter or copied third-party code. Build-time savings were not measured.

## Acceptance and delivery gates

1. Parent React integration: A private draft created, B denied, C never attempted; the Open button navigates to **the exact saved A workspace ID**, not an arbitrary list item.
2. Child React: A prepared, B transient failure, C retired; retry B only, keep C blocked, preserve A's original workspace ID and provide distinct exact Review actions for A and B.
3. Missing workspace IDs from older synthetic/mocked outcomes never result in guessed IDs; existing generic My applications path remains.
4. Run all five exact PR-head checks and independently merged-main CI (PostgreSQL/Python + AutoApply E2E, React/companion, Chromium, temporary Docker, exact review receipt).
5. Production still **HOLD**: owner-approved native ObumDelivery project enrollment and positive/negative exact-source receipts, backup-first OVH exact-SHA rollout, running image/revision evidence, two actual authenticated accounts, fresh sources, independent employer rights and genuine employer-issued application acknowledgment. Green GitHub `deploy-stack` is synthetic and **does not** deploy OVH.

**No real employer submission, release, native Woodpecker activation, unauthorized browser final click or measured speedup is claimed.**

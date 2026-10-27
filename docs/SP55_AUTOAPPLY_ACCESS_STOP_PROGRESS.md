# SP55 — Preserve AutoApply draft progress on mid-batch access denial

**Date:** 27 October 2026 (Europe/Helsinki)  
**Plan subpart:** SP21 P0-B CV-first selected-job batch → durable application workspace and Agent Zero case.  
**Baseline:** merged main `f80a5c614d291cbdc0b157a48e2c4c1c80b39908` (SP54).  
**Scope:** still-verified signed-in account, private draft preparation only. **No employer send or production release.**

## Original core defect

SP50 stopped on HTTP 401/403 by throwing away the entire batch response. If a private workspace for job A was already created but job B later lost access, the interface showed no successful-job progress, left A selected and encouraged another preparation request even though the original create-or-get API was already idempotent.

## Reuse-first implementation

- Reuse existing owner-verified `runPrivateMutation`, exact selected job keys, original PostgreSQL idempotent `startApplicationWorkspace` and Agent Zero, existing SP50 safe error-classifier and stop-after-current UX. No new workflow, crawler, scheduler or database.
- On **same-account** 401/403, retain earlier successful drafts and their agent statuses. Classify the denied job as nonretryable `access_denied`, list all later jobs as **unattempted**, and immediately stop the loop before the next API request.
- Avoid exposing backend error details. Show accurate saved/denied/unattempted counts and a blocked resume/selection state until the candidate restores access and reloads. Existing saved drafts remain in My applications.
- Keep a **different or expired account** entirely fail-closed: the original OIDC guard clears private state instead of leaking former-owner progress. No retry, permission or employer approval is manufactured.
- All other SP49/50 behaviors (retry transient private drafts, stop after current, prevent duplicate selected keys) remain unchanged.

**New code:** one batch-result flag, one fixed safe access error kind, small React workflow glue and synthetic tests. **Reused:** six original first-party components; no copied external code, new runtime dependency, new auth layer, schema migration, provider adapter or external action. Time savings from reuse were not measured.

## Required checks and production truth

1. React: job A success → job B 403 → job C **never called**; A disappears from retry selection, B/C stay blocked, restored access requires reload, safe diagnostic contains no private provider message.
2. Existing single-403, same-email account switch, transient retry, stop/resume and full AutoApply synthetic PostgreSQL contract continue passing.
3. Exact-head and merged-main Python/Postgres, React/companion, Chromium, Docker and source review CI before merge/release. Native ObumDelivery must independently attest exact SHA, not be inferred from GitHub CI.
4. Existing guarded OVH release still requires operator approval, backup-first exact SHA, running image/revision, two-user authenticated acceptance, real job source freshness and authorized genuine employer application acknowledgment.

**HOLD:** No native ObumDelivery admission, authenticated OVH deploy, or real employer submit is performed by this change. Unsupported employer sites still use human-reviewed browser handoff; the queue never contacts employers.

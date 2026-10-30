# SP73 — Read-only previous employer attempt checks for prepared drafts

Date: **2026-10-30**. Baseline: `main` `9bb6aec1d3bae67ea8ed7489c7b2abb94d782c3d`.
Plan section: SP21 P0-B / Agentic SmartPloy Gate 3 safety prerequisite after SP69–SP72.

## Actual user gap

AutoApply produces separate private job-specific drafts, including a potentially long application queue. The durable `ApplicationWorkspace.status="draft"` does **not** guarantee that no prior employer handoff/one-use claim has been reserved. Until now, the app only queried the signed-in employer attempt ledger for the currently opened draft. A different draft in the left list could say "not submitted" despite a reserved or uncertain attempt for the same employer posting.

## SP73 implementation

- Add an explicit, **read-only** **Check previous attempts** section to My Applications (only for owner-loaded drafts). It calls the original OIDC/same-origin-protected `GET /api/v1/application-workspaces/{id}/employer-attempt` endpoint. That service checks the durable employer claim across source keys and devices; no new API or employer authority.
- Only on a direct user click, check **at most 10 loaded drafts per batch**; require exact current OIDC `user_id` and `auth_source` checks **before and after every private GET** using the original `ApplicationStudio.verifyAccount`. No ambient automatic polling, worker task, CV upload, or request to an employer.
- Distinguish `reserved` / `not_reserved` / `unavailable` in a private result list. A reserved claim is **never safe to retry**; provide a button opening the exact existing draft for reconciliation. A failed, malformed, denied, or missing status is **unverified**, never interpreted as clean. `not_reserved` only means no prior claim **at check time**, not an approval to submit.
- Invalidate the data synchronously when the loaded draft IDs, revisions, last update or canonical keys change; cancel old work on unmount, account switch or reload. Do not display a previous revision's "clear" status. A late request from the old OIDC subject is not published.
- Adjust generic draft labels in the list to **employer outcome unverified**. The existing per-case SP71 next-action panel, one-use attempts, reviewed partner sends, native browser handoff, signed-in CV and Agent Zero remain unchanged.
- On exact-case open, the original `pick()` still requires user confirmation before discarding unsaved CV or cover-letter edits.

## Reuse-first ledger

| Component / source | Treatment |
| --- | --- |
| Original `getEmployerAttemptStatus` and server route | **REUSED UNCHANGED**. Original OIDC owner, origin, cookie, ledger, canonical job and employer URL checks remain security authority |
| `ApplicationStudio.verifyAccount`, `pick()`, owner-bound `workspaces` | **REUSED UNCHANGED**. Same-email switched accounts fail closed. No new server or browser permission |
| `ApplicationAgentInbox`, SP71 `applicationNextStep`, SP72 `applicationReviewQueue` | **REUSED UNCHANGED**. Existing status / due-case behavior preserved |
| `web/src/ApplicationStudio.tsx`, CSS | **MINIMAL ADAPTATION** to mount the read-only triage and correct ambiguous draft labels |
| `web/src/ApplicationAttemptAudit.tsx` | **NEW**: small local check limiter, status presentation and stale-scope guard; no backend or external dependencies |
| Vitest and Playwright fixtures | **ADAPTED** to run real signed-in synthetic API reads, dynamic revision/account-switch negative checks and no-send assertions |
| morluto/rea | **REA_NOT_APPLICABLE** to this change: complete first-party authorized source and existing security-critical endpoint already present, no opaque/missing code to reconstruct. REA not run; no reported speedup or third-party copied implementation |

## Security and acceptance contract

1. Checking attempts does **not** create a workspace, queue a task, contact an employer or grant a browser send. HTTP verb is GET, existing server-side same-origin/OIDC checks enforced. No secret, CV body, employer URL or claim token is returned to another account.
2. Tests: no requests before explicit click; reserved and clear statuses with truthful labels; selected reserved job opens exact existing application; errors fail closed; same-email account-switch and stale revision suppress past results; at most ten reads per check; zero pending drafts means no check.
3. React integration: original unsaved-editor confirmation holds when opening a reserved case, no provider send or browser packet is issued. Browser synthetic CV→Manual→draft→check displays real client result, with no extra creation.
4. No change to externally authorized Lever/Ashby partner gates or the companion's one-use flow. Browser observation is not an independent provider receipt.
5. **Do not count authenticated synthetic tests as OVH deployment or employer ACK.** Source integration requires exact-head 5/5 CI, a separate authorized native Woodpecker check and independent trusted production release/parity and signed-in acceptance.
6. External KEHA P67 production source remains disabled pending approval. No scraping/private source change.

## Honest completion ledger

- DONE in source: new read-only bounded employer attempt audit, integration in Application Studio, tests and this record.
- IN PROGRESS: exact-head CI and merge until receipts are verified.
- BLOCKED: native ObumDelivery SmartPloy enrollment, trusted OVH exact-SHA release and real signed-in acceptance; independently authorized employer final sends and KEHA production feed.

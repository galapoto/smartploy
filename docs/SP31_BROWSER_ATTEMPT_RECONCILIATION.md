# SP31 — Reconcile a consumed browser application without submitting twice

**Plan subsection:** SP21 P0-B single application status and SP21 P0-C one-use
browser submission. Extends SP25 application-agent reconciliation and SP26–SP30
authorized first-party Lever flow. **Not evidence of production deployment.**

## Confirmed gap and desired core behavior

The Chrome companion can consume one server-side employer attempt and attempt
one authorized Lever final click. A failed network response or browser closing
leaves an irrevocable `reserved_unverified` or `uncertain` attempt. SmartPloy's
Application Studio previously blocked importing even an **existing** visible
employer confirmation whenever this durable claim existed. It also disabled the
candidate's `I applied` status update. The ordinary PostgreSQL workspace
transaction intentionally denied all edits and self-report after reservation.

A reserved attempt is **not** proof that the employer received the application.
The applicant must be able to reconcile one attempt without issuing a new
attempt, changing the exact reviewed CV, or mislabeling user observations as
official provider acknowledgment.

## SP31 reconciliation sequence

1. Applicant chooses the saved job with a previous server claim. UI displays
   **previous attempt — outcome needs review**. Document editors, fresh
   autofill packets, AI edits and new employer submission remain unavailable.
2. Applicant checks the original employer confirmation and receives a
   reference-bearing receipt from the existing Chrome companion. If no
   qualifying observation exists, leave the case in uncertain status; **never
   retry** or assert an employer acknowledgment.
3. Applicant uses the existing **Import observed receipt** UI. The original
   backend validates owner, exact workspace revision and CV/letter SHA-256,
   matching Lever employer URL, observable confirmation, timestamp and bounded
   reference. It records **browser_observed_unverified**, not a provider ACK.
4. Only when this receipt is present may the owner choose **Confirm outcome of
   previous attempt**, explicitly asserting they personally saw delivery. The
   existing owner-bound report-applied endpoint stores
   **self_reported_applied**, which remains distinct from employer verified.
   The existing Agent Zero lifecycle can consume that status.
5. The original durable employer claim stays consumed forever. No code
   deletes, restores, resets or retries the claim; no browser click, partner
   API POST or external employer communication occurs during reconciliation.
6. The user may review records and follow-up drafts. Without a matching
   observation, human reconciliation remains necessary; a partner API timeout
   remains blocked from this browser-only reconciliation exception.

## Transactional boundary

We reuse `PostgresWorkspaceRepository._lock_claim_free_draft` with the
existing `FOR UPDATE` workspace lock followed by the fresh sticky-claim
lookup. `edit` remains denied with **any** reserved claim. Only
`report_applied` opts into a narrow exception requiring all of:

- A still-draft, owned workspace and exact expected revision.
- A sticky claim on the same profile/workspace/canonical job.
- A **consumed browser-channel** final approval tied to the same owner,
  reviewed document digest, employer/job identity and revision (not a
  partner-API approval).
- A previously validated owner-scoped browser-observed receipt for the exact
  document digest/revision, still marked **not employer-verified**.
- Explicit final applicant confirmation via the original
  `confirmed_external_application=true` API contract.

This transition is only a **local self-report**, never a new external send.
Browser claim state, original receipt and approval records are not mutated.
The existing partner timeout regression must continue to reject re-report,
even if the applicant supplied an unverified observation without a consumed
browser approval.

## Reuse versus scratch

**Reused, not rewritten:** original SP15a sticky PostgreSQL claim, original
SP15e final approvals/action-scope ledger, SP26 browser companion, SP15
receipt/owner hash and URL validation, `report_applied` workspace transition,
SP25 application agent status reconciliation and original first-party OIDC
identity.

**New:** narrow browser receipt/approval predicate in the original locked
workspace write, reconciliation UI state and guarded prompts, and targeted
PostgreSQL OIDC + React tests. No extra database tables, new browser adapter,
model calls or third-party dependencies.

## Acceptance evidence required

- Synthetic PostgreSQL OIDC test: reserve one browser claim; editing blocked;
  reporting before receipt blocked; import matching visible receipt; other
  identity denied; explicit owner report succeeds as self-reported; claim
  stays consumed; official partner receipt count unchanged.
- Existing uncertain partner API test: cannot re-report or retry.
- Frontend React: saved uncertain attempt blocks new packet/edit; observed
  receipt import remains accessible; no report before receipt; confirmation
  requires explicit applicant action; never invokes employer API.
- Exact-head GitHub CI, merged-main GitHub CI and native ObumDelivery
  qualification remain separate gates.
- **Production:** no assertion of a live release, working ZITADEL owner login,
  real job submission or genuine employer acknowledgment without actual OVH
  and authorized employer receipts.

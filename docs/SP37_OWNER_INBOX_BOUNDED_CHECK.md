# SP37 — Applicant-requested bounded Agent Inbox check

**2026-10-25 | Baseline:** SP36 merged
`main@e96a0bc9ebb607bb0ce0c511c31cd74672f5df8c`.

**Plan subsection:** SP21 P0-B guided CV-first application lifecycle;
Agentic SmartPloy Gate 1 per-application followup, candidate action inbox.
This is a direct functional follow-on to SP34 exact-case Check Now, SP35
prioritized Agent Inbox and SP36 OVH worker activation. It does **not**
replace the separately permissioned employer submission path.

## Previously built vs this change

SP34 already allowed candidates to open an individual agent and click
**Check agent now**, using the shared PostgreSQL worker's idempotent
`process_due(profile_id=owner, agent_id=case)`. SP35 listed *all*
owned cases by status change and due date, but presented only
**Open application** on each row. An applicant with several due or
changed jobs still had to navigate through each application's document
editor, click each agent card, and return to the inbox repeatedly.
Meanwhile an operator-disabled background worker meant there was no
owner-initiated bulk maintenance option.

SP37 adds **Check due agents** directly in that inbox. One
applicant-initiated click inspects a **maximum of 10 cases**, not an
unbounded queue. It reconciles only actual saved submission-status
changes and existing due in-app reminders. It does **not** draft or
send recruiter messages, submit CVs, contact a website, use ObumAI,
claim a background run, infer replies or mark an application sent.

## Reuse-first implementation evidence

- `PostgresApplicationAgentRepository.check_due_inbox` first uses
  existing SP35 `inbox(profile_id, limit=10, offset=0)` for
  deterministic server-side priorities. It only selects
  `active` items with `attention_state=status_changed` or
  `due_review`; paused, closed, future-due, draft-only or
  awaiting-response cases are ignored.
- For each selected existing case, it invokes the **original SP34**
  `process_due(limit=1, profile_id=owner, agent_id=...)`.
  That exact-owner/case SQL scope, `FOR UPDATE SKIP LOCKED`,
  event sequencing, reconciliation, and transaction-level next-due
  update are already tested. No change to the global worker,
  `_case_scope`, event types, SQL table or scheduled cadence.
- A follow-up read of the same owner-scoped inbox reports whether
  more actionably due cases remain. A second click is permitted; there
  is no background loop and no implied promise all cases were handled.
- New API `POST /api/v1/application-agents/inbox/check-due` is
  registered **before** the dynamic `/{agent_id}` routes. It
  uses the original `application_agent_context(mutate=True)` to
  require signed-in OIDC identity, the exact initiating user ID,
  same-origin and CSRF policy before touching any case. No user-supplied
  agent IDs or unbounded pagination are accepted. Private, `no-store`
  response reports only aggregate counts and policy-false booleans.
- React `ApplicationAgentInbox` now offers an explicit action only
  when current server-provided rows contain due/changed active cases.
  It has a single-flight guard, validates the original signed-in
  account **before and after** the POST, refreshes the actual saved
  priorities, suppresses old-account results and tells applicants
  exactly how many private reminders and status changes were recorded.
  It never claims recruiter communication or scheduler activation.
- The original Studio passes the initiating `expectedUserId`
  rather than deriving an identity from email or job metadata.
  All existing individual case actions, document revisions, dirty
  edit guards and browser final-submit authorization are unchanged.

**Original code reused:** owner-bound durable case/agent registry,
in-app reminder transitions, career-ops followup cadence already
integrated, SP34 read-only/single-case action, SP35 sorted inbox,
signed-in OIDC policy + CSRF, React Studio and fetch wrapper,
PostgreSQL fixture and same-email/two-OIDC-subject tests.

**Code newly written:** one small orchestration method, one first-party
endpoint, one typed client function, one inbox button + status message,
responsive styles and focused regression tests. No new framework,
dependencies, migration, provider integration, shared daemon or
separately copied source code. Time saved by reuse was not measured.

## Mandatory acceptance and safety tests

1. **Real PostgreSQL:** owner with 12 due cases gets 10
   `review_reminder_due` events from the first click, the remaining
   two on the second click, and no duplicate on the third. Another
   account's case is untouched. Invalid owner/limit fails closed.
2. **Saved real applicant state:** personally self-reported application
   is reconciled first, and its followup schedule moves forward
   without falsely recording an immediate recruiter reminder. Paused
   agents are excluded.
3. **Concurrent clicks:** two parallel invocations of the original
   per-case engine cannot create duplicate in-app events.
4. **Production-mode synthetic OIDC HTTP:** two different authenticated
   subjects with **the same email** remain isolated. Wrong user,
   cross-origin and cross-site mutations fail; authorized counts
   return private `Cache-Control: no-store`. Zero employer
   submit claims created.
5. **React and typed HTTP:** valid initiating account header required,
   no client-selected case list/POST body, no second click while first
   one is pending, priorities are refreshed, stale result hidden after
   a cookie change, and paused/waiting cases do not offer the action.

## Explicit deployment and autonomy boundaries

The source change requires 5/5 exact-head GitHub CI before merge, 5/5
independent merged-main push CI afterward, **native ObumDelivery**
exact-SHA qualification, and owner-approved OVH deployment and signed-in
acceptance. GitHub CI's synthetic Docker smoke is **not production**.

The public Komplyint service's `/healthz` observed on this date
still lacks the source's newer `release_revision`, even though the
PostgreSQL and worker infrastructure report ready and unauthenticated
private endpoints are protected. Do not infer SP37 (or SP24–SP36) is
running on OVH from a public `ok=true` response.

`SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED=false` remains the default;
bulk agent checks are **not** job applications. Real employer
submissions require independent employer-specific rights, applicant
review, one-use authorization, and independently verified receipt.

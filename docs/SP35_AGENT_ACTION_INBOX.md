# SP35 — Private application-agent action inbox

**Baseline:** SP34 main `c9d4944dcf4d5ccb8373160f39624716cf7c3e8c`.
**Plan:** Agentic SmartPloy master plan, candidate-visible application
priorities, per-case status and a bounded persistent action inbox.
**Priority:** Improve the ACTUAL CV-first AutoApply review experience,
not a second tracking service or an unverified production claim.

## Confirmed gap

SP32 binds a durable Agent Zero to an explicitly selected application and
SP33 can create the same agent from separately opted-in background matches.
SP34 lets the signed-in applicant check an exact case on demand. Yet the
My Applications page only shows a flat saved-workspace list. A candidate
with dozens or hundreds of cases must open every draft to learn which has
a changed submission status or is due for private review; no effective,
prioritized cross-case view exists. The original `getApplicationAgents`
returns only the most recently updated 100 cases, not the next relevant
actions. An old due case could be omitted entirely.

## Core implementation

The existing `PostgresApplicationAgentRepository.inbox` reads the original
case/workspace tables through its existing `_COLUMNS` owner-scoped join.
It orders cases by **recorded facts only**:

1. **Submission status changed**: a saved application state differs from the
   last worker-observed workspace status. This is a pending *in-app*
   reconciliation, not employer confirmation.
2. **Due review**: an active case has `next_due_at <= now`. It does NOT
   imply a reminder was delivered, that a background worker is alive, or that
   an employer responded.
3. **Draft review**: active but unsent, not yet due.
4. **Awaiting response**: an existing submitted/self-reported case is active
   and no in-app review is due. Employer-acknowledged and user-reported
   statuses remain distinctly labeled.
5. **Paused**, then **closed** agents. Neither is reactivated.

The SQL still filters by exact private profile ID and account-erasure
quarantine. It uses the original owner+case ID, stable tie-breakers, and
bounded, deterministic `limit`/`offset` pages. It queries only
`limit+1` rows, exposing whether another page exists rather than
mistaking the first 100 latest agents for the entire pipeline. No new table,
database column, source connector, model request or employer action.

The new first-party
`GET /api/v1/application-agents/inbox?limit=25&offset=0`
uses the original authenticated `application_agent_context(request)`.
Every response has `Cache-Control: private, no-store`, sanitized
case metadata only (no CV text, email address or attachment), and explicit
`background_worker_verified=false`,
`external_actions_authorized=false`.

**Application Studio** now shows an accessible responsive Agent Inbox
above the existing editor. It lists server-prioritized cases, the original
next due date, honest submission provenance, Refresh and Load more, and
**Open application** for each case. Selecting a listed case reuses the
existing dirty-edit confirmation and case-local agent card.
If the case is older than the ordinary workspace list, the UI uses the
already available owner-bound `GET /api/v1/application-workspaces/{id}`
with account verification **before and after** the request. An async
account switch or a second selection invalidates the old response. An
older selected case stays available on workspace refresh.

The inbox is read-only. It never creates an application, wakes another
agent, sends an employer form, emails a recruiter, performs AI inference
or accepts/declines a job offer. The original SP34 **Check agent now**
button remains where the candidate must explicitly open their own case.

## Reuse versus scratch

**Reused:** original PostgreSQL `smartploy_application_agents`,
`smartploy_application_workspaces`, original `_COLUMNS` and
`_public` serializer, owner scope/erasure checks, one agent per
workspace, existing `getApplicationWorkspaces`, exact-case read API,
signed-in OIDC account re-verification, original `pick` unsaved-draft
guard, Agent Zero card, standard frontend styles, synthetic two-identity
OIDC/PostgreSQL test harness.

**New:** one bounded read-only repository query with priority labels and
pagination; one read-only API route; a small typed React inbox and style
rules; careful older-case selection glue; focused regression coverage.
No dependencies, migrations, new background workers, external adapters,
separate agent process or second application store. Elapsed time saved by
reuse has not been measured.

## Acceptance gates and test coverage

- Actual PostgreSQL: six distinct owner cases prioritized as status-changed,
  due, draft-review, awaiting, paused, closed; stable two-row pages and
  deterministic `next_offset`; another account's case excluded; blank
  owner/invalid pagination denied; erasure quarantine returns no case data.
- Synthetic production-mode two-subject OIDC HTTP fixture with same email:
  correct owner sees only their case; other subject sees zero; unsupported
  query limits 422; response private/no-store; no CV/email content or
  employer claim generated.
- React: due label, correct-case navigation, explicit loading/refetch,
  bounded paging, refresh resets old rows, unavailable agent store not
  mislabeled as empty; a switched account cannot publish an in-flight GET.
- Studio: inbox links to already saved draft with no mutation; older
  private case uses exact owner GET and survives Refresh; account swap
  rejects delayed old-case data. Typed API tests confirm no body/mutation.
- Full exact PR-head and merged-main GitHub checks required before claiming
  source complete. The `deploy-stack` check is only synthetic Docker
  build/smoke, not an OVH release.

## Known operational and permission boundaries

The operator still must separately qualify the exact SHA through native
ObumDelivery and deploy to OVH. The production `main` source SHA, running
image provenance, ZITADEL two-account acceptance, source freshness,
scheduled background Agent Zero wakeup, and a genuine permissioned employer
submission acknowledgment require actual live evidence.
`SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED` remains OFF by default.
A due reminder **never** means a recruiter has been contacted. Nothing
in SP35 enables automated external outreach.

**Source tests only do not equal a deployed or fully automatic job hunter.**

# SP34 — Owner-scoped on-demand application-agent check

**Plan:** Agentic SmartPloy Gate 1, SP21 CV-first application lifecycle,
SP22–SP25 private Agent Zero follow-up and submission reconciliation.
**Baseline:** `main@64d8bdade684892f2bc343159ba64a539c4aa225` (SP33).

## Why this is a core feature

SP32 attaches one private Agent Zero to every explicitly selected job, and
SP33 extends that same case creation to separately opted-in background
matching. The case repository already has a crash-safe, due-time, owner-scoped
in-app reminder engine. However, recurring wakeups depend on a separately
configured OVH worker (`SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=true`), which
has **not yet been proven enabled in production**. Applicants currently see
an agent with no obvious way to process a due reminder when that worker is off.
A recent self-reported submission can also remain visibly
`observed_workspace_status=draft` until a scheduled worker tick.

**SP34 adds an explicit, useful first-party action:** an applicant can select
one saved job and click **Check agent now**. It immediately reconciles that
case's saved application status and, if a reminder is actually due, persists
one in-app reminder. It is not a browser-closed background process and never
reaches a recruiter or employer.

## Exact original-code reuse

- `smartploy/application_agents.py`:
  - Original `PostgresApplicationAgentRepository.reconcile_workspace_updates`
    (real saved application status, no fabricated provider acknowledgment).
  - Original `process_due`, `FOR UPDATE ... SKIP LOCKED`, atomic revision,
    due-time update and immutable activity event.
  - Original `next_case_due`, `due_message`, human follow-up stage logic,
    existing erasure quarantine, pause/close and private per-user case IDs.
  - Existing **global shared scheduler** uses unchanged, unscoped method
    calls, with no new worker, migration, daemon, external queue or
    submission adapter.
- `smartploy/api.py`: original OIDC/Cloudflare `tenant_context`,
  `application_agent_context(mutate=True)` initiating user, same-origin and
  CSRF preconditions, original per-agent `get`/events.
- `web/src/ApplicationAgentCard.tsx` and `api.ts`: existing owner
  verification before/after HTTP mutations, selected case and activity
  refresh. Same method and original setup, not a new agent UI product.
- Original PostgreSQL worker, OIDC browser-final synthetic two-subject
  fixture, React and typed API test harnesses.

## New components (minimum necessary)

1. Fixed-code SQL scope helper `_case_scope(profile_id, agent_id)`.
   Both parameters are required together; neither is interpolated into
   SQL. The original global worker passes neither, preserving current
   behavior. Owner on-demand check passes **both** to the original
   reconcile and due-query, with `limit=1`.
2. `POST /api/v1/application-agents/{agent_id}/check-now` uses the original
   account-bound mutating route policy. It requires an existing **active**
   case owned by the authenticated profile, triggers the exact-case engine,
   then retrieves the latest owner-bound case. Returns only the private
   updated case and event **counts**, plus explicit
   `external_actions_performed=0`, `employer_contacts=0`,
   `background_worker_verified=false`. Response is private/no-store.
3. Application Studio has **Check agent now** only for active cases, plus
   truthful messages: reminder saved, case status updated, or no update
   due. Account identity is verified before **and** after the POST; the
   activity panel reloads with its existing request.
4. Focused PostgreSQL OIDC and React tests verify the real transaction,
   ownership, absence of provider calls and user feedback.

## End-to-end acceptance

- Real Postgres: two different private profile IDs with the same job can
  exist; A's request for B's case cannot wake it; A's due case generates
  one `review_reminder_due` event even under concurrent requests; repeat
  requests generate zero additional events.
- Original global worker remains able to process B afterward.
- A real already-saved `self_reported_applied` status is reconciled first
  with an `application_self_reported` event, moving the next due time to
  the submitted-first cadence. A user check must not immediately generate
  `followup_due` for a just-submitted application.
- OIDC HTTP: two accounts with same email cannot read/trigger one another's
  case; missing initiating-user precondition and cross-origin/cross-site
  requests fail; paused/closed cases do not wake; an authorized case check
  has no employer claim, body containing private CV, automatic sender or
  provider acknowledgment.
- React: no check without a user gesture; Check button is available for
  active cases only; no button when paused; failed signed-in re-verification
  never dispatches the request. Replies distinguish due vs not due without
  suggesting a background worker tick has run.

## Release and user-experience boundary

**Source-gate required:** exact pull-request head full GitHub Actions and
exact merged-main GitHub Actions after a green merge.

**Native production gates still independent and blocked:** Woodpecker
ObumDelivery exact-SHA qualification, authorized OVH release/running image,
real signed-in ZITADEL two-account browser acceptance, enabled source worker,
and agent wake after the browser closes. A successful GitHub
`deploy-stack` job only proves synthetic Compose build/smoke, not OVH
deployment. `SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED` remains OFF unless
separately authorized. No employer application or follow-up is sent by SP34.

**No invented savings:** Reuse avoids creating a second scheduler and event
system, but elapsed engineering-time savings are not independently measured.

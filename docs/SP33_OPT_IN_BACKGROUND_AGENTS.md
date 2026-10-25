# SP33 — Separate opt-in background job hunter agents

**Plan subpart:** Agentic SmartPloy Gate 1 + SP21 CV-first AutoApply,
*one reviewed real job → one owner-bound durable case*.

**Previous stage:** SP32 allows the candidate to explicitly select a batch of
jobs and create one logical in-app agent per job. The preexisting opted-in
background worker can independently discover current suitable IT roles and
prepare private drafts, but it did not create any per-job agents: tracking
required extra manual clicks in each workspace.

**Implemented in source:** A separate *background agent tracking* opt-in
(on top of the existing automatic draft opt-in) now binds Agent Zero to
eligible owner-scoped application drafts. This is permission to make local
in-app records only; it is **not** permission to submit an application or
contact an employer.

## How it works

1. The applicant opens the existing personalized Search settings, chooses
   explicit target roles and enables automatic private drafts. An independent,
   initially unchecked option permits **private application-tracking agents
   for matching saved drafts**. This is clearly not a recruiter contact or
   automatic form submission permission.
2. The preference is stored in the existing **revisioned JSONB criteria**
   (`auto_agent_tracking_enabled=true`), with the normal signed-in OIDC
   user/Origin contract and strict boolean validation. No database migration
   or second consent store was added. General search and draft opt-out
   automatically disable the agent opt-in; backend rejects agent=true without
   draft=true. Existing users remain false after upgrade.
3. Original background job matching still enforces current trusted employer/
   official source, recently verified snapshot (up to 48 hours), open deadline,
   safe HTTPS destination, explicitly targeted role, mandatory-gap check,
   approved profile facts and current CV. No unreviewed source or driver role
   gains automatic draft authority.
4. Immediately before every write the original
   `PostgresSearchPreferenceRepository.auto_draft_guard` locks the
   owner/revision and checks revocation and account-erasure quarantine. Under
   **the same guard**, after the existing
   `PostgresWorkspaceRepository.create_or_get`, the original
   `PostgresApplicationAgentRepository.create_or_get` creates/reuses the
   per-job private case. This respects SP31's duplicate-safe agent ID and
   does not add a second scheduler or worker.
5. Case creation remains bounded by the original three-per-profile scan.
   Existing paused/closed agents stay paused/closed. A second worker scan
   reuses the exact agent ID and event, creating no duplicate. Neither
   the draft nor the agent sends anything.
6. The existing **immediate** `/api/v1/auto-draft/prepare` endpoint now
   passes the already-configured application-agent repository, so applicants
   who opt in can see cases appear on the first scan rather than only after
   a later worker tick. The shared worker does the same if the operator
   enables its existing independent task.
7. Results expose **counts only**: agents started, already present and
   unavailable. If agent storage fails, preserve the saved private draft,
   show agent unavailable, and never pretend that tracking or worker wakeups
   succeeded. No CV, name, email or job URL appears in aggregate output.
8. The original Agent Zero follow-up cadence and candidate-reported outcomes
   are unchanged. Background reminders require the **separate** operator
   `SMARTPLOY_WORKER_AGENT_ZERO_ENABLED` flag, migrations 025–027 and
   actual OVH worker acceptance. New agents do not imply the worker ran.

## Reuse first, scratch second

**Reused existing code:**
`smartploy/auto_draft_shortlist.py`, `smartploy/search_preferences.py`,
`smartploy/search_preference_storage.py`, `PostgresWorkspaceRepository`,
`PostgresApplicationAgentRepository`, the original owner/revision
`auto_draft_guard` and erasure protections, the existing job scoring, CV
and approved facts, `api.py` authenticated private action, existing
shared `worker_runtime.py`, `SearchSetup`, and the PostgreSQL/React
CI fixtures.

**New glue:** one independent strict default-off preference bit and setting,
bounded conditional agent call in the existing auto-draft scan, truthful
aggregate counters and user-facing notice, test cases and this evidence
record. **New migrations, standalone services, third-party packages, and
employer submitters: zero.** Engineering time saved by reuse was not measured.

## Explicit limitations and safety conditions

- Per-job agents begin as **local cases**, not autonomous permissioned
  browser identities or employers' agents; no CV forwarding, emails, calls,
  or employer submissions are performed by this change.
- Older workers remain idle when the operator flag is off; a created case
  is not proof of active background reminders.
- Turning off background tracking prevents **new** cases after any
  in-flight preference-locked transaction finishes; already-created cases
  remain in My Applications until individually paused/closed/deleted.
- No recruiter response, employment outcome or application acceptance
  may be inferred from a case record, an auto-draft or a browser click.
- The original source/authorization freshness policies and sticky
  one-employer-attempt ledger are preserved without modification.
- The three-per-profile cap is bounded per background scan. The shared worker
  controls total profiles, retries and cadence through its existing
  task configuration.
- Manual/assisted preparation continues to create documents without
  starting a background agent. SP32's candidate-selected batch API retains
  its own explicit in-app tracking authorization.

## Mandatory tests and release evidence

**Python memory and PostgreSQL:** default-off draft-only path; explicit
agent=true rejected unless draft=true; strict Pydantic bool; two accounts
with same email receive different profile/case IDs; exact one agent/event
per eligible workspace; repeat scans reuse; revocation stops new agent
writes; agent DB failure preserves the draft and reports unavailable;
aggregate count has no private profile data.

**Web/React:** separate agent checkbox disabled until draft opt-in; defaults
false; draft opt-in alone remains agent=false; agent true saved/reloaded
correctly; disabling draft/general search revokes both; applicant sees
truthful agent count and disabled worker disclaimer.

**Delivery:** GitHub CI at exact PR head and actual merged-main SHA; native
ObumDelivery Woodpecker CI with negative control; guarded OVH production
exact source SHA and running image; ZITADEL two-account acceptance; actual
source freshness and a browser-closed worker wakeup with no external action.

Status to be filled from actual CI/merge receipts; **source-only work
is not an OVH deployment**. Final one-use browser submission remains
operator-off by default, subject to separate employer rights and consent.

# SP25 — Agentic SmartPloy status-to-case reconciliation

**Date:** 22 October 2026  
**Plan:** Agentic SmartPloy Gate 1/2 operational correctness; prerequisite for safe AutoApply completion tracking.  
**Project baseline:** SP21 CV-first, SP22 durable Agent Zero and SP23 candidate follow-up/outcomes already merged into main before this branch.

## User problem fixed

Previously the background agent could be created while an application was still
a draft, with a reminder due one day later. If the person then submitted the
application, that old reminder could wake and immediately suggest emailing the
employer—even though the application had just been sent. Similarly, a later
genuine Lever provider acknowledgement was not recorded as a distinct,
provenance-labeled case event.

SP25 consumes **the original application workspace status**, in a separate
bounded worker phase **before** suggesting the next follow-up:

- `draft → self_reported_applied`: one private `application_self_reported`
  event with explicit *applicant report, not externally confirmed* status;
  calculate first follow-up from actual recorded application time plus the
  existing career-ops seven-day cadence.
- `draft → provider_acknowledged`: one private
  `application_provider_acknowledged` event; first review from actual
  provider-status update time. This is **not** an employment/hiring decision.
- `self_reported_applied → provider_acknowledged`: upgrade provenance but
  retain previously scheduled follow-up; never restart a count or outreach.
- Unexpected status reversal: one `application_draft_review` event,
  review-only reminders and zero employer action.
- Paused, closed or account-erasure-quarantined cases: no reconciliation or
  follow-up activity until authorized resume; closed remains terminal.
- Two concurrent worker processes cannot insert the same event: reuses
  PostgreSQL `FOR UPDATE ... SKIP LOCKED` plus the original event sequence and
  revision transactions.

The UI distinguishes the original workspace status from the last worker-seen
status, so pending synchronization does not masquerade as a provider receipt.
No external employer action, email, phone, CV forwarding or ObumAI call is
triggered by this change.

## Exact first-party reuse

- `smartploy/application_workspace_storage.py` + migration 023:
  immutable owner-bound application record, distinct draft, personally reported
  submission and provider-acknowledged states. No new application store.
- `smartploy/application_agents.py` + migrations 025/026:
  owner-bound case, event sequence, pause/close controls, due timer; extended.
- `smartploy/application_followups.py`: previously imported MIT career-ops
  first-follow-up and status check cadence, with original license notice at
  `docs/third_party/CAREER_OPS_MIT_NOTICE.md`. No additional external package.
- `smartploy/worker_runtime.py`, `worker_schedule.py`: existing bounded
  optional Agent Zero task; **no new daemon or always-on process**.
- `web/src/ApplicationAgentCard.tsx`, `types.ts`: existing authentic
  account-scoped UI and case timeline, augmented to show pending sync.

## New code absent before SP25

- Migration `027_application_agent_submission_state.sql`: durable
  `observed_workspace_status`; backfills only missing values to avoid
  repeatedly overwriting status observation after restarts/migrations;
  extends allowed audit event types.
- `reconcile_workspace_updates()`: one bounded, duplicate-resistant
  transactional claim per changed real workspace, which updates the old case.
- `process_due()`: first reconcile workspace truth then run ordinary due
  events, preventing an old draft deadline from leaking into new application
  scheduling. Operator opt-in remains unchanged.
- Synthetic PostgreSQL regression fixtures prove no early follow-up, two
  worker claims one event, later provider status distinct from self-report,
  post-provider cadence not restarted, pause/close/erasure safeguards, and no
  external send or false hiring counts.

## Release gate

Required: exact-head GitHub Python/Postgres tests, web/TypeScript, synthetic
Chromium, Docker fixture and review receipt. **No source-only run counts as
OVH deployment.** Apply migrations 025, 026 and 027 in that order, using the
original guarded migration, backup and restore process. Enable the existing
agent worker switch only after operator-controlled host acceptance. Verify one
browser-closed draft→applied case and one authorized partner acknowledgement
with real source status before calling it production-ready.

## Still outstanding

- Exact OVH source SHA, native ObumDelivery source/negative CI and release
  approval, signed-in ZITADEL two-account QA.
- Confirmed allowed provider rights and actual send receipts across each
  supported employer form.
- Unrestricted autonomous browser final submit on arbitrary ATS sites is **not**
  supported and must not be represented as complete.
- Scoped read-only ObumConnect recruiter inbox and explicitly consented
  ObumAI case-specific reasoning are separate next gates.

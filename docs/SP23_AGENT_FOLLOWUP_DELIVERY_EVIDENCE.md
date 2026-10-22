# SP23 — Agentic SmartPloy Gate 2A: candidate follow-up and stage outcomes

**Date:** 22 October 2026  
**Project plan subpart:** Agentic SmartPloy Master Plan Gate 2 (candidate-side events and follow-ups)  
**Delivery state:** Source implemented on PR #184; exact-head CI, merge and production receipt must be verified separately.  
**Parent:** Gate 1 Agent Zero was merged as PR #182. No second worker, CV engine, sender, login or application tracker has been introduced.

## What the applicant can now do

Inside the **existing Application Studio** for one job:

1. Start/resume the durable application agent originally introduced in SP22.
2. Read the workspace submission provenance (draft, personally reported applied, or acknowledged by an authorized provider).
3. After the application is recorded as sent in the **original workspace**, review a candidate-side follow-up draft and copy/edit it in their own email app. The draft does not address or contact an employer automatically.
4. Explicitly attest **I sent a follow-up myself** (maximum two routine outreach logs per case), which updates an in-app schedule. There is **no external delivery acknowledgment** for user-reported sends.
5. Explicitly report recruiter reply, interview, offer, rejection, or accepted employment. Each milestone is labeled `candidate_self_report`, not a provider-verified outcome. The user must check the attestation checkbox and terminal outcomes require a second confirmation.
6. Reporting rejection or having accepted employment atomically closes the agent and cancels its next wake. Pause, resume, manual close and erasure quarantine still work.
7. Per-workspace case lookup uses an indexed query rather than scanning a capped list of 100 agents.

The same Postgres worker produces event-specific, owner-only reminders. A draft receives a draft review event; a sent application may receive a follow-up suggestion; after two logged follow-ups, the agent switches to status-only review. Interview/offer create review reminders. No job application, email, phone call, calendar update or ObumAI text job runs as a result of this implementation.

## Reused exact code and source evidence

| Source | Reused component | Result |
| --- | --- | --- |
| [career-ops/followup-cadence.mjs @ dff9703](https://github.com/career-ops-hq/career-ops/blob/dff9703a092e2872245aef09b096edcee054ac69/followup-cadence.mjs) | `DEFAULT_CADENCE` constants; applied, responded and interview scheduling branches of `computeNextFollowupDate` | Actual MIT-licensed adaptation in `smartploy/application_followups.py`; [MIT notice](third_party/CAREER_OPS_MIT_NOTICE.md) preserving copyright |
| `smartploy/application_agents.py`, `migrations/025_application_agent_zero.sql` | Existing logical agent, sequence-based event ledger, Postgres locking, create idempotence and owner scoping | Extended, not replaced |
| `smartploy/worker_runtime.py` and `worker_schedule.py` | Shared optional leased worker task | Calls extended `process_due()` without introducing another runtime |
| `application_workspace_storage.py` and `migrations/023_provider_acknowledged_workspace.sql` | Real first-party submission status and origin | Required for outcome and follow-up reporting |
| `api.py`, `oidc.py`, `identity.py` | Existing tenant identity, same-origin and stable-user guards | All mutations reuse existing verified account context |
| `web/src/ApplicationStudio.tsx` and `api.ts` | Original UX/editor and verified private mutation method | Reused for in-app draft, status and event UI |

The upstream project is written for Markdown trackers and Node. It was not appropriate to import the entire CLI and app. Only the applicable cadence branch was ported into the existing Python/PostgreSQL architecture. The no-send, self-report source gate, per-case receipt distinction, erasure behavior and bounded rechecks are **original SmartPloy-specific work**.

## Added code, tests and migration

- `migrations/026_application_agent_followup_outcomes.sql`: existing case status extended with `milestone`, `followups_sent`, `last_followup_at`; additional event vocabulary and terminal close constraints. Migration is idempotent under existing ordered migration runner.
- `smartploy/application_followups.py`: reviewed and attributed source adaptation plus privacy-safe text template.
- `smartploy/application_agents.py`: owner-only, revision-checked milestone and self-reported follow-up transactions, no duplicate events, source-gated due wakeups, indexed workspace lookup.
- `smartploy/api.py`: two explicit attestation endpoints plus owner-only direct workspace-agent read. No raw employer emails can be submitted into these endpoints.
- `web/src/ApplicationAgentCard.tsx`, `types.ts`, `api.ts`: status-dependent guidance, explicit candidate-reported milestone and follow-up affordances, copyable review draft; existing account verification before/after private mutations.
- `tests/test_application_followups.py`, `tests/test_application_agents.py`, `web/src/ApplicationAgentCard.test.tsx`: cadence parity, durable owner binding, unsent-draft refusal, stage order, stale revision, terminal no-wake, source provenance, max two, no-send contract and React controls.

## Deployment and acceptance gates

1. Confirm PR #184 full exact-head GitHub CI: Python/Postgres, web, browser, Docker fixture and exact-checkout review receipt.
2. Merge to main only if all gates pass and there are no new unexpected branch modifications.
3. Obtain a separate native ObumDelivery approval and exact OVH source SHA; apply migrations **025 then 026** in the guarded existing migration process before enabling worker case tasks.
4. Turn on existing `SMARTPLOY_WORKER_AGENT_ZERO_ENABLED` only after migrations; no additional external-sender flag is provided.
5. Signed-in OVH acceptance: submit/record one sample application, create agent, close browser, observe one in-app due event on reopening, record recruiter reply, confirm outcome, verify terminal stop, test distinct user identity and paused state.
6. Measure upstream integration engineering minutes and actual live due-task latency before claiming speedup.

**Not delivered in this subpart:** ObumConnect mailbox OAuth/read-only inbox, true recruiter email source verification, automated reminder email or phone, ObumAI model classification, employer ATS final actions, permission to use browser submissions, calendar synchronization, native OVH rollout receipt. Do not describe a submitted application based on a user's follow-up event.

## Next targeted source-reuse task

Evaluate `career-ops/reply-matcher.mjs` and `reply-watch.mjs` at the same pinned MIT commit together with current ObumConnect read-only OAuth scopes. Build only the missing **safe message-to-one-application matching** boundary using synthetic recruiter message fixtures, sender-domain/role validation, prompt-injection resistance, and explicit owner confirmation. No inbox access or auto-send is authorized by this plan.

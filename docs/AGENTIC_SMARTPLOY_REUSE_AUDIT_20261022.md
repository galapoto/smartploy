# Agentic SmartPloy — reuse audit and architecture decision record

**Date:** 22 October 2026. GitHub stars, licenses and source paths were read from public primary repositories on this date.  
**Status:** Research and source-code inventory; Agent Zero now merged to main via PR #182. No third-party runtime imported and no native OVH agent deployment verified.  
**Related plan:** [Agentic SmartPloy Master Plan v1.0](AGENTIC_SMARTPLOY_MASTER_PLAN_V1.md)

## Decision ADR-ASP-001: the appropriate agent type

**SELECT:** one durable, event-driven *application-case agent* per selected job application, coordinated by one candidate-level career coordinator, with shared bounded workers and specialist ObumAI tools. An agent is persistent state and an event/timer subscription, not an always-running LLM. No model or child agent may mint its own external-action permission.

**RETAIN:** SmartPloy's existing PostgreSQL canonical job, profile, CV, owner-scoped application workspace and continuous worker. Reuse ObumAI Core's bounded text-job runtime, Browse browser observations, Connect scoped integration and Speech future applicant opt-in voice. The original ObumAI durable text-job API has external actions disabled; a separate SmartPloy grant and audit gateway must mediate all consequential operations.

**FIRST EXTERNAL DOMAIN CODE:** career-ops (MIT). Its recruiter-response triage, follow-up cadence, candidate evidence and outcome modes most directly match the new responsibilities. Read open-apply (MIT) alongside it for state/guardrail fixtures; do not build a second CLI tracker or replace existing SmartPloy storage.

**OPTIONAL REASONING GRAPH:** Evaluate LangGraph (MIT) in a narrow, fail-closed synthetic human-approval subflow. Compare with Pydantic AI (MIT) and Microsoft Agent Framework (MIT), then choose at most one if it demonstrably outperforms a simple existing ObumAI/SmartPloy worker callback. No new framework is required to ship Agent Zero.

**OPTIONAL BROWSER:** Retain SmartPloy's reviewed companion and ObumAI browser_runtime first. Compare Stagehand (MIT), Playwright MCP (Apache-2.0) and Browser Use (MIT library) on identical *non-submitting* employer-form fixtures. Authorizing a browser tool never confers rights to submit applications to employers.

**FLEET OPERATIONS:** Evaluate Paperclip (MIT) for permission, budget, lifecycle, heartbeat and cost patterns; do not deploy its business-employee control plane as a parallel SmartPloy application backend unless a measured integration pilot proves benefit.

**FUTURE:** Applicant-only disclosed voice calls can evaluate LiveKit Agents (Apache-2.0) or Pipecat (BSD-2-Clause) after ObumSpeech and telephony/legal review.

## Popular repository inventory

Stars are a rough, time-sensitive popularity measure, not proof of quality. The main selection criteria are license, source fit, isolation, deterministic outcomes, compatibility, safety, integration effort, maintenance and real test evidence. Approximate stars below are GitHub repository metadata snapshot readings from 2026-10-22.

| Repository | Stars | License / warning | Fit and decision |
| --- | ---: | --- | --- |
| [n8n](https://github.com/n8n-io/n8n) | 208,327 | GitHub NOASSERTION; fair-code terms | Research connectors; no unapproved embedded copy |
| [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | 187,705 | Mixed/custom; detector NOASSERTION | Entire platform unsuitable for direct transplant |
| [Dify](https://github.com/langgenius/dify) | 159,247 | Custom/mixed; detector NOASSERTION | Do not replace existing ObumAI runtime |
| [LangChain](https://github.com/langchain-ai/langchain) | 148,269 | MIT | Small adapters only where actually useful |
| [Browser Use](https://github.com/browser-use/browser-use) | 118,856 | MIT open-source library; paid cloud separate | Browser benchmark, read/prepare only |
| [Paperclip](https://github.com/paperclipai/paperclip) | 105,989 | MIT | High-relevance fleet controls; adapt patterns selectively |
| [MCP Servers](https://github.com/modelcontextprotocol/servers) | 91,482 | Multiple packages/license check | Protocol examples, not a copied server fleet |
| [career-ops](https://github.com/career-ops-hq/career-ops) | 76,533 | MIT | **Top job-domain reuse candidate** |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 70,967 | MIT; last push Jan 2026 | Coding-company agents, not job case controller |
| [AutoGen](https://github.com/microsoft/autogen) | 61,530 | Metadata CC-BY-4.0; mixed code/doc; README deprecated | **Exclude**, Microsoft directs users to Agent Framework |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 59,984 | MIT | Role-based flows; challenger, not default persistence |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 43,718 | MIT | **Primary optional reasoning-graph trial** |
| [Agno](https://github.com/agno-agi/agno) | 42,863 | Apache-2.0 | Alternate framework, avoid overlapping dependencies |
| [UI-TARS Desktop](https://github.com/bytedance/UI-TARS-desktop) | 39,367 | Apache-2.0 | Future visual browser R&D |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | 38,507 | Apache-2.0 | Non-final browser observation/interaction trial |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | 30,225 | MIT | Lightweight tool orchestration candidate |
| [Alibaba Page Agent](https://github.com/alibaba/page-agent) | 29,544 | MIT | Research in-page DOM agent; not cross-origin submit |
| [Mastra](https://github.com/mastra-ai/mastra) | 29,006 | GitHub NOASSERTION, inspect exact terms | Not a first-choice Python backend |
| [Stagehand](https://github.com/browserbase/stagehand) | 25,780 | MIT | **Primary browser-library challenger** |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) | 23,252 | **AGPL-3.0** | Evaluate only; copying requires AGPL compliance or separate rights |
| [Google ADK](https://github.com/google/adk-python) | 21,961 | Apache-2.0 | Optional competitor |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | 20,790 | MIT | Typed model-neutral reasoning challenger |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | 16,717 | BSD-2-Clause | Future voice trial |
| [LiveKit Agents](https://github.com/livekit/agents) | 14,894 | Apache-2.0 | Future voice/telephony trial |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | 14,271 | MIT | AutoGen successor and workflow trial |
| [Temporal Python SDK](https://github.com/temporalio/sdk-python) | 1,229 | MIT | Consider only if existing scheduler proves inadequate |
| [ResumeSkills](https://github.com/Paramchoudhary/ResumeSkills) | 2,825 | MIT | Candidate-focused templates and fact checks |
| [HackerRank hiring-agent](https://github.com/interviewstreet/hiring-agent) | 7,312 | MIT | **Exclude:** employer-side resume evaluation, different use case |

Additional specialized codebases examined: [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT), [SpaceCorps/open-apply](https://github.com/SpaceCorps/open-apply) (MIT, Rust, application lifecycle), [averatec0773/offeros](https://github.com/averatec0773/offeros) (Apache-2.0), [Aditya-00a/Instaply](https://github.com/Aditya-00a/Instaply) (MIT), [waddington/job-application-tracker](https://github.com/waddington/job-application-tracker) (Apache-2.0), [ZeyadElganainy/Job-Agent](https://github.com/ZeyadElganainy/Job-Agent) (MIT), and [feder-cr/AIHawk](https://github.com/feder-cr/AIHawk). The last project's old bulk applier is retired and pre-Sept-2026 license history differs; do not adopt old bulk-submit code.

**Selection scoring after pass/fail gates:** feature fit 30%; safety, deterministic retries and correctness 25%; existing Python/Postgres/Ollama/ZITADEL integration cost 20%; maintenance/dependency/security 15%; measured performance and total engineering effort 10%. These are selection weights, not benchmark results.

## Exact candidate code to reuse, adapt or avoid

| SmartPloy need | Reusable existing source | External source files inspected / candidate | Decision |
| --- | --- | --- | --- |
| Job discovery and matching | smartploy/sources/public_ats.py; scoring.py; search_preferences.py; worker_runtime.py | career-ops/scan.mjs and modes/scan.md; open-apply/src/sources | **Reuse internal first**, add only source rights/gaps |
| CV facts and documents | smartploy/cv_import.py; cv_storage.py; application_workspace.py and storage | career-ops/verify-cv-facts.mjs and modes/auto-pipeline.md; ResumeSkills | **Reuse**, selectively adapt fact-check tests |
| Application case identity | Existing owner-bound workspace and Postgres repositories | career-ops/modes/outcome.md; open-apply/src/model.rs | **Build only new binding/event state** |
| Wake, retry, pause, close | smartploy/worker_schedule.py; worker_runtime.py; ObumAI text-job pattern | Paperclip/server/src/services/agent-lifecycle.ts, agent-execution-stop.ts, decision-wakeup.ts | **Adapt internal**, learn from Paperclip tests |
| Follow-up cadence | Existing worker timers | career-ops/followup-cadence.mjs; modes/followup.md; open-apply/src/commands/followups.rs | **Adapt**, initially notify only |
| Recruiter reply classification | Existing ObumAI bounded text jobs, owner-scoped OAuth | career-ops/reply-matcher.mjs; reply-watch.mjs; modes/reply-watch.md; open-apply/src/triage.rs | **Adapt** with applicant review and sender verification |
| Applicant action inbox | Existing Application Studio and My Applications | career-ops/agent-inbox.mjs; modes/agent-inbox.md; Paperclip approvals service | **Adapt** to current UI/data, no second CLI inbox |
| Browser steps | SmartPloy browser-companion; browser_handoff.py; ObumAI browser_runtime/workflow.py | Stagehand observe/act/extract; Playwright MCP; Browser Use | **Benchmark**, no uncontrolled submit |
| Model planning | smartploy/obumai.py and ObumAI Core agent-jobs | LangGraph checkpoints/interrupts; Pydantic AI typed outputs; Microsoft Agent Framework HITL | Trial one optional bounded task engine |
| Email/calendar | ObumAI obumellm/connections/manager.py, registry.py | career-ops follow-up and reply modes | **Reuse** grant/preview; build case binding |
| Agent budget and audit | ObumAI dispatch and SmartPloy task trace | Paperclip/server/src/services/budgets.ts and budget-reservations.ts | Adapt policy/fixtures, not whole platform |
| Optional candidate call | ObumSpeech specialist API boundary | LiveKit Agents or Pipecat | P2; not built today |

**SmartPloy-specific code that truly must be built:** the atomic one-per-case agent record binding, case-specific immutable events and transitions, recipient-and-case bound action-grant gateway, employer/provider receipt reconciliation, case-safe recruiter mailbox associations, candidate-visible agent activity and consent controls. These are narrowly defined integration components, not a new AI stack.

**Do not rebuild:** job source pollers, profile/CV schema, application documents, first-party login, ObumAI reasoning provider, existing browser observations, basic OAuth vault, CI/CD or Postgres scheduler.

### Licensing rule

Import requires a pinned source revision, explicit license review, kept notice/attribution, transitive dependency assessment, security scan, public fixture tests and release receipt. **Modifying AGPL/custom-licensed code does not convert it to MIT.** SaaS/network obligations and source policy require independent legal assessment. A video tutorial is a clue, not a license.

## Video reference audit — original conversation leads

Previously named tutorials were investigated against their public video metadata and canonical upstream GitHub repositories:

| Video lead | Verified provenance | Upstream source and usable insight |
| --- | --- | --- |
| [Automate Web Forms with AI Agents — Browser-Use Python Tutorial 2025](https://www.youtube.com/watch?v=yZDj9wK5bXE), Mohamed Naji Aboo | YouTube page/description found; dated 2025-08-12 | [browser-use/browser-use](https://github.com/browser-use/browser-use); Python web form example, not a production employer-submission credential |
| [Playwright MCP: How AI Agents Can Control Your Browser](https://www.youtube.com/watch?v=2716IUeCIQo), Playwright | YouTube page/description found; dated 2025-03-28 | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp); DOM/accessibility actions, controlled browser fixture |
| [Give your AI a browser with Stagehand](https://www.youtube.com/watch?v=zGR6TDKTeGo), Elie Steinbock | YouTube page/description found; dated 2025-06-13 | [browserbase/stagehand](https://github.com/browserbase/stagehand); observe/act/extract/agent with explicit steps |
| FREE Skyvern Web Browsing AI Agent Beats Claude Computer Use?!, Josh Pocock | Secondary indexed title/creator/date found via [video index](https://www.damoa.ai/services/video/410?video=GxsJmOnl6GE), dated 2024-10-26. **Direct YouTube watch URL not independently verified.** | [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern); feature comparison only due AGPL obligations |
| Earlier TikTok-indexed career-ops, Page Agent and UI-TARS demonstrations | **Direct playback/creator URLs not verified; original TikTok pages blocked.** | Primary GitHub repositories verified independently. No claimed video-to-exact-commit mapping. |

**Directly found original YouTube pages: 3. Secondary video listing: 1. Verified direct TikTok clips: 0.** Some YouTube search descriptions replace actual outbound code links with the word URL; the projects were therefore verified independently through their canonical repositories, not by inventing video-linked code.

## Comparable frameworks — what actually controls a job agent

**Primary system:** SmartPloy durable application case with existing database/worker + ObumAI bounded reasoning. This best preserves application truth and owner isolation while introducing minimal dependencies.

**LangGraph (optional):** strong for multi-step reasoning checkpoints, interrupts, review. Does not itself establish employer permission or replace the application ledger.

**Microsoft Agent Framework (challenger):** production-oriented workflow and human-in-the-loop; compare on a single bounded test.

**Pydantic AI (challenger):** strong model-neutral typed task outputs; potentially simpler than a complete graph for straightforward drafting.

**CrewAI (not primary):** role-based collaboration well suited to transient research teams, less compelling for a months-long applicant-owned case state machine.

**Paperclip (pattern reuse):** control plane for AI employees, not inherently a per-applicant job submission system. Study heartbeats/quotas/permissions while avoiding a second production control plane.

**Stagehand vs Browser Use:** Stagehand supports controlled per-step deterministic flows and extracted schemas; Browser Use offers open-ended navigation. Safety/latency/cost evaluation will decide in a synthetic form suite. AI browser capability is never authorization to send.

### Trial and evidence before selecting an external package

1. Pin actual source commit and review license and dependencies.
2. Run identical **nonproduction** scenarios with the existing SmartPloy/ObumAI implementation as baseline.
3. Browser test fixture: 20 randomized field layouts, dynamic steps, stale pages, unsupported forms, cross-origin redirects, CAPTCHA/MFA handoffs and 0 final submits.
4. Agent case fixture: 2 candidates × same employer; double-click duplicate, worker crash/claim lease, email injection, changed user permission during task, cancellation vs completion race and no send.
5. Measure time to first working integration, regression test count, execution duration p50/p95, model tokens/calls, provider costs, and failures.
6. Adopt only where test quality is at least as strong and measured integration effort is lower. Keep one selected framework, not parallel redundant agent engines.

## Reuse-first engineering-hours estimate (illustrative, not yet measured)

These assumptions compare the same six functional slices for one candidate-side pilot, in *person-hours* of an experienced engineer. They exclude legal agreements, unknown production outages, nonroutine ATS rights and deployed cross-provider end-to-end validation. They are **not proof of elapsed time saved** or a delivery commitment.

| Functional slice | From scratch | Reuse-first integration | Potential person-hours avoided |
| --- | ---: | ---: | ---: |
| CV facts and documents | 40h | 12h | 28h |
| Case identity, timers, retries and events | 48h | 24h | 24h |
| Follow-ups and reply triage | 40h | 20h | 20h |
| Safe browser observation and prefill | 60h | 30h | 30h |
| Bounded reasoning and human handoff | 40h | 24h | 16h |
| Scoped email read and reviewable draft | 48h | 30h | 18h |
| **Total hypothesis** | **276h** | **140h** | **136h** |

This model implies **49% less engineering effort**, or approximately **2.0× implementation throughput** for that illustrative scope. At 8 hours/day, the difference corresponds to 17 engineer-days. None of these numbers is a measured SmartPloy experiment; actual saving could be smaller, zero or negative when third-party integration/testing dominates. It does **not** imply production-ready unattended employer submissions and AI phone calls in 140 hours.

**Required empirical step:** For two tightly matched pilot components, record actual minutes spent (source discovery, security/license review, adapting, tests, integration, CI, rollback) and compare against a peer-reviewed clean-room task estimate. Report measured avoided hours, lines imported/adapted/original, and credible speedup after each delivery PR.

## Prioritized execution

**P0-A / Agent Zero:** **Source delivered on main**: CV-first PR #180 `8af78df2ba6e04263f82ef484d089b2adefb2af9`, Agent Zero PR #182 `d3f05c744bd55f4a6f333f68624223d4c87055ef`. It binds a persistent owner-scoped case to the original workspace, reuses shared worker leases and stores private in-app reminder events; tests include isolation, duplicate start and cancellation. External actions disabled and worker flag defaults off. **OVH migration and real wakeup acceptance remain unverified.**

**P0-B / candidate follow-up:** adapt career-ops followup-cadence, reply-matcher and outcome cases only where they fill a current gap. Bring an ObumConnect opted-in mailbox into read-only observation first. Require user review for all recruiter-facing drafts and any status uncertainty.

**P1 / optional engine selection:** direct worker vs LangGraph vs Microsoft Agent Framework vs Pydantic AI for a single interrupted/restarted case. Use the winner only if benchmarked value outweighs dependency cost. Independently compare baseline browser observer vs Stagehand vs Browser Use vs Playwright MCP; no real employer actions.

**P1 / allowed provider action:** keep original one-use user approval and durable employer claim/acknowledgment contract. Use authorized ATS API or assisted human handoff as applicable. Do not claim general unattended browser submission where unsupported.

**P2 / fleet and speech:** candidate consented voice call research with ObumSpeech and LiveKit/Pipecat; per-user job count, queue quotas, spend limits, load tests and failure recovery. No unlimited copying/spawning agents.

### Progress ledger

- **Done:** own-code and public-source screening, current GitHub license/star snapshot, three original YouTube video links, architecture decision, reuse candidate map and speculative time model.
- **Partial:** Skyvern original video corroborated only through secondary index; exact TikTok clips unavailable.
- **Not started:** pinned third-party dependency SBOM/security audits; external runtime code import; head-to-head framework trials; measured engineering hours saved; native ObumDelivery / OVH Agent Zero deployment and live signed-in acceptance. **Agent Zero source implementation completed** in PR #182.
- **Blocked externally:** unverified employer provider rights, approval of real outbound calls, direct TikTok evidence, independent OVH acceptance.

**Implementation transparency:** This research document introduces **zero runtime code**. Later PRs must provide the exact source paths and commit SHAs actually reused and tested before any speedup may be marked proven.

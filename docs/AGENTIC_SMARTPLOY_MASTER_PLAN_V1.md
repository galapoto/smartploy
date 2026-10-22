# Agentic SmartPloy — Master Implementation Plan v1.0

**Product:** Agentic SmartPloy — Agentic Job Hunters  
**Date:** 2026-10-22  
**Status:** Architecture and delivery proposal; implementation not yet commissioned by this document  
**Priority:** P0 architecture following completion of the existing SP21 CV-first release  
**Principle:** One real application → one durable agent identity → one verifiable outcome. Reuse existing SmartPloy and ObumAI code first.

## 1. Executive decision

SmartPloy evolves from a job-discovery/AutoApply website into an agentic, candidate-controlled job-search operating system. It does not discard the ongoing CV-first flow; it makes that flow the front door to persistent, per-application digital workers.

Each **Application Agent** is created when a user explicitly selects and opens an actual application case, not when a crawler merely discovers a vacancy. Its durable record can exist for weeks or months. It wakes for scheduled tasks and verified events, prepares evidence-based documents, coordinates authorized employer communication, monitors an opted-in mailbox, reminds the candidate, and handles interviews and outcome reporting. It closes when hiring or rejection is confirmed, or when the candidate explicitly withdraws/closes the case. **No response is not evidence of rejection.**

Agents are **logical identities backed by durable state and a shared bounded execution pool**, not continuously running language-model processes. Elastic provisioning is policy-controlled, idempotent and budgeted: no self-authorized replication, unlimited outreach, or accidental spend.

The product must optimize **quality of real opportunities and confirmed outcomes**, not raw application volume.

## 2. User journey and candidate control

**One simple visible path:**
1. User signs in through existing first-party identity, imports a CV, chooses General or Personalized search, and specifies employment goals, restrictions, contact preferences and budget.
2. SmartPloy retrieves source-current jobs using the existing job ledger and explains match uncertainty. It can verify employer-domain legitimacy and flag suspicious offers without invasive profiling.
3. The user selects a job and chooses Manual, Assisted, or permitted Autonomous preparation. SmartPloy creates/reuses the existing owner-bound Application Workspace.
4. On explicit case creation, SmartPloy binds **one Application Agent** to the owner, real employer, canonical job, workspace and approved communication policy. One user/employer/job combination must not spawn duplicates on reload.
5. Agent checks source freshness; extracts posted criteria; proposes honest tailored CV, letter, answers and missing-information questions; candidate reviews material representations.
6. Application goes through an **authorized provider integration** if rights and a matching one-use approval are present; otherwise an existing reviewed browser companion/human completes the employer site. Agent records provider acknowledgment independently from self-reported or page-observed evidence.
7. On confirmed submission the agent tracks applicable deadlines, an opt-in mailbox/replies and applicant-reported status; it summarizes interviews or changes, drafts courteous follow-ups and asks for approvals when required.
8. It helps prepare interviews, schedules events when permissioned, reminds or optionally calls the applicant, and assists with truthful negotiations and offers.
9. On confirmed hired or rejected status it ceases execution, revokes case-scoped capabilities, retains only necessary evidence for a documented period, and offers the user deletion/export. A withdrawn, expired or unanswered case has its own distinct closure reason.
10. The personal **Career Coordinator** learns from user-approved preferences and aggregate, privacy-safe progress, not from covert surveillance or unverified AI guesses. It may suggest a fresh application; a closed case cannot silently reactivate.

### Example

The applicant selects a Junior Data Analyst role in Tampere. A-1042 creates a personalized draft using approved CV facts. After the applicant reviews the documents, an authorized connection submits once and records a real receipt. Seven business days later, if no response and the user has pre-authorized a polite follow-up, it drafts/sends one appropriately timed message using the permitted mailbox connector. A recruiter replies to arrange an interview. The agent detects the response from the connected, owner-scoped mailbox, notifies the user, proposes calendar slots, and produces interview notes. The candidate approves any external calendar reply. The case ends when the offer is accepted and employment confirmed, or the employer sends a verified rejection.

## 3. Agent organization: roles are capabilities, not always-on processes

### A. Candidate-level Career Coordinator (one per candidate)

Goal planning, location/language/role restrictions, CV facts review, application priorities, contact policies, fatigue controls, dashboards, cross-case conflict detection, shared limits, consent revocation and learning from verified outcomes. This agent does **not** inherit blanket authority to contact employers.

### B. Application Agent (one durable identity per selected actual application)

Owns the isolated case state machine, tasks, scoped memory, correspondence thread references, application artifacts, activity timeline, pending approvals, receipts, schedule, budget, and completion. It is responsible for the case but cannot delegate a permission it does not have.

### C. Specialist capabilities (shared across all agents)

- **SmartPloy Scout / Matcher:** existing current-source database, preference matcher and CV-text discovery.
- **Evidence / Documents:** CV import and approved facts; Application Studio and job-specific exports.
- **ObumAI Core reasoning:** approved job interpretation, drafting, interview coaching and summaries; no consequential external actions via text-job API.
- **ObumBrowse:** source review and browser form observation/workflow when the actual safe adapter is verified; no assumption of final-click authority.
- **ObumConnect:** scoped OAuth email/calendar connectors; independent preview, approve and execute boundaries, no broad mailbox password capture.
- **ObumSpeech:** opted-in, disclosed AI voice, speech-to-text/text-to-speech; test first with synthetic calls and provider-specific compliance gates.
- **ObumKnowledge:** per-owner evidence retrieval and retention, not a global applicant corpus.
- **ObumDelivery / ObumSteward:** independent CI/CD, policies, audit evidence and multi-repo coordination. Neither authorizes sending job applications.

These are **shared tool services**, not sub-agents continuously consuming compute for every application.

### Architecture overview

    Existing SmartPloy UI (CV-first, job search, Application Studio)
          |
          v
    SmartPloy API + ZITADEL + user policy/consent service
          |
          +-- Personal Career Coordinator
          |      |
          |      +-- Application Agent Registry (Postgres)
          |              |--> Per-case state + event log + due tasks
          |              |--> Workflows and human approval inbox
          |              |--> Model/tool dispatch through policy gateway
          |                          |
          |                          +-- Existing SmartPloy CV/jobs/workspaces
          |                          +-- ObumAI reasoning / Browse / Connect / Speech
          |                          +-- Source-approved employer/ATS interfaces
          |
          +-- Shared bounded scheduler / execution pool
          +-- Channel receipts + cost ledger + audit + kill switches
          +-- UI activity feed / notifications

No direct model output is a permission token. All external actions pass a **deterministic server-side execution gateway**.

## 4. Durable Application Agent data contract (proposed)

Retain the existing canonical SmartPloy job, user, CV and workspace models. Add only missing tables after checking current migrations and repository implementations.

- **application_agent:** opaque agent_id; tenant_id; owner/profile_id; workspace_id; canonical_job_key; employer_key; snapshot digest; current state; lifecycle version; policy version; budget class; created_at; last_active_at; next_due_at; closed_at; terminal_reason.
- **application_agent_event:** immutable sequence, event kind, source and trust label, causation/correlation/idempotency key, resource fingerprint, timestamp, transition result; PII-minimized payload reference.
- **application_agent_task:** due_at; queue; priority; lease holder/expiry; retry/backoff; hard deadline; step/checkpoint; manual-handoff reason; outcome.
- **agent_action_grant:** subject + case + allowed tool + exact recipient/employer origin + payload hash + purpose + expiry + revocation epoch + use count. Write actions need preview/confirm and time-of-execution revalidation.
- **agent_contact_thread:** provider message IDs, verified correspondence associations, send/read provenance, contact-policy/rate-limits; not indiscriminate full mailbox replication.
- **agent_artifact_ref:** CV/letter/version hashes and secure private storage refs; no unnecessary duplicate CV blobs.
- **agent_receipt:** provider-issued acknowledgment distinct from browser observation, user self-report and unverified mailbox text.
- **agent_cost_usage:** provider/model/channel, estimated versus billed amount, execution step, budget enforcement and trace/correlation ID.

Proposed uniqueness: owner + verified employer + canonical job + active attempt, with only explicit reviewed creation of a new attempt. Preserve immutable event history and idempotency across tabs, devices, retries and worker crashes. Keep raw PII out of logs. Version public APIs and durable schemas.

### Lifecycle states

DISCOVERED (no agent yet) → SELECTED → CASE_CREATED → DRAFTING → NEEDS_REVIEW → READY → [AUTHORIZED_SUBMISSION or MANUAL_HANDOFF] → [PROVIDER_CONFIRMED or UNVERIFIED_ATTEMPT] → AWAITING_RESPONSE → SCREENING / INTERVIEW / ASSESSMENT / OFFER → HIRED or REJECTED.

Additional explicit states: BLOCKED, SNOOZED, WITHDRAWN, CLOSED_UNRESOLVED and CLOSED_EXPIRED. An uncertain submission remains UNVERIFIED_ATTEMPT pending reconciliation and must **never auto-retry**. Offer is not the same as hired. Applicant self-report is not the same as an employer acknowledgment.

HIRED, REJECTED and confirmed candidate closure stop all future agent activity and revoke case grants. Separate retention/deletion policy applies to stored evidence; agent execution does not resume due to delayed mail or webhook duplicates.

## 5. Autonomy and communications policy

| Level | Allowed by default | Requires explicit applicant action and other rights |
| --- | --- | --- |
| 0 Observe | Source-current monitoring, local match, employer-domain safety indicators | No employer contact |
| 1 Prepare | Owner-scoped document drafts, interview preparation, candidate dashboard notifications | Truthful review of uncertain facts |
| 2 Assist | Prefill safe fields in supported reviewed browser flow, suggest follow-up and calendar slots | Employer-site form submission, external send, sensitive fields |
| 3 Policy-authorized | Scheduled reminders and narrowly scoped approved communication when a valid, revocable policy and provider rights exist | Fresh permissions for material facts, recipients, nonroutine outreach; partner final-send claim |
| 4 Provider-verified action | Submit once through legally/contractually approved provider and record independently verified acknowledgment | Employer API rights + exact one-use candidate approval + final safety checks |
| 5 Research only | Multimodal navigation, agent-to-agent employer interfaces, advanced voice negotiations | Disabled outside isolated experiments until legal/security/UX evaluation passes |

This ladder is a **ceiling**, never a promise of permissions from an individual employer or job platform. The same user can set more conservative policy on any case.

### Email

First use connected provider OAuth with least required scopes and optional read-only filtering for replies related to a case. Treat arbitrary employer email as untrusted input, not instructions. Match authenticated domain/thread identifiers and independently confirm consequential claims. Prepare recruiter follow-ups with recipients, exact text, purpose, cadence and daily/monthly limits. New external recipient or material change requires approval. Track sent/delivered/replied states; respect opt-outs, bounce outcomes and quiet periods. No spam or deceptive human identity.

### Phone and voice

Start with **calls to the applicant only**, at their requested times and on a separate explicit voice opt-in; clearly identify the service as AI and offer SMS/email or human alternatives. Employer outbound AI calls require a jurisdiction/provider review, recipient expectations, lawful calling basis, recorded applicant approval, throttling and a visible AI disclosure; default OFF. No human impersonation, covert recording, spoofed caller identity, voice cloning without rights, or automated acceptance of an offer.

### Calendar, reminders and interviews

Connected Calendar read-only availability may be offered first. Event write/invite requires the applicant's preview-and-confirm action or a narrowly reviewed recurring grant. Avoid sharing candidate private calendar details; send free/busy slots. Sensitive hiring assessments, tests and live interview answers remain candidate-controlled; an agent can coach and remind, not impersonate the candidate.

### Employer verification / background checks

Do domain/company registry validation and public vacancy provenance checks to protect the candidate from scams. Do not perform covert background investigations into hiring managers, gather protected characteristics, scrape private networks, infer sensitive attributes or produce unvalidated fraud labels. For candidate records or background checks mandated by an employer, surface instructions; obtain proper lawful consent and use official processes, never fabricate outcomes.

## 6. Execution and scaling: millions of identities, bounded workers

**Primary design:** thousands of dormant agent records consume database storage, not continuous LLM tokens. Wake on webhook/mail event, approved task deadline, recruiter response, source-state change, interview date, applicant action or an intelligently coalesced periodic check.

**Phase A:** extend existing PostgreSQL repositories and SmartPloy worker_schedule's due-task lease/claim mechanism (already available) with short bounded callbacks, reliable outbox/event delivery, per-tenant queues, idempotent effects, dead-letter and backoff. Avoid replacing the deployed worker prematurely.

**Phase B trigger:** evaluate Temporal durable workflows when long timers, multi-activity compensation and restart/replay complexity demonstrably exceed the existing worker. Temporal is an optional runtime adapter, not a second source of truth. LangGraph may be used for internal checkpointed reasoning steps; neither framework grants external-action rights.

**Capacity controls:** per-user count of active cases, max concurrently running workers and browser sessions, per-job model/token limits, send/call caps per employer and day, execution TTLs, priority/fairness, circuit breakers, budgets and emergency stop. No permission for agents to create arbitrary children or subscribe to external channels by self-issued credentials.

**Budget model:** total cost = model input/output + browser session minutes + connector API requests + email delivery + telephony minutes + storage + infrastructure. Charge only when work runs and aggregate billed metrics by candidate/application/tool. Forecast from measured workloads; do not claim fixed unit economics from mock tests. Candidate must see budget and limits before opting in.

## 7. Existing-code reuse map (verified GitHub source paths)

| Existing asset | Reuse / integration decision |
| --- | --- |
| SmartPloy CV-first PR #180 | Front door: mode → CV → matches → choose job → explicit draft/review. Do not build a competing onboarding path. **Open/unmerged at design inspection**. |
| smartploy/cv_import.py, cv_storage.py, profile_storage.py | Owner-bound CV extraction, evidence and user approvals. |
| smartploy/search_preferences.py, scoring.py, sources/public_ats.py, storage.py | Existing source-current discovery and conservative matches; no new indiscriminate crawlers. |
| smartploy/application_workspace.py and application_workspace_storage.py | Durable per-job document kit, revision and identity. Agent binds to existing workspace_id. |
| smartploy/worker_runtime.py and worker_schedule.py | Existing per-account scheduling, leases and runtime health; adapt to wake Application Agents. |
| smartploy/obumai.py and docs/OBUMAI_INTEGRATION.md | Existing text-job API with idempotency and third-party forwarding rules. Reasoning only. |
| browser-companion/*, smartploy/browser_handoff.py, employer receipt and review modules | Existing reviewed ATS form help and provider acknowledgment/one-shot safeguards; do not bypass. |
| obumai/obumellm/docs/agents/AGENT_JOB_RUNTIME.md | Existing durable owner-bound **text-job** state with explicit external-actions-disabled boundary. |
| obumai/obumellm/obumellm/browser_runtime/* | Existing observer, mapper and non-final multi-page form-fill logic; integrate after sandbox/source policy review. |
| obumai/obumellm/obumellm/connections/* | OAuth, scoped connections, preview/execute separation and private token vault; do not assume production email send active. |
| obumai/ObumBrowse, ObumConnect, ObumSpeech, ObumKnowledge | Specialist ownership and declared interfaces. Current READMEs are development charters, not proof of live services. |
| obumai/obum-delivery | Keep isolated CI, reproducible integration tests, signed release receipts and separate OVH deployment evidence. |

**No fork/rewrite of complete ObumAI or SmartPloy.** Create only the missing case orchestrator, permission gateway, event/receipt lifecycle, candidate-visible agent UI and provider-specific follow-up adapters.

### External technologies to evaluate (not yet imported)

- **Temporal**: durable workflow/timers, human approvals and retry recovery. https://docs.temporal.io/ai
- **LangGraph**: interruptible reasoning subgraphs, checkpoints, internal human review. https://docs.langchain.com/oss/python/langgraph/interrupts
- **OpenAI Agents SDK or another model SDK**: structured tool calls, routing, tracing, evaluation. Provider-neutral wrapper is mandatory. https://openai.github.io/openai-agents-python/
- **MCP (current spec 2026-07-28)**: transport/tool capability descriptions and constrained connections. https://blog.modelcontextprotocol.io/posts/2026-07-28/
- **A2A v1**: optional inter-agent interoperability. Do not expose authority delegation directly. https://a2a-protocol.org/v1.0.0/
- **Playwright**: deterministic browser observations and permitted form work, not CAPTCHA/MFA bypass.

**Mandatory reuse research sequence before any component is built from scratch:** (1) search SmartPloy, obumellm and each existing ObumAI specialist repository; (2) inspect relevant public implementations surfaced by GitHub and documented YouTube/TikTok technical demonstrations, following any links back to their canonical upstream source; (3) compare functionality, maintenance, safety and source license; (4) legally reuse or adapt with attribution and required obligations, or independently implement when the licensing/quality gate fails; (5) benchmark implementation time against a documented from-scratch estimate. Videos and social demonstrations are discovery clues, **not proof that a package works or is licensed for copying**. Never assume that modifying restrictive-license code makes it reusable.

For each import: inspect feature fit, provenance, maintainer status, exact license at a pinned revision, security history, transitive deps, compatibility, source policy and integration test costs. **Changing licensed code does not remove license obligations.** Record reused vs adapted vs written-from-scratch lines, owner and estimated engineering time saved; do not invent a numeric speedup before benchmarking.

## 8. EU/Finland compliance and risk model (as of 22 Oct 2026)

- GDPR: document controller/processor roles, Article 6 legal bases by purpose, privacy notices, processor agreements, DPIA decision, purpose limitation, cross-border transfers, data minimization, access/export/erasure, retention, security and incident response. User settings are not automatically a valid GDPR lawful basis. Prefer privacy by design, with strict per-tenant vault/key scopes.
- **EU AI Act Article 50 transparency is already applicable from 2 August 2026:** external users who speak with an AI voice/agent must be told; avoid pretending to be a human. Product contract and local law may impose more safeguards.
- **EU AI Act employment high-risk timing:** Commission guidance reflects high-risk Annex III employment rules from **2 December 2027** (current amended timeline). Candidate-controlled job search and CV tailoring **exclusively for that candidate** are identified as out-of-scope examples for the employment selection use case; use by recruiters to filter/evaluate candidates is a different high-risk scenario. Reassess if business model or functionality changes.
- Finland electronic communications law / ePrivacy: distinguish non-marketing applicant-initiated contacts from regulated electronic direct marketing. Never assume automated cold calls are permissible because the candidate clicked AutoApply; require jurisdiction-specific legal review for employer-facing calling, opt-outs and recording.
- Platform contracts: LinkedIn prohibits unapproved crawling, scrapers and unauthorized automating activity. Use approved feeds/APIs or ordinary employer links; never circumvent login, CAPTCHA, robot access controls or contractual prohibitions.
- Social/ethical: no invented qualification, degree, visa status, identity, reference, compensation claim or hiring evidence; no spam, fake recruiter communication, non-consensual voice sample or invasive background search.
- Prompt injection, spoofed recruiter emails, malicious job descriptions, agent tool misuse, escalation, memory poisoning, replay and runaway agent replication must be covered by threat models and adversarial tests.
- Legal text and provider policies change: quarterly review, and release-blocking refresh after a relevant regulatory change or new high-risk capability. Legal counsel signs off on external channels; engineering tests alone do not establish legal permission.

Useful primary sources:
- https://ai-act-service-desk.ec.europa.eu/en/employment-0
- https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50
- https://ai-act-service-desk.ec.europa.eu/en/ai-act/eu-ai-act-implementation-timeline
- https://www.edpb.europa.eu/sme/be-compliant/be-compliant_en
- https://www.finlex.fi/fi/lainsaadanto/2014/917
- https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software
- https://genai.owasp.org/resource/aiuc-1-crosswalks-owasp-top-10-for-agentic-applications/

## 9. Delivery roadmap (gated by measured evidence, not speculative dates)

### Gate 0 — Stabilize existing CV-first core (P0)

**Scope:** Merge SP21 through exact-head CI and independently prove real OVH release SHA, signed-in user flow, current job sources, document preview and correct draft semantics.  
**Acceptance:** no false employer sends, no cross-account leaks, safe account switch, visible working CV→job→workspace.  
**Status as of inspection:** existing PR #180 open; main at 2bc677e3d5b9b9e0cfdfd6fd0295a0fda86ce2b0. Separate release receipt not verified.

### Gate 1 — First application agent: **Agent Zero** (P0, small vertical slice)

**Scope:** On explicit job selection + existing workspace creation, create/reuse one owner-scoped agent case; persist events and state, show progress and a timeline, schedule one follow-up reminder, support cancel/close/export and test worker restart. All external actions DISABLED.  
**Reuse:** Postgres workspace, worker lease, CV upload, existing UI and identity.  
**Deliverable:** real local/OVH controlled case persists across browser closure; receives one timer event and emits a candidate notification without contacting employer.  
**Evidence:** 2 tenants, double-click races, restarts, deadlines, idempotency, forced cancellation and deletion tests.

### Gate 2 — Candidate-side intelligence and communication (P0/P1)

**Scope:** applicant event inbox, case-specific notes, role/company verification, truthful drafting, opt-in reminders, one connected mailbox read-only watcher, recruiter email-to-case matching and reviewable reply drafts.  
**External send:** disabled initially; after legal/connector and authorization gate, one confirmed outbound message on a test mailbox with a verified send receipt.  
**Acceptance:** injected employer email cannot command agent; stale or mismatched contacts do not trigger sends; no duplicate reminders.

### Gate 3 — Safe application execution (P1)

**Scope:** reuse allowed Lever partner path and reviewed browser companion; add per-agent action claim binding exact account, job, posting, document version, user approval and provider acknowledgment. Expand connectors ONLY after independent rights and QA.  
**Acceptance:** one independently acknowledged allowed application; exactly-once claimed attempt across devices; uncertain results go to review, never retries or counted as applied; unsupported employer form remains manual.  
**Blocker:** actual employer/provider rights and live QA are external dependencies.

### Gate 4 — Full follow-up and interview case management (P1)

**Scope:** contact cadence, notifications, mail reply summarization, candidate calendar proposals, consented calendar event writes, deadlines, interview preparation, rejection/offer/hired closeout.  
**Acceptance:** complete lifecycle demo with synthetic recruiter and genuine owner connector consent; no unseen outbound action or stale wake-up after case closure.

### Gate 5 — Voice and broad provider expansion (P2)

**Scope:** applicant-only AI calls with explicit consent, local-language speech evaluation, then employer-facing calls only after legal and consent review; more vetted ATS APIs/browser flows.  
**Acceptance:** caller disclosure, opt-out and quiet hours, call failure recovery, speech accuracy checks, verified call receipts without unauthorized recording, bounded cost and volume.

### Gate 6 — Fleet scale and optimization (P2)

**Scope:** multi-tenant fairness and rate limits, load-test 1k/10k/100k dormant agent records and realistic active fractions, queue health, failure recovery, budget dashboards, dead-letter replay, horizontal workers, stress tests and abuse controls.  
**Acceptance:** actual load data demonstrates safe provision, cancellation, isolation, recovery and predictable cost. Scale targets remain hypotheses until measured.

### R&D track — future agentic capabilities (continuous, gated)

- Agent-to-agent employer interaction standards (A2A, versioned MCP and provider attestations).
- More capable multimodal browser navigation, accessibility-based form understanding and safe fallback.
- Local private/on-device inference, per-tool model routing, context compression and cost reduction.
- Speech conversations and multilingual coaching with candidate control.
- Outcome-aware ranking based on opt-in, privacy-safe evaluation, counterfactual fairness and feedback.
- Machine-verifiable authority, one-use delegation, zero-trust tools, independent agent sandbox and durable receipt standards.
- Optional autonomous negotiation tools; must never accept/bind a candidate to employment without explicit human decision.

Every experiment has a hypothesis, baseline, privacy review, bounded budget, signed fixtures, red-team evaluation and promotion gate. Prototype status is never advertised as a production capability.

### Indicative delivery windows, not commitments

Assuming existing CI/dev access and stable migrations, **Agent Zero can be a short focused engineering sprint (roughly 1–2 weeks)**. An integrated candidate follow-up MVP typically needs additional connector/policy work and real user testing (roughly **2–5 more weeks**). Authenticated employer submission and phone contact depend on outside provider rights and legal review and cannot honestly be promised on a calendar alone. Replace these ranges with measured throughput, blockers and acceptance evidence after the first sprint.

## 10. Security and acceptance contract

**Non-negotiable release tests:**
1. Agent never crosses owner/tenant or job boundaries; same-email switched accounts remain isolated.
2. One case per selected application despite retries, browser refresh and concurrent workers.
3. No CV/contact/identity/private calendar data leaks through logs, model output or another user.
4. Prompts inside postings, emails and CVs cannot alter tool permissions, send recipients or execution policies.
5. A model-generated plan is never an executable approval: server verifies scope, resource hashes and revocation just before external dispatch.
6. No unapproved employer email, call, form submission, message send, calendar invite or background check.
7. Manual/browser-observed/provider-acknowledged states remain distinguishable; unknown is never “rejected” or “submitted”.
8. Crash mid-task/restart produces a single external effect or honest uncertain state; unsafe sends are not blindly retried.
9. Candidate can pause/kill all agents; terminal cases never wake or spend.
10. Provider adapter is disabled immediately on terms/compliance regression; alternate legitimate handoff remains available.
11. Rejection, withdrawal, deletion, expired consent and hiring confirmation cause worker/grant shutdown consistently.
12. Opt-in voice test proves disclosed AI identity and compliant contacts.
13. Signed build/release receipts, exact SHA and real signed-in acceptance are separate from synthetic tests.
14. Cost and rate quotas block runaway generation and sender spamming.
15. Accessibility, Finnish/English and mobile UI work end-to-end for real first-time users.

Testing pyramid: unit and state-machine property tests → ephemeral PostgreSQL interleaving tests → provider fixtures and contract tests → synthetic browser/telephony/email tests → staging with consenting accounts → deliberately approved live action → release/rollback drills. Measure exceptions and security regressions; fail closed.

## 11. Product metrics and business quality

- **North star:** verified interview opportunities and verified accepted employment **per genuinely suitable application**, not gross applications sent.
- Agent funnel: found → selected → draft ready → review approved → provider acknowledged / manual handoff → recruiter reply → interview → offer → accepted/hired/rejected/closed unresolved.
- Guardrails: unauthorized sends = 0, account leaks = 0, double provider submissions = 0, fabricated evidence = 0, unlabeled voice interactions = 0.
- Operating KPIs: agent task recovery, due-reminder SLA, time to human review, verified reply association, conversion by role/source, candidate response burden, external send rate, opt-outs, cost per active case and per verified interview.
- Agent efficiency: percent of cases sleeping; model calls per meaningful event; total provider spend versus quality outcomes; employer-facing contact complaints and account restrictions.

Never use model-generated outcome guesses to boost conversion figures.

## 12. Ownership and coordination

| Workstream | Owner | Core boundary |
| --- | --- | --- |
| SmartPloy UX + API + case state | SmartPloy product engineering | Owns candidate/business state and application truth |
| Core models / agent text job | ObumAICore / actual obumellm runtime owner | Text reasoning and bounded jobs; no implicit write rights |
| Controlled employer form | ObumBrowse + SmartPloy connector owner | Source rights, form evidence, exact safe actions |
| OAuth mail/calendar | ObumConnect | Scoped user tokens, preview/execute, receipts and revocation |
| Audio/channel | ObumSpeech | Consent-based speech, disclosures, no unsolicited calls |
| Candidate-scoped retrieval | ObumKnowledge | Isolated evidence and retention |
| Delivery and governance | ObumDelivery + ObumSteward | Multi-repo coordination, independent CI and controlled release |

Parallelize by versioned API/fixture contracts; services remain functional if others are unavailable. Every run reports **Done / In Progress / Blocked / Not Started**, reused exact files, newly implemented code, tests, actual CI SHA, production SHA, operator proof and unknowns. No silent merge of speculative code, no developer-facing claim of live capability from a README.

## 13. Immediate ordered engineering backlog

1. Finish and deploy existing SP21 CV-first path independently; do not make Agent Zero a new prerequisite to ordinary job searching.
2. Draft versioned agent event/state/API contract and authorization matrix; map to the **existing** migrations and repositories to avoid duplicated tables.
3. Implement atomic create-or-get per-job agent bind to an existing Application Workspace, plus timer claim and close/cancel; no external actions.
4. Add simple UI: **My Job Agents**, one case page, current step, next action, timeline, consent/budget, Pause, Stop, Needs review and End case.
5. Add candidate-only notifications and one safe read-only mailbox connector behind explicit opt-in; require clear status provenance.
6. Design and security-review external action grants, outbox, receipts and provider boundaries before implementing sends/calls.
7. Ship a real end-to-end **Agent Zero** acceptance scenario, then widen one authorized channel at a time.
8. Start parallel R&D evaluations with published comparative evidence; retain the stable public contracts during technology changes.

**First independently usable milestone:** A person creates an application in the existing SmartPloy journey, receives a durable personal application agent, closes the browser, and later sees that agent automatically wake, review its case, and notify them of the next actionable step without contacting an employer or consuming unbounded resources.

## 14. Status and factual limits at plan creation

- **Existing SmartPloy:** CV/job/workspace/worker/browser foundation in source; SP21 PR #180 had not merged at inspection; latest real production status must be checked independently.
- **Existing ObumAI:** durable agent text-workflow contracts and browser/connectors source exist in obumai/obumellm; their own contracts prohibit assuming consequential external actions or a production-ready voice sender.
- **New proposed work:** Application Agent Registry, lifecycle state/events, policy gateway, multi-channel follow-up, case coordination and audit UI are **not implemented by this plan**.
- **External blockers:** exact ATS rights, legal channel review, real OAuth accounts, domain reputation and validated production infrastructure.

Plan versions should be compared to recorded release evidence and revised quarterly or upon a material capability, security, provider or regulatory change.

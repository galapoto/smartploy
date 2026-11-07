---
title: "SMARTPLOY | THE FINAL RAPID-SHIP CONTRACT"
subtitle: "Production-first AutoApply, award-calibre UI, aggressive reuse, and parallel engineering — starting 7 November 2026"
author: "Independent product and engineering synthesis | Builder-ready specification"
date: "7 November 2026"
lang: en-US
---

**VERSION 4.0 — IMPLEMENTATION AND ACCEPTANCE CONTRACT**  
**Decision:** Start all workstreams now. Release the smallest *complete, usable, verified* candidate feature as soon as it qualifies. The first critical outcome is a real job application filled to an observed review state or a separately authorized, evidenced submission. Do not spend another development cycle producing only mockups, test-only workflows, or an unreleased mega-branch.

> **Evidence status, not marketing:** This document is a build order, not proof that SmartPloy has been fixed or deployed. On 7 November 2026, a live GitHub check showed `galapoto/smartploy` main at `f565c8789f141628b79fe3285cd9e16e1a1302e3` and PR #299 **open**, head `d44221b2910546d4fd4a87c0bd8d3d58f217bb90`. The previous papers reported public release `cee0017091e5`, but that *production version was not independently re-verified for this edition*. The signed-in public candidate journey was not executed here. No production deployment was performed for this paper.

**One-line promise:** *Know my qualifications accurately. Find worthwhile roles. Prepare excellent truthful materials. Apply visibly, reliably and under my control. Prove what happened. Help me progress.*

![A proposed, not deployed, SmartPloy application workspace.](smartploy_v4_workspace.png){width=6.8in}

\newpage

# 1. Executive decision: what becomes usable today

SmartPloy must become excellent **by releasing an actual product**, not by accumulating stronger paper scores. The existing Python API, PostgreSQL application workspaces, React/Vite UI, first-party Manifest V3 extension and ObumAI-derived Playwright browser actor remain the foundation. The four prior papers repeatedly identify the same bottleneck: a source/deployment mismatch, narrow field automation, cumbersome setup, an incomplete application journey, and a design whose sophistication is not yet visible in the public product.

The plan is ambitious but bounded. **Today is 7 November 2026**, and the target is an observable same-day release *if the team can meet the exact acceptance gates*. "Perfect today" cannot honestly mean automatic successful submission to every employer in the world; third-party sites may require human authentication, block automation or change forms. **It can mean zero known critical defects in a clearly identified, real, supported journey**, with a polished public UI and an honest manual/assisted fallback for other jobs.

## 1.1 Day-zero acceptance: one candidate, one real job, no invented success

| Must be working in the signed-in production UI | Evidence needed before the label "working" |
|---|---|
| CV upload or existing CV selection without unnecessary re-upload | Saved CV identity and extraction review survive refresh |
| Visible Manual / Assisted / Automatic choice, followed by job selection | Actual click path, persistent case, no dead-end button |
| Complete truthful CV and cover letter; editable and downloadable | Exact approved PDF/DOCX bytes, extraction and revision check |
| AutoApply opens the **correct live employer form** | URL/origin/job identity verified after navigation and redirects |
| Extension *and* Playwright perform supported field filling | Separate real Chromium tests, persisted values, controlled widgets |
| CV attachment, required questions, multi-step transition and resume | Acknowledged uploads and checked requirements, with focused handoff |
| Candidate can watch, pause and take over | Real browser tab/window/stream; controls operate on the live case |
| Reaches ready-for-review, or sends only if expressly approved | Reviewed packet, unique submit claim, correlated receipt or `unknown` |
| Application remains in tracking after refresh/reconnection | State, event log, next action and receipt provenance retained |
| New beautiful responsive public UI | Actual signed-in screenshots at desktop/mobile, light/dark and zoom |

**Do not redefine success downward.** Filling name and email is not a complete AutoApply journey. Clicking Submit is not a confirmed application. A visual prototype is not the public UI. An extension-only result is not Playwright parity. If any critical gate fails, label that capability "not yet verified" and release only other independently complete, safe features.

## 1.2 Scope we will *not* put on the critical path

A new microservice fleet, a new universal browser platform, complete country localization, every ATS adapter, autonomous mass submission, a rebuilt database, a new model provider, and a cluster-scale orchestration system are **not prerequisites** to today's first working release. Those initiatives may begin in separate branches immediately; they must not delay the current user journey. This is simultaneous development with dependency-aware release, not simultaneous changes to the same production code.

## 1.3 Changes from V1/V2/V3 — final decisions

| Previous direction | Final decision and reason |
|---|---|
| A major integration PR carries many features | **Extract independently testable vertical patches**; never blindly merge a huge PR |
| Lever/Ashby first, semantic engine later | **Complete one real supported journey immediately**, while semantic coverage starts in parallel |
| Hosted browser early | **Start hosted isolation work now**, but do not block local/extension acceptance or expose unisolated sessions |
| UI styles and mockups are a major deliverable | **Make the connected browser workspace the signature screen**; screenshots must reflect real events |
| Generic document-generation quality goals | **Ship a full factual CV/letter editor and valid exports in the same first wave** |
| Six 9.6–9.8 target scores | **Replace score-first goals with release gates and observed numerator/denominator evidence** |
| Reuse many GitHub repos | **Copy the smallest proven units aggressively**, retain provenance, sanitize behavior, measure gains |

# 2. Current evidence and the first debugging decision

**Fresh live read for this edition:** GitHub reports `main=f565c8789f14…`, PR #299 open at `d44221b29105…`, and the branch still contains `web/src/App.tsx`, `ApplicationStudio.tsx`, `ApplicationJourney.tsx`, `StartChoices.tsx`, `browser-playwright/assistant.py`, `browser-playwright/bridge.py`, `browser-companion/logic.mjs`, and `deploy/personal/scripts/deploy.sh`. The original papers inspected this same integration head and recorded the public-release gap; this report confirms the code state and PR status, **not** the current production SHA.

The current inspected `browser-playwright/assistant.py` states that it is a review-gated local filler, and its `UNSAFE_INPUT_TYPES` deliberately includes checkbox, radio, select, number and date. The bridge explicitly says there is **no automatic final submit** and its reviewed PDF attachment is a separate authorized step. Those are policy/code limitations, not a mysterious lack of model intelligence. `ApplicationJourney.tsx` itself describes Automatic as supervised filling and final Submit as remaining with the user unless a separately authorized provider is supported.

The right immediate engineering response is therefore **not** "install another AI agent and hope." It is: isolate the smallest safe controls needed for an actual chosen job; add typed approved answers and verification; connect them to a persistent case and UI; qualify and deploy the exact artifact. Keep safeguards for sensitive disclosures rather than globally declaring entire input element types unsafe.

## 2.1 First 60–90 minutes: release truth audit

**Release owner** obtains current `origin/main`, PR #299 head, active deployment manifest, website HTML asset versions, API/helper versions, feature flags and CI status. Inspect the exact active production identity mode and authorized deployment path. Record current branch/commit, current public release (if observable), blocked route, and reproducible browser error. Run one signed-in smoke journey and save a sanitized trace. Do not treat unauthenticated `/release.json` or GitHub merge state as a substitute for signed-in product proof.

**Decision fork:**

* If the tested feature already works at PR #299 and the only blocker is promotion, prepare a **small extraction/cherry-pick with its dependencies**, pass native CI, deploy and verify.
* If the feature is incomplete in source, modify **the smallest existing controller/adapter**, not a parallel execution stack.
* If the production deployment differs because of an explicit identity/security gate, fix the gate according to its approved policy; never bypass OIDC, release-source checks or authorized review.
* If no authorized live employer job is available, prove a full controlled fixture flow and clearly label the external real-site acceptance **pending**; do not call it production AutoApply success.

# 3. Today's implementation calendar: parallel from minute one

The following are *target work windows from kickoff*, not promises. They assume at least **one integration/release owner; two browser engineers; one frontend engineer; one documents/profile engineer; and one independent QA/security engineer**. If fewer people are available, reduce the number of concurrent experiments, **not** the correctness gates.

| Window | Parallel work and exit signal |
|---|---|
| H0–H1 | **Release:** actual running SHA/flags and login audit. **Browser:** reproduce blocked live form, trace extension and bridge. **UI:** audit actual screens. **Documents:** reproduce export defects. **QA:** freeze test job, packet and negative cases. |
| H1–H3 | **Release:** small #299 extraction and locked contracts. **Browser:** typed controls, uploads, step verification. **UI:** fast shell, sidebar, mode flow. **Documents:** full text/editor/export and factual protection. **QA:** shared fixture corpus and isolation. |
| H3–H6 | **Release:** qualify separate candidates. **Browser:** one full form, pause/resume, review and receipt rules. **UI:** bind real case events and browser controls. **Documents:** exact approved packet. **QA:** cross-executor real Chromium and negative tests. |
| H6–H9 | **Release:** deploy each qualifying slice. **Browser:** repair failed traces. **UI:** dark/light, zoom and mobile tests. **Documents:** byte-for-byte export verification. **QA:** signed-in public acceptance and rollback rehearsal. |
| H9–H12 | **Release:** evidence ledger and running-artifact check. **Browser:** second site/field family once first passes. **UI:** interaction polish. **Documents:** bilingual editorial review. **QA:** regression and incident corpus. |

**Integration policy:** No lane waits for the others' entire feature roadmap. Each lane uses the locked `Case`, `Packet`, `Observation`, `Action`, `Receipt` and `CandidateFact` contracts. A lane that finishes a coherent user-visible feature delivers a small independently reviewed release immediately. The release owner alone promotes production flags; the QA owner can block release on critical failures.

# 4. Complete candidate journey: the only primary flow

A first-time user signs in, uploads or writes a CV, confirms extracted factual details, chooses Manual / Assisted / Automatic, selects one real job, reviews a job-specific packet, and starts. A returning user lands at the last actionable case or strongest relevant jobs without repeating onboarding.

**Manual:** Prepare/download truthful documents; open the exact employer URL; track the job. **Assisted:** Fill through an active authorized browser with candidate review before send. **Automatic:** Complete permitted steps with user-approved packet and bounded action scope; stop for new sensitive or ambiguous questions; final submission only if an explicit active authorization includes it. A candidate may start with **CV only**, but must be told additional questions may arise; after each new ordinary answer, SmartPloy offers to save it for reuse.

The primary action is a single state-aware button: `Continue setup` → `Choose job` → `Prepare packet` → `Start AutoApply` → `Answer question` / `Reconnect browser` → `Review and send` → `View result`. Never show a clickable Automatic button without an eligible executor, and never send because a user merely selected the mode.

The last step distinguishes `ready for review`, `confirmed by employer`, `employer rejected/validation error`, `unknown after attempted send`, and `user reported applied`. The application timeline persists all of these as different facts.

# 5. Technical architecture: keep one case; expand the executor

![One authoritative application case and three execution surfaces, with verified outcomes.](smartploy_v4_architecture.png){width=6.7in}

Do **not** create three agents with conflicting permission systems. Preserve SmartPloy's server-side authoritative application workspace (case aggregate). Implement one controller and three *transport adapters*: first-party Chromium extension, local visible Playwright, and secure hosted Playwright when isolated and accepted. A model proposes an action; the server decides whether the action is allowed; the active executor acts; the result is observed and checkpointed. ObumAI's existing browser code is reusable as **implementation material**, not as permission to bypass SmartPloy's tenant and submission rules.

## 5.1 Versioned contracts to freeze before parallel work

The contract names are conceptual and must map onto existing database and endpoints rather than duplicate them.

```text
Case: tenant_id, case_id, user_id, canonical_job_id, employer_origin,
      state, state_version, selected_mode, policy_id, executor_kind,
      executor_lease_id, fencing_token, packet_revision, packet_hash,
      event_cursor, created_at, updated_at
Packet: approved_cv_document_id, approved_letter_id, document_sha256,
        candidate_fact_ids+revisions, question_answer_ids+scopes,
        canonical_application_url, employer_job_identity,
        granted_action_scope, approval_generation
Observation: origin, url, job_identity, frame_path, observation_revision,
             form_fingerprint, stage_id, control_snapshot,
             validation_errors, upload_acknowledgments, timestamp
ActionProposal: action_id, observation_revision, action_type, target,
                approved_fact_or_document_id, expected_effect,
                time_budget_ms, retry_policy, requires_approval
ActionResult: attempted, observed_effect, persisted_value_verified,
              validation_change, uploaded_acknowledgment, next_stage,
              sanitized_trace_ref, error_kind
Receipt: no_send|ready_for_review|confirmed|rejected|unknown|manual_report,
         provider_id, canonical_job_id, correlated_evidence_ref,
         observed_at, packet_hash, submission_attempt_id
```

**Minimal executor protocol:** `Observe → Normalize → Resolve facts → Propose → Policy-check → Execute one action → Verify on fresh page → Checkpoint → Continue, hand off or reconcile`. Every transport must return the same typed contract, although browser-specific details may differ. Version and reject incompatible messages; the first day needs protocol **minimum viable compatibility**, not a greenfield distributed architecture.

## 5.2 Durable state and non-negotiable invariants

`draft → preparing → ready → connecting → filling → needs_input ↔ filling → ready_for_review → submitting → confirmed | rejected | unknown`, with `paused`, `cancelled` and `failed` transitions as appropriate. `ready_for_review` is a **useful and honest** day-zero completion if the user's authorization is fill-to-review.

1. One active executor lease per case; every write requires a current fencing token and expected state version.
2. An action may use only a fresh observation of the same employer job, current packet revision and authorized data field.
3. A typed answer cannot be silently inferred for work authorization, salary, consent, criminal history, medical information, eligibility or other sensitive attestations.
4. A document change invalidates the pending packet approval before any further external action.
5. Submission requires a unique durable claim, stored *before* sending and correlated to the job and packet.
6. A disconnected browser after an attempted send becomes `unknown`, **not** an automatic second send. Reconcile first.
7. Employer pages, job descriptions, third-party files and retrieved repository prompts are **untrusted content**, not agent instructions.
8. Account isolation, user takeover, pause and emergency stop must be enforced at the server, not only hidden/shown in the interface.

These are a stronger contract than simply making the automated browser click further. **Correctness must survive interruption.**

# 6. AutoApply: precise repair scope for today

## 6.1 Replace indiscriminate control blocking with typed permission

The current local Playwright code marks most input types beyond text as unsafe. That is appropriate for an early limited helper, but insufficient for normal applications. Do not remove the protections globally. Split fields into `ordinary safe`, `user-confirmed contextual`, `sensitive/attestation`, `credential/human-only`, `action-only` and `unsupported`. Grant each control an action from a typed, packet-bound policy.

| Control family | First-day implementation and verification |
|---|---|
| Text, email, phone, URL, textarea | Use confirmed values; verify actual persisted value after blur/debounce |
| Native select and radios | Exact option identity; reject aliases where positive and negative choices can be confused |
| Checkboxes | Distinguish ordinary requirements from opt-in, legal and sensitive commitments; never assume `true` |
| React-controlled text | Native value setter plus proper input/change events; re-read after render replaces DOM |
| Autocomplete / combobox | Scope to owning field and popup; wait for options; select only an approved exact or unambiguous equivalent; verify selected state |
| Number / date | Check field meaning, units, locale and approved answer revision; no guessed salary, availability or birth date |
| CV / letter uploads | Bind approved document hash, MIME/size and exact target; observe employer upload acknowledgment |
| Education/experience arrays | Add one row; verify dates, employer, degree, count and required follow-on controls |
| Conditional steps / iframe | Re-observe after each triggering answer; use frame-aware locators; do not replay old coordinates |
| CAPTCHA / login / new attestation | Pause with focused candidate handoff; resume from fresh observation |
| Submit button | Requires policy + unique claim + fresh review + matching job; never equate clicking with confirmation |

**Fastest existing-code seam:** preserve `browser-playwright/assistant.py` and `bridge.py`; add targeted field adapters, preferably a shared testable matcher in `browser-companion/` with a thin Python port. Preserve the existing strict URL/packet checks in `browser-companion/logic.mjs`; do not copy a donor's unrestricted navigation or broad content-script permissions.

## 6.2 Three interpretation layers — in one controlled loop

**Layer 1, deterministic recognized ATS:** Leverage known Lever/Ashby form structure and exact fingerprinted locators. **Layer 2, universal semantics:** inspect accessible names/roles, groups, required rules, option relationships, validation and current step. **Layer 3, bounded visual:** if the semantic engine cannot identify a control, use a fresh redacted screenshot for **one proposed action at a time**, validate against authority, act and verify. Vision never grants approval, invents candidate facts or autonomously crosses site restrictions.

Build Layers 1 and 2 from kickoff, but **ship Layer 1's first complete real case first**. The universal layer should share the same observation and action contracts from day one; it does not need exhaustive unknown-site coverage before launch. Stagehand and Browser Use can compete **behind** a single fallback interface, not become rival controllers.

## 6.3 Field-loop pseudocode — no blind actions

```python
while case.can_continue():
    obs = executor.observe(case)                  # fresh origin, job, controls
    assert policy.matches_job_and_packet(case, obs)
    target = planner.next_required_control(obs, case.packet)
    if target is None:
        return checkpoint_ready_for_review(case, obs)
    proposed = resolver.resolve(target, confirmed_facts, scoped_answers)
    if proposed.missing_or_ambiguous_or_sensitive:
        return checkpoint_needs_input(case, target, proposed.reason)
    token = authority.authorize(case, proposed, obs.revision)
    result = executor.execute(proposed, token)    # one bounded action
    fresh = executor.observe(case)
    if not verify_expected_effect(proposed, fresh):
        return checkpoint_recover_or_takeover(case, fresh)
    case.checkpoint(fresh, result)                # state/version/fence enforced
```

This intentionally excludes final submission from the generic field loop. Sending has a separate guarded state transition and receipt correlator. **The executor must not try harder by guessing.** It should re-observe, ask the user or stop honestly.

## 6.4 One employer, then two, then breadth

First-day real acceptance should target **one currently open, authorized Lever or Ashby form**, chosen for observable completeness and no bot restriction conflict, and reach `ready_for_review`. Verify actual submission only if that candidate has expressly authorized sending that particular application. Repeat the same controlled example via extension and local Playwright; no artificial submission merely to increase a pass count.

Second, run a different form family (Ashby if Lever was first), then additional controls and multi-step workflows. Start Greenhouse/TalentAdore follow-ups against real demand. Track (a) supported complete cases, (b) all requested jobs, and (c) forms needing human handoff — not just counts of filled inputs.

# 7. Browser experience: watch, interrupt, resume

**Extension:** The employer form stays in the user's actual Chromium tab; a SmartPloy side panel shows stage, verified progress, missing answer, pause, take over and next action. Keep MV3 state outside a fragile popup; use active-tab/explicit host permission and an authenticated server case-bound handshake.

**Local Playwright:** Reuse the ObumAI-derived visible persistent Chromium actor and existing loopback bridge; do not introduce Selenium or a second browser controller. The browser window is real; SmartPloy shows synchronized truthful activity and the ability to pause/stop. Pair once and expose clear `Connected / Reconnect / Connect browser` states. Reauthorize on tenant/session changes.

**Hosted Playwright:** Start a security-isolation vertical slice **today in a separate lane** because mobile and zero-install users need it. It becomes a user-facing option only with per-user context isolation, origin/SSRF restrictions, short-lived case-bound stream/control authorization, secret masking, termination, cost limits, takeover and independent tests. A normal webpage iframe is not a substitute for a controlled hosted browser stream. The release of hosted does **not** block today's extension/local path.

**Executor chooser:** Prefer a previously connected permitted extension where the user's session is already active; otherwise a qualified hosted session when available and opted in; otherwise an explicitly connected local worker; otherwise offer Assisted/Manual. Device reality matters: desktop extensions do not run as-is inside iOS Safari.

# 8. The UI today: distinctive, connected, responsive

A premium appearance is not a matter of installing a design library. Use SmartPloy's existing `BrandMark.tsx` vector (turquoise `#06D9E8`, dark navy `#021E3D`) and identity, retain the requested horizontal Finland landscape on **Home**, keep the sidebar with a graceful two-way collapse control, and make the *real* browser workspace the distinctive product moment. In Apply, omit the large decorative banner so the employer form gets the space.

The V3 mockup is too close to an ordinary back-office dashboard. The new concept in the first figure emphasizes **one actual job**, **one live work surface**, **one next action**, and **very little technical prose**. Every verified check mark must correspond to a real recorded field state.

## 8.1 Visual system ready for implementation

| Token / rule | Immediate working specification |
|---|---|
| Typography | **Inter Display** headings and **Inter** body/UI, or preserve proven current fonts if bundle/performance comparisons favour them. Body 16/24 px, controls ≥14 px; reserve width for Finnish labels |
| Colors | Canvas `#F3F6FB`, surface `#FFFFFF`, primary navy `#11223D`, action blue `#245AD7`, brand turquoise `#06D9E8`; dark canvas `#091323`, dark surfaces `#13243B` |
| Geometry | Primary cards 20 px radius; controls 12 px; baseline 8 px spacing grid; meaningful 16–24 px gaps, generous content width |
| Elevation | Two soft ambient shadows plus an optical top highlight; vary elevation by interaction, not decorative shadow everywhere |
| Sidebar | 232 px expanded, 72 px icon rail collapsed, visible expander in both; drawer/sheet on mobile |
| Desktop layout | Fluid content up to a sensible wide-display limit; employer browser is the dominant flex region, no giant empty side gutters |
| Motion | 120–200 ms transitions; only actual state change drives progress. A subtle **status orbit** may animate during observed active execution, never as a fake infinite completion spinner; honor reduced motion |
| Access | Keyboard, focus indicators, WCAG 2.2 AA target, 320 CSS px reflow, 200% zoom, 44 px touch-action product standard |
| Navigation | Home / Jobs / Apply / Applications / Documents / Profile; operator tooling moves out of applicant navigation |

Do not begin with a massive Tailwind migration. Implement reusable React card primitives and CSS variables in the existing Vite app; use small shadcn composition ideas and React Aria behaviors where required. Preload only key fonts, lazy-load heavy editors, reserve banner dimensions and show shell before private dashboard requests complete.

## 8.2 Screen acceptance, not mood boards

**Home:** Calm Finland banner; next step card; up to three genuinely suitable jobs; current documents; unobtrusive attention items. **Jobs:** Effective searching and filters with truthful fit reasons, saved status, real employer link, supported/needs-handoff label. **Apply:** Real tab/window/stream plus stage, current question, progress, pause, takeover, approved packet; a single next-action area. **Documents:** Full CV/letter editor, revision compare, actual PDF/DOCX, download and reopen. **Applications:** True state, observed receipts, missing action, reminders. **Profile:** All typed facts and user-approved reusable answers; not a random questionnaire that blocks CV-only users.

Do not expose release SHA, worker health, ingest sources, model tokens or retry internals to normal applicants. Create a separate allowlisted operator API/portal, rather than merely hiding developer widgets with CSS. Private cache/query state must be keyed by tenant and login session generation, canceled on logout/account change.

## 8.3 Realistic same-day UI definition of done

The current React product must display and respond correctly under the following screenshots/tasks: 1440 px desktop, wide desktop, 768 px tablet, 390 px phone, 320 CSS px reflow, 200% zoom, Finnish/English long text, light/dark, keyboard and screen-reader smoke. The sidebar opens/closes without shifting content outside the viewport. Buttons do what their labels promise. Initial navigation shows useful UI while data loads. Hover-only actions have keyboard/touch equivalents. A blinded reviewer can find `Start AutoApply` and `Take over` without instructions.

# 9. CV and cover letter: fix the complete packet today

The generator's main job is not to make text longer or collect keywords. It must produce a **convincing, employer-specific, truthful argument** from approved evidence and user voice. Keep one structured master CV and immutable tailored versions. Only the user confirms previously uncertain facts. Store a claim-to-evidence link; keep education, dates, positions, certificates and numbers protected against invention.

**Same-day document pipeline:** Import CV → extract facts → approve conflicts → map job requirements to evidence → create complete CV/letter → deterministic claim/identity validator → consistency check between documents and answers → editable review → render PDF/DOCX → extract and compare bytes/content → bind hashes to the application packet. Permit user edits and restore; changes invalidate stale approval.

The first release must repair real export/download issues **without introducing a whole new document engine**. Reuse SmartPloy's current renderer. Adapt `srbhr/Resume-Matcher` preservation checks and `career-ops` fact validation; assess Reactive Resume or RenderCV only if a measured export/layout gap remains. Verify Finnish diacritics, long titles, page breaks, embedded links, ATS text extraction, exact approved revision, and complete cover letter without placeholders.

Quality review should score relevance, specificity, evidence support, clarity, natural voice, language correctness, ATS parseability, completeness and editing effort. Do not claim a predictive "hiring percentage" from a resume score.

# 10. Candidate memory and jobs: start now, avoid blocking AutoApply

**Profile truth store:** typed contact, experience, education, skill and project evidence, links, preferred locations/arrangements, languages and scoped application answers. Every stored fact has source, revision, confirmation, validity, sensitivity, localization and scope. Ordinary stable answers may be saved after confirmation. Work eligibility is jurisdiction-specific; salary needs currency and period; legal attestations remain exact-question decisions. New CVs merge by diff rather than overwriting confirmed evidence.

**Opportunity engine:** Preserve Finland-focused KEHA and authorized source ingestion, canonical job identities, freshness, exact application URLs and existing user filters. Show clear qualification requirements, two evidence-backed fit reasons and one meaningful gap; don't suppress adjacent roles because the candidate changes careers. Job discovery and application execution are **separately measured**. A newly added job must actually continue to the chosen mode's next action rather than becoming a dead saved item.

**Tracking and outcome learning:** Start from actual case events. Later opt-in email synchronization may classify replies, offers and rejections, and draft follow-ups. Measure qualified interviews per active candidate hour as a longer-run north star, but do not confuse correlation with causality or delay today's application acceptance waiting for outcomes.

# 11. Aggressive reuse: exact donors, not wholesale takeovers

This section converts the previous 30-repository research into a **speed-ranked, executable intake**. Repo names/paths below come from the previous paper plus live GitHub file checks for the highest-priority donors. Pin the precise working commit before copying and record a source hash. "Sanitize" means remove unsuitable behavior, permissions, telemetry, prompts, secrets and brittle matches — **not** erase provenance or license notices. Installed dependencies are preferable to copying large maintained frameworks.

## 11.1 Start copying/adapting these proven units immediately

| Donor and exact source seam | What to adopt *today* | Required sanitization / acceptance |
|---|---|---|
| `galapoto/smartploy` PR #299 and current main | Existing application/workspace, UI modes, typed packets, extension, bridge, prior matcher changes | Extract small cohesive patches; preserve identity, packet guards and native CI; verify public deployment |
| `obumai/obumellm` `obumellm/browser/fill.py`, `live_session.py` | Visible Playwright, selector strategy and session handling already reused in SmartPloy | Map to SmartPloy tenant/lease/policy; never import ObumAI's private database or user cookies |
| `AhmadHassan-BTed/FormFilla` `src/content/fill/combobox-adapter.ts` | Native value setting, portal-mounted listbox, MutationObserver wait and owner-aware selection | Eliminate guessy fuzzy selection/global fallbacks; verify actual selected ID and stable display |
| `vesaias/JobNavigator` `extension/lib/ats_combobox.js` and `extension/lib/autofill_match.js` | MV3-compatible custom widgets, field/option matching and extension flow | Unicode-safe normalized exact aliases; reject `authorized` vs `not authorized`; retain upstream `freehire` attribution |
| `feder-cr/Jobs_Applier_AI_Agent` `src/aihawk/plugins/lever.md` | Lever upload/field-order knowledge, distinction between upload success and application receipt | Translate into adapter fixtures, **not** unrestricted agent prompts or guessed answers |
| `vaibhavarora14/job-application-agent` `scripts/ats/submit-adapters.mjs` | Receipt classification cases and ATS-specific checks | Exact host/job/session binding; thank-you text alone cannot confirm delivery |
| `srbhr/Resume-Matcher` `apps/backend/app/services/resume_preservation.py` | Deterministic preservation of employer, dates, degree and numeric facts | Adapt to approved SmartPloy fact IDs and test conflicting inputs |
| `career-ops-hq/career-ops` `verify-cv-facts.mjs` | Document fact-checking plus selected ATS identification/follow-up logic | Give explicit source inputs, block implicit file discovery and unapproved sends |
| `shadcn-ui/ui` composable Card primitives | Small semantic card anatomy and presentational building blocks | Rebuild in existing styling/tokens, no wholesale design-system migration |
| `TanStack/query` package | Independent query caching, dedupe, loading and cancellation | Key by tenant/session generation; no persistent cache of private CVs, grants or secrets |
| `adobe/react-spectrum` React Aria primitives | Keyboard-safe combo/selection, dialog and focus behavior | Use selected components, keep original SmartPloy visual identity |

**Rule:** Adapt small pure helpers by copying source with attribution; import stable libraries as version-pinned packages. The first two donor lanes (combobox + verified job-specific action), the fact-check lane and the UI card lane can be executed **in parallel today**.

## 11.2 Sophisticated repos that start as benchmark challengers, not blockers

| Repository | Appropriate role | P0 decision |
|---|---|---|
| `browser-use/browser-use` | Python browser reasoning/observation challenger; can target local or remote browser | Same-form comparison behind existing controller; do not replace Playwright today |
| `browserbase/stagehand` | Hybrid observe/act/extract and cached action patterns; current upstream also offers Python/Go | Test against same unresolved-form corpus; use only if better accuracy/cost |
| `microsoft/playwright` | Primary browser dependency, actionability, tracing, locators, file upload | **Retain and deepen now** |
| `microsoft/playwright-mcp` | Optional bounded agent-tool facade | No additional autonomous control plane today |
| `Skyvern-AI/skyvern` | Visual automation comparison | Hold out of P0; heavier stack and license review before direct import |
| `langchain-ai/langgraph` | Optional workflow interruptions/checkpoints | No duplicate application state machine today |
| `temporalio/temporal` | Later durable distributed scheduling | Do not commission another cluster during first release |
| `reactive-resume/reactive-resume` | Templates/schema if current export is inadequate | Compare, then adopt a limited adapter only |
| `rendercv/rendercv` | Typographic and ATS extraction benchmark | Keep existing renderer until regression proof shows a gain |
| `speedyapply/JobSpy` | Discovery source supplement | Does not fix applications; do not displace KEHA |
| `morluto/rea` | Reverse-engineer and map code relationships and donor surfaces | **Use now as audit/reuse accelerator**, never treat static analysis as live browser proof |

Remaining historical comparison repos from the previous survey (`strelov1/freehire`, `DaKheera47/job-ops`, `GodsScion/Auto_job_applier_linkedIn`, `wodsuz/EasyApplyJobsBot`, `NathanDuma/LinkedIn-Easy-Apply-Bot`, `FarzamHejaziK/claude-linkedin-assistant`, `Br1an67/OpenJobAutofill`, `Liam-Frost/AutoApply`, `tmwclaxton/autoapplycv`, `xitanggg/open-resume`) may contribute **individual tested techniques**, but do not become P0 dependencies. Some have different license conditions, unresolved metadata, older selectors or large integration surface. Never copy a whole unattended mass-application bot merely because it has many stars.

**Internal reuse map:** `obumai/ObumAICore` for shared policy/identity ideas, `obumai/obumbrowse` for isolated browsing/evidence design, `obumai/ObumConnect` for bounded provider adapters, `obumai/ObumKnowledge` for candidate-evidence indexing patterns, `obumai/ObumForge` for build/package automation, `obumai/ObumBench` for acceptance benchmarking, `obumai/ObumStudio` for visual composition and `obumai/obumellm` for browser-session and local inference ideas. **These are integration candidates, not verified ready-to-copy implementations**; individual files must be re-inspected before transplantation. Preserve repository boundaries and avoid hidden cross-database dependencies.

## 11.3 The rapid sanitized-code adoption protocol

```text
1. Pin exact upstream commit and source path; record URL, hash, license, notices.
2. Characterize behavior with a minimal failing SmartPloy fixture.
3. Extract the smallest useful pure unit into a named adapter, NOT an entire repo.
4. Strip donor-specific accounts, telemetry, credentials, global browser rights,
   broad origin access, unauthorized actions, guessed profile answers and prompts.
5. Replace fuzzy matching with approved typed values; instrument observed effect.
6. Run normal/negative/injection/Unicode/ambiguous-option tests on both executors.
7. Run REA/static and dependency analysis; review transitive dependencies.
8. Benchmark against existing behavior on the identical fixture and candidate data.
9. Commit one source manifest + regression fixture + owner + rollback feature flag.
10. Qualify exact SHA in native CI, deploy if safe, verify signed-in public UI.
```

No dependency may silently obtain cookies or send candidate materials. No employer page may rewrite SmartPloy's system policy through prompt injection. This is aggressive reuse **with bounded authority**, the fastest way to avoid debugging a huge copied codebase later.

# 12. Test matrix: what makes today's build credible

**Minimum real-path acceptance** covers one complete authorized supported employer form on each of the two existing desktop executors; a controlled test environment is used for destructive edge cases. The candidate's actual sending must never be performed without their specific authorization. The team needs an explicit P0 release matrix, not only unit tests.

| Test ID | Candidate action / failure | Required expected outcome |
|---|---|---|
| P0-01 | Upload CV and choose mode | Same approved CV persists; route advances to selected job |
| P0-02 | Add external job link | Canonical correct form opens; job identity checked after redirect |
| P0-03 | React text, delayed options, custom location | Exact selected and persisted values; wrong city blocked |
| P0-04 | Select, radio, checkbox, number, date | Approved semantics; unknown/sensitive prompts the user |
| P0-05 | Upload exact CV and tailored letter | Acknowledgment observed and bound to current hash |
| P0-06 | Conditional question and next step | New required controls re-observed; no old locator reused |
| P0-07 | Pause, take over, reconnect | One control owner, resumption from fresh observation |
| P0-08 | Refresh, browser process restart, server restart | Durable case/packet state; no repeated upload or send |
| P0-09 | Unauthorized submit, stale packet, wrong origin | Action denied, no employer send, comprehensible UI message |
| P0-10 | Network loss immediately after permitted submit | Mark `unknown`, reconcile before any resend |
| P0-11 | Two accounts with colliding job/case identifiers | No private data leakage via API, browser, queue or cache |
| P0-12 | Finnish/English docs, mobile, dark mode, 200% zoom | Complete exports and usable UI; no clipping, dead buttons or hidden actions |

**Same-day exit gate:** all critical negative tests pass; a controlled full-journey fixture passes extension and local Playwright; an authorized live employer journey has been observed on the exact deployed artifact for the advertised capability; no unapproved send, false confirmation, cross-tenant leak, fabricated fact or duplicate attempt has occurred. If the real-site test remains unavailable, **limit release claims accordingly**.

**Expansion benchmarks**, run while day-zero feature shipping continues: 30 rapid fixtures on every change; 200 versioned complete cases for the first pilot; 1,000+ across varied ATS/custom forms, multilingual and held-out designs for broad coverage; then longer real-request measurement. Target ≥95% eligible-case pilot completion and ultimately ≥99% for declared mature families, with `n/N`, uncertainty and unsupported share. These are **targets**, not current rates.

# 13. Performance, reliability and operational truth

Fix the user-visible loading gate in `web/src/App.tsx`. Render the shell before dashboard/search queries finish. Split panel loading and error handling; add bounded request deadlines, cancellation and tenant/session-aware TanStack Query; never cache private candidate documents in a shared CDN. The original analysis found an `App.tsx` loading waterfall, grouped secondary requests and operational source widgets in applicant views. Address these through request boundaries and allowlisted DTOs rather than concealment.

**First-day UI budgets:** visible local click feedback within 100 ms where feasible; a nonblocking shell; real case-accepted/queued state within ~1 second from server acknowledgment; truthful connected-stage feedback promptly after actual browser connection. **Field monitoring goals, not promised measurements:** p75 LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1, and warm navigation without disruptive full-screen loading. Employer page latency must be measured separately from SmartPloy's own overhead.

Separate document/model queues from interactive reads; do not run expensive ranking, browser work and PDF production within the same latency-critical request. Add feature-level error tracking and sanitized trace playback for operators. Track real hosted-browser minute cost and avoid unbounded model retry loops.

# 14. Feature-first deployment and hard production gate

Use the repository's existing **Woodpecker/native deployment** process. The inspected `deploy/personal/scripts/deploy.sh` requires an approved immutable 40-character SHA and checks that it is an approved `origin/main` artifact before deployment. It also enforces runtime and identity policy; do not bypass any of these checks to gain speed.

**State ledger:** `source_ready` → `CI_qualified` → `staged_accepted` → `released` → `signed_in_user_verified` → `field_validated`. Every state carries its own evidence; a green source/test status does not imply deployment. Release schema must record: SHA, CI run, build/image digest, UI/API/helper versions, feature flag/cohort, UTC timestamp, executed journey, sanitized trace reference, reviewer and rollback SHA.

## 14.1 Production rollout recipe for each useful slice

1. Build a branch from the current verified main, or extract a minimal patch from PR #299; prove exact base compatibility.
2. Write one real candidate action and all significant failure-path tests.
3. Reuse existing API, persistence, current identity and feature flags; keep database migrations backward-compatible.
4. Run focused unit tests, contract parity, security negatives and the exact-artifact browser journey.
5. Get authorized approval, land the reviewed commit in main and run the native deployment with its immutable SHA.
6. Verify login, public UI route, correct browser executor, user-action success and exact SHA agreement.
7. Save production receipt; expose feature immediately to its intended cohort. Expand after safe canary data.
8. If any invariant fails, disable or roll back that capability; preserve in-flight application evidence and user documents.

**Do not manufacture a successful demo** by editing the public UI only. A click that starts a toy animation is a regression, not a release.

## 14.2 Example release verification commands (authorized operator only)

```bash
REPO=/srv/obum/stacks/smartploy
sudo git -C "$REPO" fetch --no-tags origin main
sudo git -C "$REPO" rev-parse origin/main
# Set SHA only after source review and CI qualification.
SHA=<approved-40-character-main-commit>
# Execute only under the existing authorized deployment policy.
sudo env SMARTPLOY_RELEASE_APPROVED_SHA="$SHA" \
  bash "$REPO/deploy/personal/scripts/deploy.sh" "$SHA"
# Use the product's online release evidence/acceptance script, then
# separately verify a signed-in candidate path and real browser behavior.
sudo env SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc \
  bash "$REPO/deploy/personal/scripts/release-evidence.sh" --online
```

Replace the example identity profile with the environment's verified configured mode; **do not** assume OIDC/Cloudflare values. This is an operator runbook, not evidence that any command was executed here.

# 15. Six lanes, one integration contract, nonstop delivery

| Lane / owner role | First user-visible release | Parallel follow-on that starts now | Merge ownership |
|---|---|---|---|
| A — Integration/release | Public UI displays exact qualified new feature; release ledger | Automated per-slice evidence and rollback | Sole production integrator |
| B — Playwright execution | Real supported form fill/upload/review, pause/resume | Semantic engine, conditional steps, second ATS | Execution-contract owner |
| C — Extension execution | Same verified field corpus in real active browser tab/side panel | Additional widgets, session recovery, robust MV3 delivery | Browser-parity owner |
| D — Documents/profile | Complete truthful CV/letter edit + export | Reusable question memory, richer evidence graph | Candidate-fact contract owner |
| E — Product UI/design | Immediate shell, sidebar, cards, actual Apply controls | Responsive live/Focus views, mobile hosted takeover | Design-system owner |
| F — Independent QA/security/ops | Negative test corpus + signed-in release acceptance | Hosted isolation, 200/1,000-case benchmarks, performance | Independent veto on critical defects |

**Shadow capability workers:** Hosted browser isolation, job matching/KEHA quality, future ATS adapters, and outcome learning can run in additional isolated branches if human or agent capacity permits. They must use the locked contract and never compete for the release owner's attention with a failed P0 journey. Each lane files small PRs, attaches evidence and stops changing shared schemas without integration-owner approval. No sprint-end batch deployment; release by **qualified useful feature**.

# 16. Priorities after the first accepted release — already in motion

**Next 24–72 hours (conditional, not a deferred start):** Expand one more ATS family, improve form-label/option reasoning, get controlled hosted isolation working, make all primary UI states visually consistent, complete document-quality blind review, and maintain a production failure corpus. Ship each accepted improvement as soon as independently useful.

**Next 1–2 weeks:** Move from selected ATS fingerprinting toward broad semantic form coverage, stronger unknown-site handoff, private hosted browser on mobile, richer question memory and career evidence, accessible UI study, Firefox/other Chromium variants where supported, and measured unit economics. Each of these should already have an owner and a same-day starter branch.

**Next 30–90 days:** More regional capability packs, verified employer-source partnerships, cross-ATS document consistency, application response tracking, candidate interview preparation, independent comparative benchmarking and realistic customer pricing. No market is marked supported until its language, document quality, employer forms, permissions and operating model pass local tests.

**North-star:** candidate-confirmed qualified interviews per active hour of candidate effort. **Immediate health metrics:** all-request useful completion, eligible-case correctness, unsupported share, no false-positive receipts, no duplicate sends, user interventions, p50/p95 time, exact export quality, signed-in release frequency and cost per confirmed application.

# 17. Release blockers, recoveries and honest limits

| Critical blocker | Required resolution / user message |
|---|---|
| Correct job cannot be established after redirect | Stop and show exact employer URL for manual verification |
| Missing or conflicting sensitive answer | Ask user with exact employer wording; never infer from CV or another country |
| Unsupported widget/anti-automation restriction | Pause or offer manual handoff; no stealth bypass or fake completion |
| Browser login or CAPTCHA | User takes over; resume after fresh observation |
| CV and packet hashes differ | Rebuild packet and renew approval before any external action |
| Browser crashes mid-form | Restore durable case; re-observe before continuing |
| Browser disconnects after submission click | Outcome unknown; investigate employer evidence; no blind retry |
| UI new release breaks identity or private routes | Halt canary, roll back feature; preserve cases and receipts |
| Accessibility failure hides Stop/Review at zoom | Block visual release until action is usable with keyboard and narrow viewport |

**The limits of "perfect":** No system controls every external employer site, authentication challenge, network, language or user's evidence. Today can produce a premium, responsibly working **first supported capability** and start all expansion lanes. It cannot honestly certify 100% worldwide AutoApply or an independently won design award before evidence exists. Do not let that limit dilute the urgency of shipping what *is* safely possible now.

# 18. Builder execution order — the definitive handoff

**Do these steps in this order, with other lanes active in parallel:**

1. Inspect the actual 7 November live environment; reconcile current main, PR #299, running release, signed-in UI and permitted employer test. Document only verified facts.
2. Lock minimal `Case/Packet/Observation/Action/Receipt` protocol; keep existing API/database as authority.
3. Extract small complete fixes from the integration rather than merging hundreds of unrelated changes; preserve current approved deployment and OIDC safeguards.
4. In local Playwright and extension, replace blanket field-type rejection with typed, candidate-approved field policies; port FormFilla/JobNavigator matching and existing ObumAI browser behavior; verify every action.
5. Complete one real employer form through **ready-for-review** with upload, missing question, step transition, pause and resume. Submit only with explicit current case authorization; preserve true receipt or unknown.
6. In parallel, ship complete editable truthful CV/letter + PDF/DOCX exports, and premium responsive Home/Jobs/Apply UI with the real SmartPloy logo, Finland home banner, collapsing sidebar and connected browser workspace.
7. Run independent exact-artifact acceptance on both desktop executors; deploy each accepted full-use slice immediately; verify under a real signed-in intended account and record SHA plus trace.
8. Continue parallel semantic, hosted, additional ATS, intelligence, outcome and global lanes without accumulating completed code in a mega-branch.

**Final acceptance decision:** Approve this V4 implementation contract for immediate engineering use. Approval is **not** a claim that production features are already complete. The first decisive artifact must be a working signed-in candidate journey, not another paper.

\newpage

# Appendix A. Repository and file-target manifest

**SmartPloy current-source targets (GitHub checked 7 Nov 2026):**

* `https://github.com/galapoto/smartploy/pull/299` — integration head and extraction candidate (`d44221b29105…`, open at inspection).
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/browser-playwright/assistant.py` — partial-control parser/filler.
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/browser-playwright/bridge.py` — loopback controlled browser.
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/browser-companion/logic.mjs` — packet identity/origin security.
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/web/src/ApplicationStudio.tsx` — candidate application state, documents and browser controls.
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/web/src/ApplicationJourney.tsx` — CV/mode/job progression.
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/web/src/StartChoices.tsx` — CV-first mode selection.
* `https://github.com/galapoto/smartploy/blob/d44221b2910546d4fd4a87c0bd8d3d58f217bb90/web/src/BrandMark.tsx` — actual brand vector and colors.
* `https://github.com/galapoto/smartploy/blob/main/deploy/personal/scripts/deploy.sh` — exact-SHA native release gate.

**High-priority checked upstream seams:**

* `https://github.com/obumai/obumellm/blob/d682da2582ebfa3f013cf37dc542384fe605f303/obumellm/browser/fill.py`
* `https://github.com/obumai/obumellm/blob/d682da2582ebfa3f013cf37dc542384fe605f303/obumellm/browser/live_session.py`
* `https://github.com/AhmadHassan-BTed/FormFilla/blob/main/src/content/fill/combobox-adapter.ts`
* `https://github.com/vesaias/JobNavigator/blob/main/extension/lib/ats_combobox.js`
* `https://github.com/vesaias/JobNavigator/blob/main/extension/lib/autofill_match.js`
* `https://github.com/feder-cr/Jobs_Applier_AI_Agent/blob/main/src/aihawk/plugins/lever.md`
* `https://github.com/srbhr/Resume-Matcher/blob/main/apps/backend/app/services/resume_preservation.py`
* `https://github.com/career-ops-hq/career-ops/blob/main/verify-cv-facts.mjs`
* `https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/card.tsx`
* `https://github.com/browserbase/stagehand` and `https://github.com/browser-use/browser-use` — separately benchmarked challengers.
* `https://github.com/morluto/rea` — reverse-engineering and code relationships.

The `main` links above are discovery links, **not immutable copy pins**. Before adoption, resolve and record each specific upstream commit and file SHA, compare it with the previously inspected V2 pins, preserve license/attribution and freeze it in `reuse-manifest.yaml`. Internal private sources require authorized repository access.

# Appendix B. Minimum `reuse-manifest.yaml` template

```yaml
schema: smartploy.reuse.v1
capability: custom-combobox
source_repo: AhmadHassan-BTed/FormFilla
source_path: src/content/fill/combobox-adapter.ts
source_commit: REPLACE_WITH_VERIFIED_40_HEX_SHA
source_sha256: REPLACE_WITH_VERIFIED_SHA256
license_and_notices: RECORDED_FROM_PINNED_COMMIT
local_adapter: browser-companion/adapters/combobox.mjs
modifications:
  - exact-approved-option-only
  - owning-listbox-and-frame-binding
  - stable-selected-value-verification
forbidden:
  - global-fuzzy-first-match
  - implicit-user-attribute-inference
  - cross-origin-credential-access
tests:
  - controlled-react-select
  - portal-popover-and-delayed-options
  - unicode-option-collision
  - authorization-negative-wording
  - extension-and-playwright-parity
owner: BROWSER_PARITY_OWNER
release_flag: autoapply_combobox_v1
```

# Appendix C. Status receipt required after every feature release

```json
{
  "feature": "autoapply.reviewable_form_v1",
  "source_sha": "<40-hex-approved-commit>",
  "ci_run": "<native-ci-id>",
  "artifact_digest": "<approved-image-digest>",
  "running_ui_sha": "<observed-UI-version>",
  "running_api_sha": "<observed-API-version>",
  "executor": "extension|local_playwright|hosted_playwright",
  "case_id": "<redacted-case-reference>",
  "employer_family": "<observed-ATS-or-custom>",
  "exact_job_verified": true,
  "approved_packet_verified": true,
  "required_controls_verified": true,
  "approved_upload_observed": true,
  "review_state_observed": true,
  "submission_outcome": "not_attempted|confirmed|rejected|unknown",
  "sanitized_trace_ref": "<audit-reference>",
  "signed_in_public_ui_verified": true,
  "rollback_sha": "<last-known-good-commit>",
  "utc_observed_at": "<actual-UTC-timestamp>"
}
```

The schema above is a **template, not an actual release receipt**. A deployment dashboard must reject `verified=true` unless its fields come from real run evidence and the exact artifact comparison passes.

# Sources and provenance

**Provided source documents** (read and synthesized, 7 Nov 2026):

1. *SmartPloy AutoApply and UI Build Paper* (36 pp.), particularly pp. 3–14 and 20–32.
2. *My critical review of the SmartPloy paper* (10 pp.), especially pp. 3–9.
3. *SmartPloy Final Product and Build Specification* V2 (55 pp.), especially pp. 6–18, 31–48 and 49–50.
4. *SmartPloy V3 Near-10 World-Class Blueprint* (18 pp.), especially pp. 2–16.
5. *SmartPloy V3 Source and Visuals* ZIP (Markdown source, four illustrations, print stylesheet).

**Fresh external verification for this edition:** live GitHub repository metadata, main branch, PR #299, exact SmartPloy/ObumAI source files and selected FormFilla, JobNavigator, AIHawk, Resume Matcher, career-ops and shadcn source files via connected GitHub on 7 Nov 2026. The main and PR facts are described above. `https://github.com/galapoto/smartploy`.

**Primary technical references:** `https://playwright.dev/docs/actionability`; `https://playwright.dev/docs/trace-viewer`; `https://www.w3.org/TR/WCAG22/`; `https://owasp.org/www-project-top-10-for-large-language-model-applications/`; `https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en`.

**Research comparison, not product proof:** `https://github.com/browserbase/stagehand`, `https://github.com/browser-use/browser-use`, `https://github.com/vesaias/JobNavigator`. Vendor READMEs and earlier reviewed competitor descriptions are not independent evidence that their automation is successful on SmartPloy's target employer sites.

**Explicit exclusions from evidence:** no signed-in production browser test, no current public release-manifest read, no exact-permission real submission, no new deployed SmartPloy code, no independently measured 9.x rating. This report provides precise instructions to obtain those proofs.

---

**THE BUILD RULE**  
*Every independently qualified, genuinely useful feature must become immediately reachable and usable from the public SmartPloy product, with its own verifiable release record. Do not accumulate completed features behind a future whole-application launch. Today begins with an actual employer application and a product-quality interface; tomorrow's breadth is already being built in parallel.*
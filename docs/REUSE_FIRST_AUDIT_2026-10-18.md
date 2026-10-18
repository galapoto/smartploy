# SmartPloy — Reuse-first evidence and source audit
**Date:** 2026-10-18 (Europe/Helsinki). **Scope:** planning/research only.  
**Source of decisions:** [PROJECT_PLAN.md](PROJECT_PLAN.md). **Operational tracker:** [issue #88](https://github.com/galapoto/smartploy/issues/88).  
**Method:** live connected GitHub API repository inventories, selected current/default-branch source trees and actual files (including selected *unmerged* ObumAI branches), original YouTube/TikTok video metadata when accessible, project LICENSE and documentation. Not a dynamic software test, complete legal review, complete supply-chain audit, or signed-in user acceptance. Direct social-video claims are not treated as verified submissions.

## 1. What we counted — 44 internal + 22 external candidates

**Internal catalog: 44 GitHub repositories.** Four connected source owners were inventoried: `obumai` (11), `galapoto` (21), `Nordvantage` (5) and `komplyint` (7). Inventory means the repo exists and its published metadata/title was inspected. Only explicitly mentioned high-relevance code was inspected more deeply. Several specialist agent repos have *unmerged review branches* with substantial code while `main` contains only README/AGENTS. The actual running Core/OVH services and local offline archive were **not** accessed.

**External catalog: 22 repository families.** The AIHawk fork family is counted once despite multiple forks with differing license terms. **13** have a primary MIT/Apache declaration and merit selective code review, **9** have no license, GPL/AGPL, Commons Clause or source-use restriction and are not approved for copying into a proprietary hosted service. Some of those 13 also have **website terms restrictions** or unsafe cloud egress, so the figure is **not 13 approved imports**.

**Usable subsystem candidates, not complete integrations:** 15 families, documented in [PROJECT_PLAN.md](PROJECT_PLAN.md). Counts are not additive with repository counts. This audit **changes documentation only**: no third-party code copied or dependencies installed.

### Legend

- **Reuse-now-candidate:** a named existing capability to audit/pin/reuse when implementation is authorized, NOT shipped.
- **Candidate-draft:** functionality exists on a GitHub draft review ref, NOT automatically in production.
- **Evaluate:** may be useful but often overkill for MVP, or conflicts with a canonical SmartPloy module.
- **Context only:** no direct job-applicator value or no qualifying implementation.
- **NO COPY:** no commercial source grant or blocked licensing; modify/rewording does **not** cure the restriction.

## 2. Every internal repository and selective source evidence

### obumai (11)

| Repository | Source evidence / findings | Reuse decision |
|---|---|---|
| [obumai/obumellm](https://github.com/obumai/obumellm) | Active private runtime `main`: **24** `obumellm/application/*.py` and **17** `obumellm/browser/*.py` modules. Read `application/job_application_agent.py`, `form_mapper.py`, `browser_apply.py`, `upload_policy.py`, `final_submit_preflight.py`, `evidence_vault.py`; `browser/live_session.py`, `upload_plan.py`, `submit_packet.py`, `live_autopilot.py`. Real Playwright persistent-context code; doc generator, job application drafting and strict preflight. `job_application_agent.py` states **no live-board search, upload or submit**; upload planner stages locally and never performs employer upload. | **Primary same-owner API/functionality to reuse**. Keep independent SmartPloy profile/auth/DB; use versioned ObumAI contract. |
| [obumai/ObumAICore](https://github.com/obumai/ObumAICore) | Engineering/leadership repository, default branch README; executable source still lives in `obumellm`. | Coordination and product constraints; no duplicate runtime. |
| [obumai/obumbrowse](https://github.com/obumai/obumbrowse) | Default branch only charter. Unmerged draft source includes Go HTTPS reader, bounded responses, source evidence/headers, offline browser fixture and consent/action-policy drafts; inspected example draft `6106970961fe50e94fe0ff93234c1009dbcac155` with ~60 files and tests. | **Candidate-draft** for permission-safe browser/source inspection; do not claim executable product. |
| [obumai/ObumConnect](https://github.com/obumai/ObumConnect) | Default branch charter, draft kickoff and offline OAuth/provider simulations; no verified production ATS tokens. | Connector authorization patterns after integration proof; not a source of ATS credentials. |
| [obumai/ObumForge](https://github.com/obumai/ObumForge) | Default branch charter; numerous review branches for offline rootless CI/checkout provenance/process cleanup. | Development/testing reuse, not application logic. |
| [obumai/ObumKnowledge](https://github.com/obumai/ObumKnowledge) | Draft `7cdebd5b0406df45ec5648ff5665600bf168a683` contains ~94 files incl. consented memory, encrypted source store, FI/EN retrieval tests and key rotation; default branch only charter. | **Candidate-draft** for evidence provenance, retrieval and erasure; test privacy/tenant binding first. |
| [obumai/ObumStudio](https://github.com/obumai/ObumStudio) | Review-only PDF/DOCX and locale-related branch work (e.g. `feature/studio-product-01-real-pdf-docx`); latest independent `feature/studio-reuse-xlsxwriter-offline-v1` addresses XLSX, not SmartPloy. | **Candidate-draft** document renderer; do not rebuild output formats when tested versioned service available. |
| [obumai/ObumBench](https://github.com/obumai/ObumBench) | Draft frozen FI/YKI test data, independent evaluations and Promptfoo reuse; no live AutoApply browser tests. | Shared evaluation harness after acceptance; actual Finnish job samples still required. |
| [obumai/obumspeech](https://github.com/obumai/obumspeech) | FI/EN speech and audio integrity experimental drafts, source default small. | Optional accessible notifications in later release; not on AutoApply critical path. |
| [obumai/ObumSteward](https://github.com/obumai/ObumSteward) | Review/oversight root README. | Independent release/privacy review, not executor. |
| [obumai/obum-delivery](https://github.com/obumai/obum-delivery) | Woodpecker KVM isolated worker and artifact/release infrastructure; product admission remains independently reviewed. | Separate CI and trusted deployment infrastructure; **do not gate product coding on this platform redesign**. |

**Critical non-duplication proof:** Do not recreate `cv_tailor.py`, `cover_letter.py`, `questionnaire.py`, `evidence_vault.py`, `form_mapper.py`, `live_session.py`, `upload_plan.py`, `final_submit_preflight.py` before a REUSE-CHECK demonstrating an unrecoverable gap. Conversely, code that **only stages an upload** is not evidence of completed employer attachment.

### galapoto (21)

| Repository | Reuse decision |
|---|---|
| [galapoto/smartploy](https://github.com/galapoto/smartploy) | **Primary product foundation.** `main@d0ebe59...`; review-only [#149](https://github.com/galapoto/smartploy/pull/149) at `ca56d17...`. `smartploy/sources/`, account-scoped application workspace/CRM, `browser-companion/`, document download; no demonstrated unattended employer submit or production rollout of the draft. |
| [galapoto/vakevahti](https://github.com/galapoto/vakevahti) | **Selectively reuse** durable notification/outbox, leases and report-delivery concepts from `backend/alembic/versions/20260911_0004_notification_outbox.py` and `...0005_notification_outbox_leases.py`; domain is funding monitoring, so adapt via a narrow adapter rather than copying its entire backend. |
| [galapoto/Robot-framework-projects](https://github.com/galapoto/Robot-framework-projects) | Selective UI/form/API testing patterns; older demos, no employer apply engine. |
| [galapoto/smart-pdf-chatbot](https://github.com/galapoto/smart-pdf-chatbot) | Document Q&A ideas, no material application subsystem established. |
| [galapoto/zeebe](https://github.com/galapoto/zeebe) | Workflow experimentation; not needed while SmartPloy has its own lease/CRM. |
| [galapoto/zeebe_testautomation](https://github.com/galapoto/zeebe_testautomation) | Test/workflow examples only. |
| [galapoto/Task](https://github.com/galapoto/Task) | Context only; no relevant code verified. |
| [galapoto/integrated-env-energy-health-pipeline](https://github.com/galapoto/integrated-env-energy-health-pipeline) | Domain-incompatible analytics pipeline; no copy needed. |
| [galapoto/PythonLearningJourney](https://github.com/galapoto/PythonLearningJourney) | Learning examples only. |
| [galapoto/qa_project](https://github.com/galapoto/qa_project) | Test patterns possible, not a job-application adapter. |
| [galapoto/Projects](https://github.com/galapoto/Projects) | Coordination; verify source assets before any reuse. |
| [galapoto/vaketomate](https://github.com/galapoto/vaketomate) | Domain-specific workflow; no high-priority SmartPloy component established. |
| [galapoto/sparkpoint-clean](https://github.com/galapoto/sparkpoint-clean) | Domain-specific; context only. |
| [galapoto/trading-platform](https://github.com/galapoto/trading-platform) | Trading; no job application reuse. |
| [galapoto/prismatic-v4](https://github.com/galapoto/prismatic-v4) | Trading; no job application reuse. |
| [galapoto/test-case-generator](https://github.com/galapoto/test-case-generator) | Potential test-generation patterns; not a product application engine. |
| [galapoto/fmi-energy-pipeline](https://github.com/galapoto/fmi-energy-pipeline) | Energy-data pipeline; context only. |
| [galapoto/Penetration-Testing-](https://github.com/galapoto/Penetration-Testing-) | Security test ideas only; no blind re-execution against employers. |
| [galapoto/Elisa](https://github.com/galapoto/Elisa) | Training/test code only. |
| [galapoto/crindex](https://github.com/galapoto/crindex) | Trading analytics; context only. |
| [galapoto/robot-api-testing](https://github.com/galapoto/robot-api-testing) | API QA examples; not a production job-apply subsystem. |

### Nordvantage (5)

| Repository | Reuse decision |
|---|---|
| [Nordvantage/NordVantage](https://github.com/Nordvantage/NordVantage) | Auth contracts, account/gateway policy tests and deployment-readiness designs; use only proven first-party identity patterns; identity ownership stays with SmartPloy/Obum Identity. |
| [Nordvantage/runtime_lead](https://github.com/Nordvantage/runtime_lead) | OIDC discovery, asset/website checks and self-hosted CI readiness; reuse test patterns. |
| [Nordvantage/OrderHarbor](https://github.com/Nordvantage/OrderHarbor) | Trading platform; no applicant workflow code verified. |
| [Nordvantage/AlphaLoom](https://github.com/Nordvantage/AlphaLoom) | Quant research; no job-submission code verified. |
| [Nordvantage/MintHawk](https://github.com/Nordvantage/MintHawk) | Trading platform; no applicant workflow code verified. |

### komplyint (7)

| Repository | Reuse decision |
|---|---|
| [komplyint/proctor](https://github.com/komplyint/proctor) | OIDC, tenant-scoped attestations, Go control API, language-specific safety events; selectively reuse design/testing contracts, never let candidate proctor control employer credentials. |
| [komplyint/veriscope](https://github.com/komplyint/veriscope) | Audit/evidence/API patterns from compliance SaaS; not direct application workflow. |
| [komplyint/todiscope-v3](https://github.com/komplyint/todiscope-v3) | Domain-specific compliance product; context only. |
| [komplyint/Todiscope](https://github.com/komplyint/Todiscope) | Domain-specific compliance product; context only. |
| [komplyint/Todiscope-v2-Engine](https://github.com/komplyint/Todiscope-v2-Engine) | Domain-specific compliance product; context only. |
| [komplyint/esg_carbon_saas_startup](https://github.com/komplyint/esg_carbon_saas_startup) | Domain-specific ESG; context only. |
| [komplyint/komplyint-website](https://github.com/komplyint/komplyint-website) | Company website; no AutoApply logic. |

## 3. Full external candidate matrix — 22 families

The following license values refer to **GitHub repository metadata/visible LICENSE on 2026-10-18**. Pin and examine the *specific files* and third-party dependencies before using. All "candidate" entries still require a dependency/security/data-egress audit and signed permission to use the *target employer site*. Social-media popularity is not evidence of software correctness.

| # | Repository and examined implementation | Primary license | SmartPloy use; decision and risk |
|---:|---|---|---|
| 1 | [career-ops](https://github.com/career-ops-hq/career-ops): `providers/`, `docs/SUPPORTED_JOB_BOARDS.md`, `docs/APPLY_AUTOFILL.md`, CV/cover-letter/tracker scripts | MIT | **P0 selective reuse candidate** for permitted ATS discovery, source liveness, Ashby/Greenhouse/Lever/Workable form quirks and claim grounding. Describes 55+ providers but many may be outside Finland or use non-authorized endpoints. Its README explicitly says **user clicks Submit**. Do not import its entire project or blindly enable providers. |
| 2 | [Browser Use](https://github.com/browser-use/browser-use): `browser_use/agent/`, `browser/`, `dom/`, `browser/watchdogs/` | MIT | **P1 conditional** browser executor/DOM navigation; benchmark vs ObumAI persistent Playwright first. Do not enable "stealth", CAPTCHA bypass, remote credential hosting or uncontrolled cloud AI. |
| 3 | [Stagehand](https://github.com/browserbase/stagehand): `packages/`, CLI extract/act, browser controls | MIT | **Alternative** to Browser Use for TS-based deterministic helpers, not additive second runtime. Decide based on measured existing-stack deficiency and dependency footprint. |
| 4 | [Resume Matcher](https://github.com/srbhr/Resume-Matcher): `apps/backend/app/services/ats.py`, `ats_parse/`, resume editor/export/fixtures | Apache-2.0 | **P0** ATS PDF extraction, parseability, document fact consistency and independent tests. Preserve NOTICE, identify sublicensed templates and fonts. |
| 5 | [Reactive Resume](https://github.com/reactive-resume/reactive-resume): `apps/`, `packages/`, PDF/DOCX export, ATS document options | MIT | **P1** document render templates or isolated export API; large 2,000+ file monorepo, high whole-app integration cost. Do not ship font/media without separate rights. |
| 6 | [JobSpy](https://github.com/speedyapply/JobSpy): employer/job board scraper library | MIT | **P1 conditional** for only sources whose access and republishing are authorized. **Never** assume LinkedIn/Indeed/Glassdoor scraping is permitted by software license. |
| 7 | [Hiring Agent](https://github.com/interviewstreet/hiring-agent): `evaluator.py`, `score.py`, scoring prompts | MIT | **P2** evaluation methodology; applicant scoring is not automatically fair or accurate, and SmartPloy already has a ranking engine. |
| 8 | [ResumeSkills](https://github.com/Paramchoudhary/ResumeSkills): prompt/checklist assets | MIT | **P2** reusable writing-review ideas with attribution; not a job submission runtime. |
| 9 | [Yaima/agent-apply](https://github.com/Yaima/agent-apply): `agent/forms/apply.py`, `agent/forms/common.py`, `agent/tracker.py`, `tests/` | MIT | **P0** supported Greenhouse/Lever assisted form fill, liveness/Exceptions/manual tail, no guesses for authorization, separate human final action and duplicate skipping. README says no unattended submit. Its personal spreadsheet tracker must map to tenant-scoped SmartPloy PostgreSQL. |
| 10 | [ApplyAI](https://github.com/muhammad-saadd/applyai): MV3 `content_scripts/{greenhouse,lever,ashby,workday,generic}.js`, `manifest.json`, `utils/ai.js` | MIT | **P0** field-detector patterns; **safety gap:** README says browser-local storage but OpenAI requests transmit resume/job data externally. Manifest has broad `https://*.lever.co/*` etc host permissions. Do not directly lift network/permission design; use exact-host, consented local-first SmartPloy API. |
| 11 | [neonwatty/job-apply-plugin](https://github.com/neonwatty/job-apply-plugin): `scripts/job-apply-store.py`, `scripts/job_apply_policy.py`, `qa/`, `tests/` | MIT | **P0** answer confidence and provenance ledger, sensitive answer retention policy, synthetic sanitized browser replay/privacy checks. ATS flows are guided and explicitly **not** live verified for all portals. |
| 12 | [AbhishekMandapmalvi/AutoApply](https://github.com/AbhishekMandapmalvi/AutoApply): `bot/apply/{base,lever,greenhouse,ashby,workday}.py`, `core/resume_*.py`, tests | MIT | **P1 conditional** provider-specific upload/form handling. README says educational/personal use in disclaimer; review final text/rights and code before commercial adoption. LinkedIn/Indeed modules not permitted automation targets. |
| 13 | [GodsScion LinkedIn applier](https://github.com/GodsScion/Auto_job_applier_linkedIn): browser/selector tests | MIT | **Platform restriction**: LinkedIn disallows unauthorized automated extensions, scraping and website activity. Generic isolated tests only if needed; no live LinkedIn apply or bots. |
| 14 | [Skyvern](https://github.com/Skyvern-AI/skyvern): AI browser automation | AGPL-3.0 | **License hold:** public network service/source obligations, counsel/architecture review or separate authorized commercial license; no embedding/copying into planned closed-source SmartPloy as-is. |
| 15 | [AIHawk fork family](https://github.com/Karinza38/Auto_Jobs_Applier_AIHawk), [Commons Clause example](https://github.com/samolat/Auto_Jobs_Applier_AIHawk) | AGPL or MIT **plus Commons Clause**, varies by source/fork | **License hold:** no assumption that the viral project's code is permissive or sublicensable for a paid SaaS. Modifying cannot cure Commons Clause/copyright; permission or independently designed implementation only. |
| 16 | [n8n](https://github.com/n8n-io/n8n) | Sustainable Use/source-available (GitHub `NOASSERTION`) | **License/architecture hold:** do not embed/rebrand as customer-configurable SaaS without written commercial compatibility review. SmartPloy and Vakevahti already have worker/job scheduling. |
| 17 | [dyyfk/auto-apply](https://github.com/dyyfk/auto-apply): `scripts/scout.js`, `scripts/apply.js`, `server/`, `client/` | **No LICENSE found** | **NO COPY.** Detailed public README describes Ashby/Greenhouse/Lever submissions, durable claim/dedup and rate policies, relevant as **independent design requirements only**. No license = all-rights-reserved default. |
| 18 | [dabloo26/job-application-agent](https://github.com/dabloo26/job-application-agent): `backend/services/browser/{automation,confirmation,mapper}.py`, many synthetic fixtures | **No LICENSE found** | **NO COPY.** Strong reference for deterministic fail-closed submission policy and adversarial fixture *ideas*, but not permission to reuse its files. |
| 19 | [tmason10/job-application-automation](https://github.com/tmason10/job-application-automation): 11-file Playwright demonstrator | **No LICENSE found** | **NO COPY.** Tiny/untested broad ATS support claims; reference architecture ideas only. |
| 20 | [EricTechPro/ai-job-automation](https://github.com/EricTechPro/ai-job-automation): 27-file project named in video, browser manager, job tracker | **No LICENSE found** | **NO COPY.** Marketing video promotes CAPTCHA/anti-bot bypass and cloud automation. Prohibited SmartPloy scope; no unrestricted content rights. |
| 21 | [EasyApplyBot](https://github.com/madingess/EasyApplyBot) | GPL-3.0 | **License hold + LinkedIn policy:** don't embed in closed-source service. |
| 22 | [NathanDuma LinkedIn Easy Apply Bot](https://github.com/NathanDuma/LinkedIn-Easy-Apply-Bot) | **No detected license** | **NO COPY;** stale and platform-restricted. |

**License point:** [GitHub's official license guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) says absent a license default copyright applies. Private ownership of SmartPloy **does not confer permissions over third-party copyrighted repositories**. Every imported file needs version pin, attribution, dependency license inventory, publisher-source rights and tested purpose.

## 4. YouTube and TikTok evidence — video claim versus actual repo

Discovery did not stop at keyword searches: accessible titles, descriptions and explicit GitHub links were inspected where retrievable. **Video playback, complete transcripts and performance claims were not independently reproduced.** TikTok sometimes blocks direct extraction; search-result snippets are not elevated to code proof.

| Media source | What it discusses | Followed to / outcome |
|---|---|---|
| [TikTok Ty AI — five job-search repositories](https://www.tiktok.com/@ty.prompts.ai/photo/7674326127220968718) | Explicitly names `career-ops`, `reactive-resume`, `AIHawk`, `interviewstreet/hiring-agent`, `ResumeSkills`. | Actual GitHub repos and license categories inspected; strongest discovery link to career-ops. |
| [TikTok Sabrina Ramonov — seven OSS AI agents](https://www.tiktok.com/@sabrina_ramonov/video/7479601981120728366) | Search excerpt explicitly identifies AIHawk as auto-apply bot. | Video page sometimes blocks content; GitHub family licenses vary. Don't use social claim as commercial grant. |
| [TikTok github.awesome — job search story](https://www.tiktok.com/@github.awesome/video/7625435150624509198) | Search excerpt claims high application volume and source scans. | Full TikTok content blocked by site; no uniquely authenticated repo relationship. **Unverified reference only.** |
| [YouTube: How to Automate Job Applications with AI Hawk](https://www.youtube.com/watch?v=gdW9wogHEUM) | 2024 tutorial explicitly says AI Hawk LinkedIn auto apply, mentions feder-cr GitHub fork. | AIHawk family inspected. License/version and LinkedIn ToS mean **no direct copy** by default. |
| [YouTube: Browser Agent Automates Anything (n8n + Skyvern)](https://www.youtube.com/watch?v=FhDYo2VKu5E) | Uses n8n + Skyvern and mentions job application. | [Skyvern AGPL](https://github.com/Skyvern-AI/skyvern) + [n8n Sustainable Use](https://github.com/n8n-io/n8n) researched; no free proprietary embed. |
| [YouTube: How to create Browser AI Agent with Browser Use/Playwright](https://www.youtube.com/watch?v=AK9mRsXdr4w) | Browser Use and Playwright runtime setup. | [Browser Use MIT](https://github.com/browser-use/browser-use), alternative to duplicating existing ObumAI browser. |
| [YouTube: How I Automated My LinkedIn Job Hunt with BrowserUse](https://www.youtube.com/watch?v=dmMMsq8Sp8s) | Browser-use demo for job hunting. | Browser Use source is permissive; automated LinkedIn access is not necessarily permitted by LinkedIn. |
| [YouTube: I Built an AI System That Automates My Job Applications](https://www.youtube.com/watch?v=lq8OaM-SeJo) | n8n workflow demonstration; description markets downloadable template. | Template license and concrete code not independently verified; **no copying from video/template**. |
| [YouTube: Automate Your Job Search Using AI](https://www.youtube.com/watch?v=LIzZRgfW4ok) | Indeed/LinkedIn/ZipRecruiter search workflow. | No verified repository rights; cannot assume any site allows automated access. |
| [YouTube: AI Job Application Bot / 100 applications](https://www.youtube.com/watch?v=UNa0t3ziwFw) | Hyperbrowser cloud automation and linked GitHub project. | Traced to [EricTechPro/ai-job-automation](https://github.com/EricTechPro/ai-job-automation); **no LICENSE**, not a copy candidate. CAPTCHA bypass claims explicitly rejected. |
| [YouTube: watch me apply to 1000+ jobs in minutes](https://www.youtube.com/watch?v=ntSbFUQZHJ0) | High-volume application marketing claim. | No independently proved employer receipts or fully identified licensed source; not counted as demonstrated capability. |

**Do not equate "1000 applied" video titles with employer acceptance**, or assume an open-source demonstration author permits commercial embedding of downloadable templates.

## 5. Fitness-gap analysis — SmartPloy versus advertised "full automation"

| Product requirement | Proven source-level foundations | Missing operational proof / implementation |
|---|---|---|
| Personalize once and edit settings | SmartPloy React/API/DB; ObumAI facts/profile | Live two-account acceptance and OIDC-onboarding user UX |
| 5 job platform families in Finland | SmartPloy direct Lever/SmartRecruiters and gated Kuntarekry/KIPA adapters; career-ops other provider code | Live lawful sources/credentials for LinkedIn/Duunitori/cities; actual refresh beyond historical 5 employer-specific feeds |
| Review CV/letter/answers per role | SmartPloy document editor and ObumAI application modules | Live publisher/AI consent + quality/locale acceptance; ensure no fabricated evidence |
| Run browser in persistent authenticated session | ObumAI Playwright; optional Browser Use/Stagehand | Isolated multi-tenant hosted browser + user auth boundary, session expiry and cancellation |
| Fill dynamic employer fields | SmartPloy Lever extension; ObumAI field parser; several permissive candidates | Greenhouse/Ashby and multistep/custom portal integration regression; real DOM changes |
| Upload documents automatically | ObumAI staged upload plan; supported Playwright patterns in candidates | **No proven SmartPloy employer transfer** with document identity and explicit external-transfer authority |
| Programmatically send permitted application | SmartPloy one-off user-confirmed Lever click + receipt observation; strict ObumAI decision code | **No unattended per-tenant consent / source-permitted executor**; no independently verified employer receipt |
| Prevent duplicate/rate-limit submissions | SmartPloy CRM/one-attempt browser SHA; Yaima skip ledger | Cross-worker atomic reservation, multi-ATS idempotency, post-crash uncertain-outcome reconciliation |
| Applications dashboard and notifications | SmartPloy CRM; Vakevahti outbox/leases | Real email/provider receipt verification, follow-up notifications, user-visible exception queue |
| Continuous production-quality service | SmartPloy tests, GitHub CI, ObumDelivery CI source plans | Actual isolated Woodpecker SmartPloy run, approved source deployment, production browser acceptance |

**No code can be marked "complete" merely because the repository has a README, passing fixture tests, a draft PR or a social media demo.**

## 6. Exact security/licensing test required before any code import

For each specific selected upstream module, record:

- Repository canonical URL, owner, **commit SHA**, file path/blob SHA, release date and license at this revision. Check per-directory license, NOTICE, vendored files, assets/fonts and dependency SBOM; commercial/legal sign-off if uncertain.
- Source scanning: malware/backdoors, shell/subprocess, hidden telemetry, remote JS, browser extensions' host permissions, accidental token/PII logging, arbitrary network egress, screenshots/DOM retention, prompt injection and unsafe fetch/redirect/SSRF. Reuse only least-privileged methods.
- For browser/runtime: deterministic known-host navigation, exact role/application URL binding, consent and page-context before every action, no browser-profile reuse across tenant accounts, document digest, no unattended 2FA/CAPTCHA/EEO/legal attestations, no anti-bot evasion.
- For data: encryption/access control, immutable attempt identity, source-rights ledger, CV and questionnaire erasure and disclosure, outside-model transfer opt-in, actual employer receipt capture and classification.
- Positive and negative tests: blocked source, revoked/expired consent, wrong account, switched job, unsupported document, missing field, changed SPA DOM, CAPTCHA, rate ceiling, duplicated click, worker crash after click, phony receipt, locale mismatch, stale source.
- Acceptance thresholds are **zero unauthorized submissions, zero cross-account leakage, zero invented applicant claims, zero duplicate automatic retries, and zero unlicensed code inclusion**. Demonstrate one full permitted source-to-employer-receipt pilot before scaling up.

**Prioritized first review order:** SmartPloy own modules + existing ObumAI contract; career-ops per-provider slice; neonwatty answer-memory; Yaima exceptions; ApplyAI selectors; Resume Matcher ATS parse; then choose Browser Use *or* Stagehand only if baseline Playwright fails. Reactive Resume and AutoApply are conditional: import less, not more.

## 7. Development-time estimate and caveats

| Scope | From-scratch missing-work estimate | Reuse-first estimate | Estimated relative throughput |
|---|---:|---:|---:|
| First complete **human-final** authorized application with files/answers/receipt | 6–10 engineer-weeks | 2–4 | **~2–3×** |
| First controlled, authorized standing-approval provider | 10–16 engineer-weeks | 5–8 | **~2×** |
| Multi-ATS + queue + real signed-in acceptance and production | 20–32 engineer-weeks | 12–18 | **~1.5–2×** |

Estimates are planning ranges for one engineer-equivalent with tooling and representative safe test access, **not calendar commitments or verified speedups**. Reuse savings reduce feature construction, not unavoidable privacy/ToS, user approval, third-party access and real acceptance. If integration overhead exceeds half of expected implementation saving, reconsider full dependency import and prefer a small adapter.

## 8. Required immediate next decision — stop before building

**Current audit result:** prebuilt code and legal permissions identified; NO third-party code copied, no merge to `main`, no OVH deployment, no actual employer submission.

Once the owner approves this plan:
1. Pin source modules and sign the 8 initial REUSE-CHECK entries; reject sources violating licensing/rights even if their demos look impressive.
2. Propose tiny source-review-only adaptations for *permitted* first ATS (Lever), then real tests and independent review; do **not** rewrite existing CV, matcher, browser-session, job, queue or tracker code.
3. Finish uploads + conditional answers + employer receipt first. Add additional permitted ATS and standing-approval automation only after measured end-to-end success.
4. Track actual speed saving and regression data in the [project plan](PROJECT_PLAN.md) and [master tracker](https://github.com/galapoto/smartploy/issues/88).

**User acceptance of this plan is the next action.** No runtime implementation is performed by this audit.

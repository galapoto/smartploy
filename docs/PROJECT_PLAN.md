# SmartPloy — Master Product Plan (reuse-first AutoApply)

**Status:** PROPOSED PLAN FOR OWNER REVIEW — **NOT** an implementation order, release approval, employer application authorization, or claim of live deployment.  
**Audit date:** 2026-10-18 (Europe/Helsinki).  
**Project:** `galapoto/smartploy`; ObumAI-powered independent Finland-first job intelligence and application product.  
**Existing operational ledger:** [SmartPloy issue #88](https://github.com/galapoto/smartploy/issues/88). The ledger remains the record of what actually shipped; this file is the forward project plan.  
**Detailed evidence, repository inventory, video/TikTok references and license matrix:** [REUSE_FIRST_AUDIT_2026-10-18.md](REUSE_FIRST_AUDIT_2026-10-18.md).  
**Expanded six-project license/safety audit and no-rewrite contract:** Sections 11–18 below. The original 22-family snapshot is historical; the expanded external discovery count is 28, with no newly imported libraries.  
**Source snapshot when this plan was written:** `main@d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1`; substantial product work remains in [draft integrated PR #149](https://github.com/galapoto/smartploy/pull/149) at `ca56d17a06741f5d8f61b7370391abed1373cba9`. The last historical owner-attested OVH release was `fc94e78e779650e781277ee1056ec92cd26a6e98` on 2026-10-12; **this audit did not reverify the running server**.

## Progress checkpoint — SP13 (18 October 2026)

- **Owner instruction:** Implementation has begun on the approved reuse-first plan, but branch and CI evidence remain separate from deployment.
- **First delivery candidate:** [SP13 PDF-attachment PR #151](https://github.com/galapoto/smartploy/pull/151) builds *on* SmartPloy's existing Lever companion and ObumAI application/preflight contracts; it does not create a second browser/login/CV generator.
- **Reused code:** SmartPloy existing 15-minute packet, application document renderer, reviewed CV text, one-attempt reservation, CRM receipt state and isolated test suite; existing ObumAI design and pinned MIT third-party source used for gap/behavior research, not wholesale vendoring.
- **Implemented in review code:** user-confirmed PDF selection, SHA-256-bound deterministic SmartPloy PDF output and new v2 packet, exact-form browser attachment, negative-case Node/Python/browser tests and source-pinned CI steps.
- **Safety status:** no external third-party source imported; no real employer site visited or submission made; no unattended application authority; browser assignment alone is not independently verified employer acceptance.
- **Release status:** PR #151 is DRAFT and stacked on draft [#149](https://github.com/galapoto/smartploy/pull/149). CI must pass for the *final exact SHA* and independent review is still needed. Main/OVH remain unchanged.
- **Next reuse investigation:** supported conditional Lever questions and answer provenance, then Greenhouse/Ashby provider-specific fixtures, durable queue and standing approval only where rights and user authority permit. Reinspect existing ObumAI forms/questionnaire, permitted MIT Yaima/neonwatty/career-ops modules **before writing new logic**.

## 1. Product outcome — actual applications, not just CI

SmartPloy must let a user create a truthful reusable applicant profile, search suitable jobs or choose general search, rank and deduplicate opportunities, prepare tailored CV/letter/answers, complete supported employer forms and permitted document transfers, and track each outcome with source-backed evidence.

**Two clearly distinct user-selectable modes:**

1. **Review-before-submit:** Discovery, preparation, form filling and permitted attachments are automated; the applicant reviews the full packet and executes/authorizes the final action on a supported provider.
2. **Standing-approval automation:** The applicant opts in per profile, employer/application channel, authorized source, allowed answer types, daily/company limits and expiry. Only a documented, permitted application flow may submit on that standing authority. Default **OFF**; stop for login/MFA/CAPTCHA, unknown or legally sensitive question, document mismatch, terms issue, consent uncertainty, blocked provider or ambiguous submission. Revocation cancels future queued sends. This is a future gated capability, not a currently operational feature.

**North-star verified result:** an authorized application has an employer-generated receipt/reference (or separately corroborated confirmation), attached to the correct user's profile and job without duplicate submission. A browser click or generated draft is **not** a verified application.

### Scope and non-goals

Finland-first; Finnish and English at minimum with appropriately reviewed Swedish UI/field variants; current, attributed, authorized jobs; account-scoped CV and profile; local-first ObumAI/Ollama when appropriate. Never invent qualifications, years, visas, salary, EEO answers or employer confirmations. Never bypass login, CAPTCHA, anti-bot restrictions, platform terms, authentication or geographic access controls. LinkedIn, Duunitori and other restricted platforms remain manual/share/authorized-API paths unless rights are established.

## 2. Mandatory reuse-first engineering rule (RF-001)

**Before any new feature or rewriting existing code, the implementing agent MUST:**

1. Search **SmartPloy main, the exact integrated review branch and relevant unmerged drafts**, plus **ObumAI runtime's existing 24 application modules and 17 browser modules** and the relevant ObumAI agent's draft source—not README alone.
2. Search the relevant related owner's repositories (source registry below), plus the vetted public candidates, their current code **and the exact version/commit**. Look at interfaces, real implementation, tests, security policy and supported platform versions.
3. Record a `REUSE-CHECK` entry with: capability, source repository and pinned commit/blob, existing filename/function/API, difference from SmartPloy requirements, exact SPDX/license text and third-party attributions, platform rights, network/data egress, tests, known defects, decision and reviewer.
4. Prefer, in this order: **existing SmartPloy service/function → versioned ObumAI API/capability (no DB or auth boundary collapse) → vetted permissively licensed library or narrowly copied module with notices → small adapter/augmentation → independently implemented new code only when the preceding alternatives are unsuitable.**
5. Reject all direct copies where copyright/license is missing, ambiguous, contradicts commercial use, or requires unapproved source-disclosure obligations. **Changing or rewriting restrictive licensed code does not erase its license.** Study published requirements and independently implement using independently documented interface behavior or seek permission.
6. Decide whether reuse saves **net** time after maintenance, integration and security costs. Do not import three competing browser stacks or duplicate the existing profile/ATS/workflow database.
7. No merge, deployment, personal-data processing, employer visit requiring authentication, or application submit until the relevant separate gates pass. Audit and documentation updates do not authorize building or sending.

**Code-review rejection condition:** any new parser, scheduler, browser executor, resume builder, form mapper, upload engine, receipt tracker or rights checker lacking its REUSE-CHECK proof is not ready for review. Add this gate to future agent instructions and CI after the owner accepts the plan.

## 3. Audited source scope and reusable inventory

Repository discovery on 2026-10-18: **44 owned/connected GitHub repositories** (`obumai` 11, `galapoto` 21, `Nordvantage` 5, `komplyint` 7) and **22 distinct external candidate repository families** (including one AIHawk fork family). These are **catalog-level counts**, NOT 66 complete code/security audits or 66 deployable modules.

**15 pre-existing subsystem families** were found, mostly as partial or review-only code. Avoid counting the same subsystem in multiple repositories as independent deliverables.

| Subsystem | Existing source to reuse or assess | Deficit to close |
|---|---|---|
| RF-S01 Source adapters and board discovery | SmartPloy `smartploy/sources/`; MIT career-ops `providers/`; conditional JobSpy | Finland authorization, KIPA credentials, employer-specific source policy |
| RF-S02 Canonical job identity, freshness, dedup | SmartPloy source/domain/polling; career-ops | Multi-ATS provenance; live feed freshness and no lost jobs |
| RF-S03 Owner-scoped verified profile/facts | SmartPloy workspace; ObumAI `application/evidence_vault.py`; Knowledge drafts | Strict stable user/profile binding, erasure and approved-vs-inferred facts |
| RF-S04 Matching, hard filters and suitability | SmartPloy scoring; career-ops; optional Hiring Agent | Human-labeled Finnish accuracy/false-negative validation |
| RF-S05 Tailored CV, cover letter and motivation | SmartPloy drafts; ObumAI `cv_tailor.py`, `cover_letter.py`, `questionnaire.py` | Fact grounding, bilingual acceptance, real document quality |
| RF-S06 Answer memory and custom questions | ObumAI `form_mapper.py`, `questionnaire.py`; MIT neonwatty answer-memory | Per-field confidence, provenance, protected answers, withdrawal |
| RF-S07 PDF/DOCX rendering and versioned files | SmartPloy private documents; ObumStudio PDF/DOCX draft; MIT Reactive Resume | Stable file identity, printable ATS-friendly document, upload ready |
| RF-S08 ATS PDF parseability/checks | Apache-2.0 Resume Matcher | Synthetic and actual parser validation, reject misleading score as eligibility |
| RF-S09 Persistent browser sessions and navigation | ObumAI `browser/live_session.py` + Playwright; MIT Browser Use **or** Stagehand | Reliable account isolation and tenant-scoped browser lifecycle |
| RF-S10 ATS DOM field extraction and filling | SmartPloy Lever companion; career-ops; MIT ApplyAI, Yaima | Greenhouse, Ashby, Workable/custom variants; dynamic questions |
| RF-S11 File selection, upload and evidence | ObumAI `browser/upload_plan.py` (staging **only**); candidate ATS appliers | **Actual safe browser attachment** + digest and document-kind verification |
| RF-S12 Durable queue, leases, retries, limits | SmartPloy worker/CRM; `galapoto/vakevahti` outbox/leases; Yaima tracker | Queue once-only reservation across crashes and multi-user action limits |
| RF-S13 Final-action authority and duplicate denial | ObumAI `application/final_submit_preflight.py`; SmartPloy browser companion | Scope-limited standing approval and supported provider-specific submit |
| RF-S14 Receipt, exception, follow-up tracking | SmartPloy CRM/receipts; Yaima `agent/tracker.py`; career-ops | Employer-origin verification, ambiguous/captcha/closed queue |
| RF-S15 Safe observation, testing, delivery | ObumBrowse candidate; ObumBench eval drafts; ObumDelivery | Real integrated CI, source-pinned acceptance and trusted OVH promotion |

**Internal reuse decision:** SmartPloy retains *ownership of jobs, accounts, source rights and submission records*. ObumAI remains a versioned bounded reasoning/execution service; **do not copy private application databases or import ObumAI runtime code directly into production SmartPloy** just to remove an API call. Incorporate self-owned library code only with repository/owner rights and independent security review.

## 4. External shortlist: adapt, evaluate, or exclude

All external candidates are **unintegrated**. MIT/Apache projects permit copying **with license, copyright and NOTICE compliance**, but do not imply safe code, permission to access an employer's website, or permission to forward CVs to a third-party LLM.

| Priority | Repository | Found license | Proposed treatment |
|---|---|---|---|
| P0 | [career-ops](https://github.com/career-ops-hq/career-ops) | MIT | Inspect and selectively adapt approved public ATS providers, resume/provenance and Ashby/Greenhouse/Lever/Workable field logic; **never infer submission authority** |
| P0 | [neonwatty/job-apply-plugin](https://github.com/neonwatty/job-apply-plugin) | MIT | Adapt answer provenance, sensitive-state and sanitized synthetic replay contracts |
| P0 | [Yaima/agent-apply](https://github.com/Yaima/agent-apply) | MIT | Adapt liveness, Exceptions queue, job-specific field mapping and one-time human-authorized acceptance workflow |
| P0 | [muhammad-saadd/applyai](https://github.com/muhammad-saadd/applyai) | MIT | Inspect narrow per-ATS Chrome field detectors; remove/replace direct OpenAI calls and broad host permissions before candidate acceptance |
| P0 | [srbhr/Resume-Matcher](https://github.com/srbhr/Resume-Matcher) | Apache-2.0 | Adapt ATS parseability checks and fact-preserving document-quality gates, with Apache notices |
| P1 | [reactive-resume/reactive-resume](https://github.com/reactive-resume/reactive-resume) | MIT | Prefer isolated renderer/export integration or selected templates; not wholesale 2,000-file app import |
| P1 | [browser-use/browser-use](https://github.com/browser-use/browser-use) **or** [Stagehand](https://github.com/browserbase/stagehand) | MIT | Benchmark against existing ObumAI Playwright; choose at most ONE missing browser runtime component |
| P1 | [AbhishekMandapmalvi/AutoApply](https://github.com/AbhishekMandapmalvi/AutoApply) | MIT | Inspect Greenhouse/Lever/Ashby/Workday upload and form variants only; avoid unauthorized LinkedIn/Indeed automation |
| P1 | [speedyapply/JobSpy](https://github.com/speedyapply/JobSpy) | MIT | Consider only approved feeds/platform adapters after source terms and endpoint verification |
| P2 | [Hiring Agent](https://github.com/interviewstreet/hiring-agent), [ResumeSkills](https://github.com/Paramchoudhary/ResumeSkills) | MIT | Optional evaluation, prompt and checklist reuse; avoid replacing SmartPloy's existing scorer |
| Research only | [dyyfk/auto-apply](https://github.com/dyyfk/auto-apply), [dabloo26/job-application-agent](https://github.com/dabloo26/job-application-agent), [tmason10/job-application-automation](https://github.com/tmason10/job-application-automation), [EricTechPro/ai-job-automation](https://github.com/EricTechPro/ai-job-automation) | **No license found** | **NO COPYING or derivative edits**; only independently implemented publicly described concepts; EricTech video suggests CAPTCHA bypass—explicitly not a SmartPloy feature |
| License/legal hold | [AIHawk fork family](https://github.com/Karinza38/Auto_Jobs_Applier_AIHawk), [Skyvern](https://github.com/Skyvern-AI/skyvern), [n8n](https://github.com/n8n-io/n8n), [EasyApplyBot](https://github.com/madingess/EasyApplyBot) | AGPL, GPL, Commons Clause/custom source-use terms | **NO COPYING pending project-specific licensing strategy or permission** |
| Source terms hold | [GodsScion LinkedIn applier](https://github.com/GodsScion/Auto_job_applier_linkedIn) and comparable bots | MIT implementation, prohibited platform action | May inspect generic test patterns but **do not automate LinkedIn**; copyright permission never overrides website terms |

See the linked audit for the remaining individual candidate classifications, YouTube/TikTok research, exact issues and observed caveats.

## 5. Source policy and legal gate (RF-LEGAL)

Two **independent** permissions are required for every proposed integration:

- **Source-code rights:** license at pinned commit; file-scoped licenses; transitive dependency obligations; provenance/copyright/attribution and trademark status. Where unclear, **HOLD** and obtain legal/owner permission. No unlicensed or Commons Clause code is reclassified by paraphrasing, editing or changing its name.
- **Employer/platform rights:** documented ATS API, publisher agreement, user authorization, provider restrictions and rate ceilings; no bypass, scraping unauthorized sites, CAPTCHA solving, stealth evasion, credential collection or hidden bulk submissions.

License examples:
- **MIT** — generally allows commercial use and modification, retaining copyright/license.
- **Apache-2.0** — commercial use with license, NOTICE/attribution, changes and patent conditions.
- **AGPL-3.0 / GPL-3.0** — copyleft/source-sharing conditions may make embedding unacceptable for the planned closed-source SaaS; legal clearance and architectural boundary first.
- **n8n Sustainable Use / AIHawk Commons Clause / proprietary** — not a generic permissive commercial embedding license.
- **No license** — **all rights reserved by default; do not copy code**. Researching broad functionality is not permission to adapt its implementation.

Use [GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) and read the project's actual LICENSE; a GitHub SPDX field alone is not a full legal review. For job boards, keep [LinkedIn's prohibited software guidance](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software) and the [Finnish source-strategy contract](SOURCE_STRATEGY.md) in force.

## 6. Minimal product architecture; integrate not replicate

```text
SmartPloy signed-in user + source-rights registry
  -> Finnish/ATS discovery (existing SmartPloy; selected approved career-ops adapters)
  -> canonical ranked job queue + per-account application policy
  -> approved evidence and document set (SmartPloy owner-scoped records)
  -> ObumAI versioned proposal API (fact-grounded CV/cover letter/answers)
  -> selected existing document renderer + ATS parseability check
  -> one isolated browser runtime (existing ObumAI Playwright unless gap proven)
  -> ATS-specific DOM mapping + safe document upload + dynamic field verification
  -> consequential-action consent/standing-approval authority, provider-rights gate
  -> one-shot submit or manual handoff, with ambiguous outcome never auto-retried
  -> employer evidence/exception queue, SmartPloy status and notifications
```

**Exactly one canonical source of truth** for each application attempt, profile, job and permission. Runtime integrations use typed, versioned contracts, not direct cross-product DB access or unmanaged plugins. Existing SmartPloy/ObumAI solutions are the baseline; foreign libraries fill *demonstrated gaps*. Local Ollama default; no CV, answers, cookie, token or employer posting forwarded to an outside AI processor without recorded, revocable, per-purpose permission and publisher rights.

## 7. Fast build order and acceptance gates

No work below begins because a project appears on a shortlist; begin only after this reuse plan is reviewed/accepted.

### Phase A — Proven single-provider completion (highest priority)

**A1. Reuse validation and license/cyber gate:** Pin source and license of 2–3 selected code slices; run dependency/license, secret/egress, SSRF, browser permission and malicious DOM/prompt-injection checks. Generate a decision receipt **REUSE-CHECK**. Independent reviewer signs the boundary.

**A2. Lever end-to-end dry-run:** Use the current SmartPloy companion, ObumAI form/application modules and permitted candidate adapters; review prior identity. In synthetic Chromium fixture and approved staging, prove file upload, extra questions, field selections, required-field validation, one-attempt reservation, consent-denial and receipt-state truth. No real employer submission without applicant authority.

**A3. First genuine application acceptance:** One legitimate owner-authorized job where the operator intends to apply, with rights verified, no test spam, complete document packet, explicit final approval, employer receipt captured and same-account tracking. It must not be reported as passed from a screenshot of a button click.

### Phase B — Turn completion into a resilient workflow

**B1. Durable controlled queue:** Background discovery/preparation, filtering, limits and duplicates; independent worker handles only explicitly authorized user/job profile, policies checked again before each action and retry. Unknown state = manual reconciliation, not resubmission.

**B2. Assisted multi-provider:** Greenhouse, then Ashby/Workable/SmartRecruiters through documented permitted forms; provider-specific fixtures, form drift detection, safe DOM mapping, conditional questions, uploads and exception handling. Submit only where an authorization path exists, otherwise user-final-submit.

**B3. Standing-approval (unattended where allowed):** Per-user/per-provider opt-in, expiry and revocation, application caps, qualification hard exclusions, least-privileged browser, kill switch and browser credential isolation. Staged rollout with no unauthorized LinkedIn/Indeed automation.

### Phase C — Finland coverage and user-visible quality

**C1. Authorized Finnish feeds:** Job Market Finland KIPA when credentials/terms allow, Kuntarekry approved feeds, direct-employer ATS expansion, permitted manual/share intake for LinkedIn/Duunitori/city portals. No provider rights => no poll/submit.

**C2. Effective ranking:** Real two-rater consented FI/EN evaluation set, relevance and completeness metrics; no invented qualification scoring or claims. Incorporate Swedish where reviewed.

**C3. Signed-in production:** Obum Identity/OIDC and real two-account A1–A7, data isolation, source freshness, backups, rollback, accessible UI, live saved Settings and notification lifecycle. Release via source-pinned CI/ObumDelivery as independent parallel lane; **do not wait for CI platform redesign before feature coding/testing**.

## 8. Mandatory safety, security and completeness checks

An external module fails qualification until all applicable negative and positive tests cover:

1. **Supply chain:** pinned immutable source and license, repository owner/provenance, SBOM/transitive licenses, reproducible build, secret/telemetry/network audit and CV/malware input handling.
2. **Account privacy:** stable user ID, profile ID, tenant-scoped browser context/queue/storage, same-email distinct users, logout/account switch, encrypted secrets, erasure/retention and no cross-account cached data.
3. **Truthful answers:** no fabricated experience/certification/work permit/EEO/salary; unknown fields pause, job change invalidates prepared package, explicit approved facts and citations.
4. **Dynamic forms:** visible/current DOM only; required/conditional fields, React/select re-render, multi-step flows, document-kind and digest, supported locales; injection/iframe/redirect attack simulations.
5. **Consent and source rights:** user per-mode/per-channel grant; employer terms per board; independent AI forwarding consent; no CAPTCHA/MFA bypass; cloud LLM off without specific authorization.
6. **Submission:** one exact job/profile/document fingerprint, atomic pre-send reservation, bounded rate/duplicate caps, no automatic retry after uncertain click, per-provider approval and kill switch.
7. **Receipts:** employer-confirmed vs browser-observed vs attempted/unverified vs blocked distinguished; correct user/source/job identity, human exceptions and immutable evidence hashes.
8. **E2E:** synthetic success/failure fixtures **and** user-authorized real account/real job verification; no green test suite alone establishes production or employer acceptance.

## 9. Count and development acceleration hypothesis

- **44** related internal repositories inventoried at metadata/name level; high-interest code read from SmartPloy/ObumAI plus selected agent drafts, Proctor, Vakevahti and Nordvantage auth. Drafts and offline packages are **not** assumed to be merged or running.
- **22** external candidate codebase families evaluated by live repository metadata, README/file layout or license; more detailed code inspection is **pending** for each actual slice selected to import.
- **15** subsystem categories with pre-existing candidate implementations. **None** is yet a newly integrated/released third-party SmartPloy capability.
- **8 priority external repositories** for first implementation review: career-ops, neonwatty job-apply-plugin, Yaima agent-apply, ApplyAI, Resume Matcher, Reactive Resume, Browser Use **or** Stagehand, and Abhishek AutoApply. Alternative browser engines count as **one selected role**, not two production dependencies.
- **Forecast, not performance evidence:** a first complete permitted assisted application flow might require **6–10 engineer-weeks custom** vs **2–4 engineer-weeks with genuinely reusable slices** (~**2–3×**, 2.5–3× midrange). The first provider-specific authorized standing-approval flow: **10–16 vs 5–8 engineer-weeks** (~2×). Broader multi-ATS service: **20–32 vs 12–18 engineer-weeks** (~1.5–2×). These assume one experienced developer equivalent, working CI, accessible permitted employer test fixtures and positive security reviews; elapsed calendar time, licensing and external accounts are not guaranteed.
- Measure actual cycle time per approved application milestone, reuse percentage, failed integrations, regressions and employer-confirmed outcomes. If an imported dependency needs a major rewrite or violates source policy, the claimed speedup is reset and a simpler local implementation evaluated.

## 10. Delivery governance, dependencies and "before build" checkpoint

**This plan is the deliverable for the current audit, NOT a permission to begin incorporation.** Reviewer should approve/change the initial 8 candidate choices and the permission-first scope. Then:

1. Create per-feature `REUSE-CHECK` with pinned eligible source and complete audit; ensure no copyrighted unlicensed code was ported.
2. Build from the *existing* SmartPloy application and ObumAI runtime foundations. Maintain native SmartPloy tenant boundary and migrate only intentional functionality.
3. Keep real production, GitHub main and employer systems unchanged until reviewed CI, owner consent, backup/rollback and signed-in acceptance.
4. Update this plan and [master tracker #88](https://github.com/galapoto/smartploy/issues/88) after every measured actual integration; distinguish source-built, CI-tested, ObumDelivery-tested, deployed, browser-verified and employer-confirmed.
5. Every implementation PR must document which upstream system avoided rewriting, the reuse license/copyright notices, security findings, coverage improvements and engineer-time actually saved.

**As of 2026-10-18:** No external code has been imported, no real application has been sent, and this plan creates no release or employer action authority.


---

## 11. Expanded reuse-first research and exact-source findings (18 October 2026)

**Research instruction:** Preserve existing implementations. Inspect original SmartPloy branches, ObumAI agents, other owned repositories, and qualified public code before authoring replacement functionality. Adapt a small licensed, safe and COMPLETE source slice; extend proven gaps only. This section extends the preceding 22-family census; it is a documentation-only assessment, not permission to operate a real employer application or release to production.

**Reconciled discovery:** 44 internal owned/connected repositories (11 ObumAI, 21 galapoto, 5 Nordvantage, 7 komplyint); 22 original external families plus **six distinct newly identified candidates = 28 external families** at repository/discovery level; **15 existing reusable subsystem families**. Of 28, 19 have MIT/Apache repository-level license declarations and nine are unlicensed, restrictive, platform-conflicted or otherwise unsuitable for direct proprietary reuse under the current plan. **Nineteen is NOT nineteen approved imports**: per-file licensing, dependencies, software security and employer-site authorization remain separate. Many of the 44 repositories have only a charter or unmerged draft.

**Source status checkpoint:** SmartPloy main [d0ebe59](https://github.com/galapoto/smartploy/commit/d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1); complete integrated product [draft PR #149](https://github.com/galapoto/smartploy/pull/149) reviewed at ca56d17a06741f5d8f61b7370391abed1373cba9; ObumAI obumellm [main a324fc0](https://github.com/obumai/obumellm/commit/a324fc0f330aeffe869dea7f96243156bc6af669). Counted 24 Python files in ObumAI application/ and 17 in browser/, including package __init__ files, NOT 41 independent deployable services. Source exists; production browser capability and real employer receipts do not follow from file counts. Do not confuse the SmartPloy draft and OVH running release.

**New parallel development warning:** [SmartPloy DRAFT PR #151](https://github.com/galapoto/smartploy/pull/151) appeared during the audit, stacked on #149, claiming a reviewed Lever PDF attachment with a specific first-party REUSE-CHECK. Treat it as pre-existing in-progress work: inspect its current HEAD, source digests, security and actual tests before writing another upload subsystem. It is **not merged**, its exact head may move, and synthetic assignment of a file input is not a real employer-accepted attachment. This audit neither touches PR #151 nor authorizes release.

## 12. No-rewrite-without-search contract: RF-001A

Every developer, ObumAI specialist agent, and external contributor must search these layers IN ORDER before opening any code PR:

1. **Original SmartPloy:** current main, the newest reviewed integrated draft (#149 as of this snapshot), all relevant open feature PRs including #151, application/database/browser/worker source and existing tests.
2. **ObumAI source:** obumellm application and browser modules, ObumAI Core agent runtime; inspect related ObumBrowse, ObumConnect, ObumKnowledge, ObumStudio, ObumBench and ObumForge **draft source refs**, not only their almost-empty default branch. Prefer a typed, versioned ObumAI service interface to copying shared secret-bearing runtime modules or databases.
3. **Other owned repos:** Vakevahti outbox/leases, Proctor/Veriscope tenancy/attestations, Nordvantage authorization checks, Robot Framework/QA test patterns; reject copies that conflict with SmartPloy domain boundaries.
4. **External code:** this 28-family registry plus targeted GitHub/YouTube/TikTok discovery for the SAME capability; verify the exact repo, pin current commit and individual blob, read actual LICENSE/NOTICE and transitive terms, inspect data egress and write actions, and run relevant negative tests in isolation.
5. **Only after missing capabilities are proven:** document the smallest augmentation or independently authored function. No second database, browser engine, scheduler, CV generator, answer memory or ATS parser may be created merely for convenience.

**Required [REUSE-CHECK receipt template](REUSE_CHECK_TEMPLATE.md) before ANY implementation PR:** requirement ID; user-visible outcome; existing SmartPloy path/function and revision; matching ObumAI module/API and revision; searched internal and external refs; precise upstream commit, file/blob, LICENSE and copyright/NOTICE; dependency/SBOM evidence; website/publisher permission; applicant consent/data processing; existing tests and completeness gaps; planned bounded adapter; accepted/rejected reason; alternative; reviewer; time budget and measured savings after delivery. Missing receipt -> review BLOCKED. Do not treat AI-generated source, a GitHub README, a green synthetic test or a video view count as a substitute.

**Licensing boundary:** MIT and Apache-2.0 usually allow commercial adaptation with their notices and other terms respected. No LICENSE is all-rights-reserved by default. GPL/AGPL can have conditions incompatible with the intended distribution/network service; Commons Clause, fair-code and source-available licenses require their actual terms or written commercial permission. **Editing, translating, disguising or rewording code from an unlicensed or incompatible source DOES NOT make the resulting derivative free to use.** Independent implementation of generally described behavior, or rights-holder permission, is allowed; no protected code may be ported without authority. Software copyright licensing is separate from employer/LinkedIn/Indeed/board authorization.

## 13. Existing code coverage by subsystem: use it before any rewrite

| Existing subsystem | Canonical SmartPloy / ObumAI source | What is already real in tracked source | Must still be proved or augmented |
| --- | --- | --- | --- |
| RF-S01 Job discovery | SmartPloy smartploy/sources/public_ats.py, jobmarket_finland.py, kuntarekry.py | Read-only ATS/Finland source adapters, explicit tenant and rights controls | Authorized credentials/new board coverage; don't duplicate Lever/Greenhouse readers |
| RF-S02 Identity/freshness/dedup | SmartPloy domain.py, polling.py, source polling | Source and job identity normalization/refresh logic | Cross-provider dedup, actual freshness and missed-job fixtures |
| RF-S03 Candidate facts/owner data | SmartPloy profile.py, profile_storage.py, application_workspace.py; ObumAI application/evidence_vault.py | Stored profile and evidence-grounding models | Real separate-user browser acceptance, erasure/withdrawal and independent facts |
| RF-S04 Ranking/relevance | SmartPloy scoring.py, search_preferences.py; ObumAI job_fit.py | Local relevance/ranking foundations | Real human-rated Finnish/English precision, exclusions, fairness |
| RF-S05 CV/letter drafting | SmartPloy preparations.py, local_drafting.py, obumai.py; ObumAI cv_tailor.py, cover_letter.py | Evidence-bound draft generation and versioned ObumAI bridge | Approved facts, quality, Finnish grammar; never fabricate qualifications |
| RF-S06 Questions and memory | ObumAI questionnaire.py, form_mapper.py; SmartPloy preparation evidence | Question mapping/safe text-field policy | Tenant-scoped reusable answer provenance, unknown/sensitive question pause |
| RF-S07 Documents/rendering | SmartPloy private CV/documents; ObumAI documents.py; ObumStudio drafts | Document preparation/rendering candidates | Validated PDF/DOCX bytes/version, consent and employer-visible attachment |
| RF-S08 ATS document quality | Existing SmartPloy rendering + Apache-2.0 Resume Matcher | Scoring/parser candidates | Test parseability from actual final file; never claim algorithmic ATS score = job eligibility |
| RF-S09 Persistent browser | ObumAI browser/live_session.py, live.py; SmartPloy browser-companion | Playwright persistent supervised browser and local companion | Isolated per-account session, allowed-host session expiry, cancellation and safe cleanup |
| RF-S10 Field discovery/filling | ObumAI application/form_mapper.py, browser/live_fill.py; SmartPloy browser-companion/logic.mjs | Safe fields and exactly targeted applicant packet matching | Lever dynamic conditional fields, React rerenders, Greenhouse/Ashby/Workable fixture drift |
| RF-S11 Actual file upload | ObumAI browser/upload_plan.py; SmartPloy [draft PR #151](https://github.com/galapoto/smartploy/pull/151) | ObumAI only stages manual file; SmartPloy draft proposes explicit Lever PDF attachment | Exact uploaded byte/digest vs reviewed document; employer readback/confirmation, scanner, adverse files; no verified real upload |
| RF-S12 Durable queues/retries | SmartPloy worker_runtime.py, worker_schedule.py and storage; Vakevahti outbox/leases | Worker scheduling and durable-event design | Per-user exactly-once reservation, crash-after-click ambiguity, rate caps and kill switch |
| RF-S13 Submission authority | ObumAI final_submit_preflight.py; SmartPloy browser_handoff.py, existing consent and reservations | Deterministic **non-actuating** policy; current companion autoSubmitAllowed=false | Rights- and consent-bound final actuation on approved ATS only; no unattended submission until separately authorized |
| RF-S14 Employer receipts/CRM | SmartPloy browser_receipt.py, applications.py, CRM storage | Browser-observed evidence explicitly NON-authoritative | Employer-confirmed ID/email/API receipt, uncertain state reconciliation and no duplicate retry |
| RF-S15 Testing/release | ObumBench drafts, ObumDelivery, SmartPloy CI and controlled OVH scripts | Unit, synthetic browser, isolated-test tooling exists | True exact-head ObumDelivery SmartPloy acceptance, authorized two-user live E2E, backup, OVH deployed SHA/provenance |

**Critical path:** RF-S11 genuine permitted upload, RF-S10 conditional fields, RF-S13 final authorization/actuation, RF-S14 independently defensible receipt. Do not claim end-to-end auto-apply by completing only a browser form or handing back a draft.

## 14. Pinned external source shortlist, gap and risk decision

All revisions below were inspected through connected GitHub source metadata or named files on 18 October 2026. They are **review candidates**, not copied dependencies. If an upstream advances, a new check against that SHA is required.

| Role / candidate | Pinned default revision and inspected path | Current verified capability | Security/completeness finding and action |
| --- | --- | --- | --- |
| Public ATS discovery: [career-ops](https://github.com/career-ops-hq/career-ops) | MIT, 9e4326b35a8ee716081b9169f44e83d232a99289; providers/lever.mjs, greenhouse.mjs, ashby.mjs | Read-only public postings adapters with HTTPS/tenant checks | Lever/Greenhouse already in SmartPloy; evaluate **only missing permitted source behavior** (e.g. Ashby discovery), do NOT claim career-ops implements employer form submission |
| Answer rules: [job-apply-plugin](https://github.com/neonwatty/job-apply-plugin) | MIT, 370204c58b1137d08c5a7e7449538ae6447be0b9; scripts/job_apply_policy.py, job-apply-store.py | Local answer/policy ledger, revocation and uncertain/confirmed outcome rules | Policy file explicitly says inert/no browser activation. Adapt tenant/privacy tests after safe state/erasure review; not a submit engine |
| Assisted form flow: [Yaima agent-apply](https://github.com/Yaima/agent-apply) | MIT, e5061bc0455ea61b75b59edbe73296ab5bbe03ca; agent/forms/apply.py | Real Playwright form/navigation code and human review pause | No unattended path in inspected source; selectors, CAPTCHA stop, outcome verification need synthetic adversarial tests; narrow reusable form adapter only |
| Selectors: [ApplyAI](https://github.com/muhammad-saadd/applyai) | MIT, d4a97b5643aa219592883a43b068fc18dff94678; content_scripts/lever.js and utils/ai.js | ATS-specific DOM selectors | utils/ai.js transmits resume/job/answers to api.openai.com. **NO wholesale extension import**; local-only reviewed selectors with exact-host and no remote data egress |
| ATS checks: [Resume Matcher](https://github.com/srbhr/Resume-Matcher) | Apache-2.0, ff5b370372d39b6cb6b56fd0dad88a2fe5c3abce; apps/backend/app/services/ats.py, ats_parse/ | ATS-score/parse pipeline and selection logic | Evaluate actual final PDF extraction/structure only; never use a proprietary ATS percentage as proof of eligibility; retain Apache notices and isolate fonts/templates |
| Rendering: [Reactive Resume](https://github.com/reactive-resume/reactive-resume) | MIT, b242aadcf2d5f819090c7aae8006ca8a235035df; apps/ and packages/ | Resume editor/export, ATS-friendly document candidates | Large app duplicates SmartPloy profile; isolate individual renderer only if current export fails fixtures; separately inspect bundled fonts/assets |
| Browser option: [Browser Use](https://github.com/browser-use/browser-use) | MIT, aa093a843da5edbf323c0b4145c9b6a0db3ecde8; pyproject.toml | Browser agent with navigation abstraction | Dependency manifest includes PostHog, OpenAI and browser-use SDK. Audit telemetry/network/LLM defaults; compare against existing ObumAI Playwright FIRST |
| Browser alternative: [Stagehand](https://github.com/browserbase/stagehand) | MIT, 10418f98831285b3cddca5328c8013a94f22672a; package.json | TS browser act/extract routines | Alternative to Browser Use, not a second production engine. Evaluate exact use case and provider egress costs before choosing either |
| ATS apply patterns: [AutoApply](https://github.com/AbhishekMandapmalvi/AutoApply) | MIT declared, 053071ba1bba5733b522d78c3d645002d817e55a; bot/apply/lever.py | Targeted Lever upload/field logic; CAPTCHA detection | Extra README commercial/personal-use disclaimer needs rights review; LinkedIn/Indeed modules excluded; source may use unsafe or unverified submit heuristics |
| Job discovery: [JobSpy](https://github.com/speedyapply/JobSpy) | MIT at repository level; see [original audit](REUSE_FIRST_AUDIT_2026-10-18.md) | Board scraping interfaces | Software license NEVER authorizes scraping against site terms; only permitted endpoints and explicit policy |

### Six additional distinct external families found after original 22-family survey

| New repository | Pinned commit / license verified from LICENSE | What we might reuse | Why it is not a cleared import |
| --- | --- | --- | --- |
| [Application Autofill](https://github.com/AkoSuminoe/application-autofill) | cffd5e2615d682dda44e2b9aaec69a922af26f17 / MIT | Offline applicant answer bank, React-safe fills, synthetic Chrome fixture, sensitive review | Manifest includes optional host permission to https://*/*; narrow it to explicitly consented employer host. No file upload or final submit |
| [ai-job-pilot](https://github.com/summitsingh/ai-job-pilot) | f28fa845400f479c142e2ea0a02fd0293d4d16c8 / MIT | Deterministic schema/field mapping and final readback, possible reduction of per-field model calls | Source includes batch unattended lane and submit_only.py doing button.click then simple confirmation-text/URL matching. Do NOT reuse unattended submission or market its ~99% token savings without independent benchmark |
| [Safe Application Prefill](https://github.com/HimavanthMahesh/safe-application-prefill) | 1619963fa24506e91a3b0ce75067f82632e71b3d / MIT | Minimal local approval, blocked field/submit/consent test fixtures | Explicitly never uploads or submits; much of feature overlaps SmartPloy existing companion. Good candidate for negative tests, not second extension |
| [PaperPlane](https://github.com/Harsh-H-Shah/PaperPlane) | 8d2d82c32b187f2eb81c4dd5c15b1c3667d608e6 / MIT | Potential ATS flow fixtures and source discovery | Large FastAPI/Next/Playwright/Gemini stack duplicates ours; audit cloud resume data transfer, browser controls and actual source permissions before any code |
| [ApplicatorAI](https://github.com/subhashbs36/ApplicatorAI) | 98d6061de9d919e6d4124a8c0fadf67259052a4c / Apache-2.0 file | Optional cover-letter and application-review patterns | README MIT badge conflicts with actual Apache-2.0 LICENSE; source/file-level rights and assets review required. Duplicates SmartPloy/ObumAI writing |
| [Keel](https://github.com/KeelDev-tech/keel) | 78f1549fbecada07b331b4c05fde1bb099ff7b45 / Apache-2.0 | Potential trust/evidence/confirmation testing ideas | Very large, overlapping system, uncertain integration cost. Never replace current SmartPloy/ObumAI baseline wholesale |

**External triage result:** Original eight priority source-role slots remain valid, but promote the small **Application Autofill** and **ai-job-pilot deterministic mapper** to an additional P0 *comparison*, not an approved import. Prefer a handful of reviewed functions or fixtures over transplanting a framework. The other four newly found systems are P1/P2 optional; no new engine or stack is justified merely by their presence. All six have permissive top-level license texts, subject to file/asset/dependency terms. Do not merge counts of alternatives as if they were separate required modules.

## 15. Social-video-to-repository evidence trail

The extended discovery included the existing [YouTube/TikTok research register](REUSE_FIRST_AUDIT_2026-10-18.md) and independent GitHub code/license checks. Direct complete YouTube playback/transcripts were not obtainable in this pass; TikTok pages prevented direct extraction, so a title or snippet is **not verified implementation, source rights or employer acceptance**.

| Media lead | Repo actually traced or independent check | Decision |
| --- | --- | --- |
| [YouTube AIHawk tutorial](https://www.youtube.com/watch?v=gdW9wogHEUM) | AIHawk README links the same tutorial; [AIHawk fork family](https://github.com/Karinza38/Auto_Jobs_Applier_AIHawk) with differing AGPL/Commons-Clause variants | Research ideas ONLY, no copy pending commercial/license and LinkedIn rights |
| [YouTube n8n + Skyvern](https://www.youtube.com/watch?v=FhDYo2VKu5E) | [Skyvern](https://github.com/Skyvern-AI/skyvern) AGPL-3.0 and [n8n](https://github.com/n8n-io/n8n) source-available Sustainable Use | Orchestration reference only; neither is a free proprietary embed |
| [YouTube Browser Use/Playwright](https://www.youtube.com/watch?v=AK9mRsXdr4w) and [job hunt demo](https://www.youtube.com/watch?v=dmMMsq8Sp8s) | [Browser Use](https://github.com/browser-use/browser-use) MIT | Optional benchmark vs native ObumAI Playwright; demo is not licensed platform access |
| [YouTube high-volume demo](https://www.youtube.com/watch?v=UNa0t3ziwFw) | [EricTechPro job automation](https://github.com/EricTechPro/ai-job-automation), no LICENSE detected in earlier audit | NO COPY; reject CAPTCHA/anti-bot bypass claims and unsupported employer receipt claims |
| [TikTok Ty AI project list](https://www.tiktok.com/@ty.prompts.ai/photo/7674326127220968718) | Previously listed career-ops, Reactive Resume, AIHawk, Hiring Agent and ResumeSkills; actual GitHub repos inspected separately | Social association unverified by direct playback; repo, license and source decide reuse |
| [TikTok Sabrina Ramonov](https://www.tiktok.com/@sabrina_ramonov/video/7479601981120728366) | Search-level connection to AIHawk fork family | Research lead only; no independent transcript |
| [TikTok GitHub job-search post](https://www.tiktok.com/@github.awesome/video/7625435150624509198) | No authenticated unique repo/source pairing established | Not counted as implementation |
| [YouTube 1000+ job apply claim](https://www.youtube.com/watch?v=ntSbFUQZHJ0) | No independently verified accepted application receipt | Not evidence of performance or source ownership |

**Standing discovery rule:** Before rewriting each ATS or browser capability, search GitHub and recent YouTube/TikTok code demos again and trace a concrete original LICENSE + file-level implementation; do not adopt opaque downloads or executable scripts from social posts. Unknown provenance -> no copy.

## 16. Safety/completeness acceptance for any source we adapt

Classify each upstream component as: (1) source found; (2) license/attribution cleared; (3) security/egress cleared; (4) requirement complete in synthetic tests; (5) ObumDelivery exact-SHA verified; (6) production read-back verified; (7) authorized employer confirmation. A module cannot skip a level.

**Mandatory negative cases for initial Lever pilot and every new provider:**

- Unlicensed/forbidden board, stale or duplicate job, wrong active tab/origin, changed ATS hostname, hidden iframe/redirect, malicious webpage instructions -> **BLOCK**.
- Candidate account switch, other user's CV/cookie, revoked consent, missing/inaccurate fact, unapproved sponsorship/EEO/visa/legal text -> **BLOCK and request user decision**.
- Wrong/missing/malformed/malicious PDF, document MIME mismatch, reviewed-text-to-export SHA mismatch, file input cleared by React rerender -> do not claim attachment.
- CAPTCHA, OTP/MFA, closed post, anti-bot challenge, terms prohibition -> **manual stop**, never evade.
- Two workers racing, retry after a submit click without an employer-confirmed result, browser crash/network timeout at final send, fake thank-you text -> **uncertain**, never auto-resubmit.
- Browser-observed page/button click must remain **unverified**, distinct from employer-confirmed application identifier or independently trusted email/API receipt.
- No unauthorized network egress: local-first Ollama by default; foreign extension code sending CV to a cloud LLM without user purpose-bound consent is a **block**.
- Exact immutable upstream revisions, inherited notices, no bundled unlicensed fonts/templates/telemetry, SBOM and dependency scan, synthetic secrets and least-privileged extension permissions.

**Completeness criteria for first supported, authorized provider:** correct published job and user identity; approved truthful answers; exact versioned CV; actual permitted browser upload with retained file bytes; dynamic/conditional required fields checked after SPA changes; deliberate final approval; one-shot consent-locked send; verified employer receipt or truthful uncertain/manual state; safe cancellation/logout and no cross-account memory; Finnish/English test cases; exact-head CI and trusted deployment read-back. A draft upload fixture alone **fails** these criteria.

**Before copying any code:** do not adopt incomplete external submit paths and patch them into uncontrolled production. Take approved ATS-specific field detectors or tests, map them into SmartPloy's own consent/tenant authority, then independently add only missing functionality. If a project is unsafe, incomplete or incompatible, **REJECT** it even when MIT-licensed.

## 17. Recommended implementation sequence after reporting and approval

1. **P0 keep what already exists:** SmartPloy #149 source modules, SP13 [draft #151](https://github.com/galapoto/smartploy/pull/151), ObumAI form/packet/preflight, existing first-party browser companion. Do not create duplicate code. Audit #151 exact current HEAD, attachment semantics and document linkage before changing upload.
2. **P0 selected upstream REUSE-CHECK:** career-ops only where SmartPloy source coverage missing; Yaima form exception rules; neonwatty answer/provenance state; Application Autofill and ai-job-pilot deterministic field extraction compared against ObumAI form mapper; Resume Matcher targeted final-PDF parse test. Restrict ApplyAI to vetted local selectors. Pin copied file and preserve required MIT/Apache notices. Alternative browser engines deferred.
3. **P0 prove one controlled Lever fixture end to end:** documented rights + synthetic Chromium, final approved CV digest, user-approved transfer, dynamic required answers, safe attachment proof, submit disabled unless explicit final approval, authoritative receipt or explicit UNKNOWN; adverse multi-tenant/cancel/duplicate cases.
4. **P0 one authorized real applicant test:** Only at an employer where the owner actually intends to apply and automation is permitted. Human reviews and approves; record legitimate employer-confirmed status without sending test spam or exposing applicant data.
5. **P1 add permitted Greenhouse, Ashby and Workable adapters:** use prior safely licensed functions where they really beat current modules; if employer/ATS terms forbid automation, retain assisted fill and user-submits workflow.
6. **P1 standing-approval only after manual-flow acceptance:** per-user/per-provider/time-limited grant, caps and kill switch, durable leased queue, no ambiguous retry, per-site rights; feature default OFF.
7. **P1 integrate tested ObumDelivery delivery and OVH rollout in parallel:** existing platform owner handles runner activation and exact-SHA acceptance; no CI redesign. Require privacy, backup/rollback, two-account real browser checks and observable running image/source provenance.

**Next checkpoint BEFORE any additional coding:** report this expanded audit and source-reuse decisions to owner, identify already-running SP13 draft work, obtain review of candidate priorities and limits, and complete initial file-level REUSE-CHECK. This document intentionally does not copy third-party code or authorize a production/employer action.

## 18. Bounded estimates, explicit delivery states and throughput accounting

| Deliverable | Missing-work custom build (engineer-weeks) | Reuse-first hypothesis | Relative speed | Current status |
| --- | ---: | ---: | ---: | --- |
| First permitted, applicant-final Lever submission with verifiable receipt | 6–10 | 2–4 | About 2–3 times faster (midpoints 8/3 = 2.67) | PARTIAL source + draft upload; real ATS E2E UNVERIFIED |
| First explicitly authorized standing-approval ATS lane | 10–16 | 5–8 | About 2 times faster | NOT STARTED / policy and site permission gated |
| Multiple permitted ATS, durable account-scoped queue and signed-in production | 20–32 | 12–18 | About 1.5–2 times faster (midpoints 26/15 = 1.73) | PARTIAL foundations, full release HOLD |

Estimates are remaining engineer-equivalent efforts, not measured calendar promises or earned acceleration. There is **no defensible claim of more than 3 times faster full-platform delivery** absent actual integration timing. Savings are conditional on legal rights, approved ATS test fixture, safe real Google/OIDC login, browser tenant isolation, ObumDelivery availability and quality acceptance. A dependency that costs more to audit/integrate than it saves is dropped; record baseline custom time, actual reuse hours, defect repair, maintenance and total cycle time for every milestone.

**Done (research/source inspection):** 44 internal catalog, 28 external-family discovery, 15 subsystems mapped, pinned upstream shortlists, YouTube/TikTok links traced with confidence caveats, license mismatch/remote egress/unattended submit hazards found. **In progress elsewhere:** SP13 user-approved attachment draft #151, unmerged; independent release candidate #149, unmerged. **Not started by this documentation change:** upstream code copying, provider adapter implementation, full employer E2E or rollout. **Blocked:** rights-approved production employer pilot, true receipt, account/data isolation evidence, exact-head reviewed CI and deployment approval.

**No platform or trading work is implied. SmartPloy remains the only job-application product; ObumAI remains its bounded reusable intelligence/browser service.**

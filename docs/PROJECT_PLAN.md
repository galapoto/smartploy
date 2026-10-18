# SmartPloy — Master Product Plan (reuse-first AutoApply)

**Status:** OWNER-AUTHORIZED IMPLEMENTATION IN PROGRESS (18 October 2026). The user explicitly approved reuse-first coding. This is **NOT** authorization to deploy, submit employer applications, waive security/source rights, or claim production acceptance.  
**Audit date:** 2026-10-18 (Europe/Helsinki).  
**Project:** `galapoto/smartploy`; ObumAI-powered independent Finland-first job intelligence and application product.  
**Existing operational ledger:** [SmartPloy issue #88](https://github.com/galapoto/smartploy/issues/88). The ledger remains the record of what actually shipped; this file is the forward project plan.  
**Detailed evidence, repository inventory, video/TikTok references and license matrix:** [REUSE_FIRST_AUDIT_2026-10-18.md](REUSE_FIRST_AUDIT_2026-10-18.md).  
**Source snapshot when this plan was written:** `main@d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1`; substantial product work remains in [draft integrated PR #149](https://github.com/galapoto/smartploy/pull/149) at `ca56d17a06741f5d8f61b7370391abed1373cba9`. The last historical owner-attested OVH release was `fc94e78e779650e781277ee1056ec92cd26a6e98` on 2026-10-12; **this audit did not reverify the running server**.

## Progress checkpoint — SP14 (18 October 2026)

- **Next build candidate:** [Reviewed employer-question PR #153](https://github.com/galapoto/smartploy/pull/153) stacks on SP13 [PR #151](https://github.com/galapoto/smartploy/pull/151); it **does not** rebuild ObumAI's already existing questionnaire generator.
- **Reuse check:** [SP14 source/policy review](https://github.com/galapoto/smartploy/blob/feature/sp14-reviewed-employer-questions-20261018-v1/docs/REUSE_CHECK_SP14_EMPLOYER_QUESTIONS.md) confirms existing SmartPloy packet, DOM reviewer and one-submit controls plus ObumAI questionnaire/form mapper, Yaima, career-ops and neonwatty alternatives were examined. **No external source code imported.**
- **New review-only capability:** required ordinary Lever text questions can receive individually reviewed and approved values; Finnish/Swedish/English protected/visa/pay/consent questions are excluded, reactive DOM drift aborts, and neither the extension nor a new service silently persists or submits the answers.
- **Exact-commit verification:** [CI #39128565412](https://github.com/galapoto/smartploy/actions/runs/39128565412) at `ffe13cac439b90c6f91969a2aef0506607e4ee59` **5/5 SUCCESS**: **626 Python/PostgreSQL, 86 React, 18 synthetic Chromium**; Compose and exact-source review checks also passed. **Not** an actual ObumDelivery Woodpecker or live employer run.
- **One-attempt hardening:** a discovered weakness allowed document revisions to alter the local attempt key. [SP14 PR #153](https://github.com/galapoto/smartploy/pull/153) now derives it from immutable applicant workspace + exact employer job and uses the Chromium Web Locks API to serialize final clicks between same-profile popups. Fails closed when locks are unavailable. This does **not** provide cross-device/browser atomicity; require a future account-scoped server claim.
- **Product limit:** This is per-application human-reviewed text assistance. It is NOT a tenant-scoped approved-answer memory, autonomous browser service, queue, verified employer submission, or live website deployment. Existing consent/legal/source gates stay active.
- **Next planned reuse:** integrate existing ObumAI questionnaire suggestions through a strict versioned SmartPloy API and tenant-owned approved-answer vault, rather than building a second LLM prompt engine; add bounded queue, provider-specific rights and independently verifiable application results.

## Progress checkpoint — SP13 (18 October 2026)

- **Owner instruction:** Implementation has begun on the approved reuse-first plan, but branch and CI evidence remain separate from deployment.
- **First delivery candidate:** [SP13 PDF-attachment PR #151](https://github.com/galapoto/smartploy/pull/151) builds *on* SmartPloy's existing Lever companion and ObumAI application/preflight contracts; it does not create a second browser/login/CV generator.
- **Reused code:** SmartPloy existing 15-minute packet, application document renderer, reviewed CV text, one-attempt reservation, CRM receipt state and isolated test suite; existing ObumAI design and pinned MIT third-party source used for gap/behavior research, not wholesale vendoring.
- **Implemented in review code:** user-confirmed PDF selection, SHA-256-bound deterministic SmartPloy PDF output and new v2 packet, exact-form browser attachment, negative-case Node/Python/browser tests and source-pinned CI steps.
- **Safety status:** no external third-party source imported; no real employer site visited or submission made; no unattended application authority; browser assignment alone is not independently verified employer acceptance.
- **Verification:** [SP13 exact-commit GitHub CI #39124331412](https://github.com/galapoto/smartploy/actions/runs/39124331412) at `a30716b167c662195b30d25f65e57acdea48056b` passed 5/5 jobs: **621 Python/PostgreSQL, 86 React, 13 Chromium synthetic browser scenarios**, synthetic Compose/backup/health and exact-source review receipt. **NOT** an actual ObumDelivery Woodpecker execution or employer acceptance.
- **Release status:** PR #151 remains DRAFT and stacked on draft [#149](https://github.com/galapoto/smartploy/pull/149); independent review and verified production acceptance remain outstanding. Main/OVH unchanged.
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

**The user approved proceeding with implementation on 18 October 2026.** This approval does not waive code-level REUSE-CHECK, third-party licenses, employer terms, personal-data consent, independent security review or deployment authorization. The eight candidates are research priorities, not eight automatically approved imports. The execution sequence is:

1. Create per-feature `REUSE-CHECK` with pinned eligible source and complete audit; ensure no copyrighted unlicensed code was ported.
2. Build from the *existing* SmartPloy application and ObumAI runtime foundations. Maintain native SmartPloy tenant boundary and migrate only intentional functionality.
3. Keep real production, GitHub main and employer systems unchanged until reviewed CI, owner consent, backup/rollback and signed-in acceptance.
4. Update this plan and [master tracker #88](https://github.com/galapoto/smartploy/issues/88) after every measured actual integration; distinguish source-built, CI-tested, ObumDelivery-tested, deployed, browser-verified and employer-confirmed.
5. Every implementation PR must document which upstream system avoided rewriting, the reuse license/copyright notices, security findings, coverage improvements and engineer-time actually saved.

**As of 2026-10-18:** No external code has been imported, no real application has been sent, and this plan creates no release or employer action authority.

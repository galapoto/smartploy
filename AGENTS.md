# Owner policy supersession — effective 2026-11-18

**OWNER-REVIEW-OPTIONAL-2026-11-18:** An independent human code reviewer, reviewer assignment, and a separate reviewer approval are **NOT mandatory** for implementation, PR merge or software deployment. The project agent/authorized maintainer must conduct direct technical review and complete the applicable tests, security/privacy checks, exact-SHA build, release evidence and rollback verification. An independent peer review is optional if expressly wanted, never a standing blocker.

This supersedes *only* older mandatory independent code-review rules anywhere below or elsewhere in this repository. It does **not** waive legal/regulatory/institutional approvals, signed exam/trading authority, security boundaries, CI/testing requirements, existing GitHub protected-branch controls, or approved project acceptance criteria. Do not fake reviews, bypass protected rules or call incomplete tests passed. Continue source/provenance accounting and ship qualified features promptly.

Canonical portfolio policy: https://github.com/galapoto/Projects/blob/main/docs/governance/OWNER_REVIEW_OPTIONAL_2026_11_18.md

---

# COMPONENT-SKILLS-REA-SPEED-001 — mandatory per-component application (2026-11-18)

For **every changed component**, select, read, and genuinely **apply** the best-fitting authorized/appropriately licensed real skill, not merely name it. Audit first-party existing code, branches, sibling repos, and suitable GitHub donor source before building original code. Evaluate `morluto/rea` on every analyzable reference and use it where authorized/technically useful; a truthful `REA_NOT_APPLICABLE` / `REA_BLOCKED` with evidence is required when it is not used. Never pretend a video, READMEs, reconstructed behavior or REA output is copied source.

**Component-specific mandatory skills**: UI/UX includes pinned Apple HIG foundations + UI/UX Pro Max and web accessibility review, animations require motion/Reduce Motion evidence, cards/illustrations need an appropriate vetted design or vector-asset skill, backend/data/browser/QA require the best relevant source/reuse/testing skill, and Docker/CI/deploy require Docker build/CI/security skills. Apply the **method to the actual diff**; only copy fitting sources with compatible permission/license and sanitize before adopting. Avoid new dependencies when existing first-party CSS/React or APIs suffice.

**Enforcement**: CI script `scripts/check_component_skill_gate.py` requires a changed `docs/skills/receipts/*.json` with traceable per-component skill/source SHA, integration and test evidence for changes to application components. Source-only prose is not acceptance. Do not claim an uninstalled skill executed; using its verified guidance through code review must be labeled `GUIDANCE_APPLIED`. Every run reports COPIED, PORTED, SANITIZED, ADAPTED, INTEGRATED, NEW, NOT_VERIFIED, REA decision, exact tests, measured or NOT_MEASURED build/deploy time and live release stage.

**Canonical authority**: [COMPONENT-SKILLS-REA-SPEED-001](https://github.com/galapoto/Projects/blob/main/docs/governance/COMPONENT_SKILLS_REA_SPEED_2026_11_18.md). This method mandate does not supersede SmartPloy V4, privacy, employer submission permission, user consent, protected branch/CI gates, nor the owner policy making **independent code review optional**.

---

# SMARTPLOY-2027-V3-APPLICABLE-001 — owner V3 method adopted, not a new blueprint

The owner-supplied *ObumAI 2027 Skill/REA First Interface and Fast Delivery Plan V3* becomes **mandatory SmartPloy implementation method** from this run onward, only in the scope documented at [SMARTPLOY_2027_V3_APPLICABILITY_20261118.md](docs/v4/SMARTPLOY_2027_V3_APPLICABILITY_20261118.md). Every AutoApply form, profile, document, browser companion, UI and delivery change must genuinely apply its matching vetted skills, REA/reuse-first proof, direct enabled/disabled/error/receipt interface states, keyboard and reduced-motion controls, actual browser observations and exact release evidence. Keep interfaces opaque where candidates read/edit legally consequential answers; no theater, ornamental blur, infinite worker loops, dependency bloat or copycat UI.

**Current primary vertical slice:** one verified profile -> exact supported job -> two current reviewed documents -> approved answers -> independent one-use final action only where authorized -> same-case receipt/UNKNOWN recovery. Do not import the V3 plan's 16 ObumAI specialist interfaces, 15 internal agent identities, Core/Conductor infrastructure, Studio media or separate orchestration into SmartPloy. SmartPloy V4 remains the authoritative scope. Native Woodpecker + GitHub CI must enforce skill receipt eligibility for changed components, not only prose. Preserve the owner's optional independent code-review supersession and all original legal/consent, security and release controls; a different-identity design review, when requested, never substitutes for real application acceptance.

---

# Repository development instructions

Preserve existing approval, privacy, security and release controls. This file grants no access to other repositories or production resources.

## REA-FIRST-001 — owner P0 reuse-first mandate (29 October 2026)

**MANDATORY for all future approved feature work, website/webapp/API design, software architecture, security architecture, tests and substantial refactoring.** Before coding, inspect existing first-party source/history and licensable upstream implementations, then make and record an REA suitability decision for any comparable authorized app, executable, website, API recording or binary. Consult the [ObumDelivery canonical directive](https://github.com/obumai/obum-delivery/blob/main/docs/REA_FIRST_MANDATORY_REUSE_STANDARD.md) and [decision/evidence template](https://github.com/obumai/obum-delivery/blob/main/docs/REA_REUSE_DECISION_TEMPLATE.md) where accessible.

**Use REA where applicable:** Prefer static/read-only analysis of authorized examples; use its CLI/MCP/browser/JavaScript/native/recorded-API evidence to recover behavior, interfaces, architecture and test cases. Record `REA_APPLIED`, `REA_NOT_APPLICABLE` or `REA_BLOCKED`, with target permission, exact source/version, evidence, unknowns and reasons. Not-applicable is a legitimate documented outcome; an unavailable REA dependency must not indefinitely halt a small useful release.

**Reuse maximally, build minimally:** (1) reuse fit-for-purpose, appropriately licensed code as-is; (2) clean and adapt it; (3) extend only missing functionality; (4) implement remaining code independently with tests. Reuse up to 100% of *relevant, permitted* code, never blindly copy entire projects. REA's own MIT license does not license third-party programs it inspects. Do not copy protected source/assets, bypass controls, import unsafe dependencies or use unanalyzed binaries in production.

**Required proof every run/PR:** plan and baseline SHA; reuse candidates and exact paths/licenses; REA status, tool revision, permitted target, observed evidence and limitations; reused/cleaned/adapted versus new code; executable feature and negative/security tests; actual CI/deploy evidence; measured engineering time with comparable baseline or `savings=unknown`; DONE / IN PROGRESS / NOT STARTED / BLOCKED. Recovered pseudocode, generated code or a green static scan alone never proves user-visible capability.

**Existing authority prevails:** Preserve this repo's stricter security/privacy, protected branch, project-plan/Director GO, independent owner, cost, scope, CI and release controls. This instruction grants no cross-repository write permission, credentials, live trading, real-exam inspection, unauthorized reverse engineering or production deployment. ObumDelivery/Woodpecker remains the authoritative CI where already designated. This is a mandatory engineering-method rule, **not proof that REA is installed or CI enforcement is deployed**.

## FEATURE-FIRST-001 — immediate user-visible per-feature delivery (owner directive 2026-11-04)

**MANDATORY standing rule:** Develop the smallest complete user outcome, with beautiful product-specific UI, real backend/data flow as needed, access controls, failure/retry, meaningful tests, recoverability and a working entry in the ObumAI launcher/sidebar (plus native product navigation) for authorized users. **Ship each independently qualified feature as soon as its own approved checks pass; never accumulate ready features while waiting for a full application, unrelated milestones or a redesign.** Bootstrap every new application with a release route and UI shell alongside its first useful feature. For shared non-UI libraries, prove actual adoption by a real consumer instead of inventing a tile.

Use the canonical [FEATURE-FIRST-001 standard](https://github.com/obumai/obum-delivery/blob/main/docs/FEATURE_FIRST_001_STANDARD.md) and [feature contract](https://github.com/obumai/obum-delivery/blob/main/templates/FEATURE_FIRST_001_FEATURE_CONTRACT.yaml). Declare `SOURCE_READY`, `CI_QUALIFIED`, `STAGED`, `DEPLOYED_DARK`, `RELEASED`, `USER_VERIFIED` honestly; only `USER_VERIFIED` is **SHIPPED**, based on actual deployed artifact/role-appropriate UI journey and recovery evidence. Use current native Woodpecker/ObumDelivery where designated, trusted promotion, REA-FIRST reuse, product-specific boundaries and existing security/Director/approval/incident holds. This is an owner policy, **not automatic CI enforcement or blanket production/deploy authorization**. On blocked releases, report the precise missing proof, owner and next action; do not label invisible, disabled, mock or draft-only code as shipped.

## SMARTPLOY-V4-LOCK-001 — owner direction (7 Nov 2026)

**Binding source:** [V4 Production-First Contract](docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md). This is the task and acceptance authority for every SmartPloy AI or human code contribution. Preserve all stricter existing security, legal, privacy, CI and production-approval gates.

**AUTOAPPLY FIRST.** Finish real signed-in CV -> choose mode -> select an exact real employer job -> verified live form fill -> approved documents -> ready for review; only separately authorized server-claimed submission may be sent. Qualify both Playwright and extension independently. UI, document quality, QA and hosted isolation advance in parallel without diverting the AutoApply critical path. No fake success, mock-only release or unreleased mega-branch.

**NO SILENT SCOPE DRIFT.** Every issue and PR names a V4 section, candidate-visible outcome, source baseline, dependency, acceptance proof and deployment status. Do not introduce an unrelated framework, separate competing case controller or cosmetic-only "AutoApply" mockup. If source reality or permission conflicts with the plan, document the exact conflict and smallest safe adjustment. Never weaken safety/approval rules to meet a date.

**COPY / SANITIZE / ADOPT BEFORE BUILDING NEW.** Inspect existing SmartPloy and authorized ObumAI code first, then V4-qualified donors. Reuse the smallest fitting authorized/licensable unit with exact provenance, source SHA, license notices, dangerous side effects removed, sanitized networking/credentials/PII, contract tests and negative tests. Use REA where authorized and useful; mark REA_APPLIED, REA_NOT_APPLICABLE or REA_BLOCKED. Implement original code only when the reusable unit demonstrably does not meet the target; explain that decision in a manifest.

**FEATURE-FIRST-001 remains mandatory.** A capability is not shipped until exact deployed SHA, CI, public signed-in UI journey, verified employer effect and rollback are recorded. An attempted click is not confirmed submission; post-submit disconnect is UNKNOWN pending reconciliation and never blindly resent. Production, credentials and employer sends require the existing authorized gates.

## LEAN-REA-FLOW-001 — mandatory lean reuse, flow-first UX and proof after every run (7 Nov 2026)

Before writing fresh code, examine the exact existing source and suitable authorized upstream donors; **show each donor project/repository URL, pinned SHA, copied original file, sanitized/adapted destination, what was adopted into the real runtime, and why any remaining original code was necessary**. Distinguish actual code copying from an interface wrapper, a fake SDK, a design inspiration or research. If nothing was copied, say **"Copied: none"** with the reason. Reuse the smallest component; keep architecture, runtime, dependencies and bundle light; avoid parallel engines and unnecessary abstractions. Measure footprint/performance differences or write **NOT_MEASURED**.

Prefer **action-oriented visual flows** and progressive disclosure to heavy explanatory text: a clear primary action, honest clickable cards, minimal microcopy, responsive light/dark accessible UI, real results and failure states. At the end of **every run**, publish source/donor evidence, reuse vs sanitized vs new files, size/dependency delta, before/after user flow, actual test/CI state, exact PR/SHA, and **user-verified usable features with real route/launcher evidence (or NONE VERIFIED)**. Preserve **FEATURE-FIRST-001**, **REA-FIRST-001**, all stricter legal/security/independent review/deployment rules. No policy-only commit is evidence of a shipped feature or automatically enforced CI.

Canonical: https://github.com/obumai/obum-delivery/blob/main/docs/LEAN_REA_FLOW_001_STANDARD.md
Receipt: https://github.com/obumai/obum-delivery/blob/main/templates/LEAN_REA_FLOW_001_RUN_RECEIPT.md

## GALAPOTO-INDEPENDENT-REVIEW-001 — mandatory independent-agent review assignment (8 Nov 2026)

**For EVERY commit/PR/release that requires independent review, the project lead agent owns getting that review assigned in the same run.** Search capable, available, independent reviewers in this repository FIRST, then in authorized adjacent repositories under the same `galapoto/*` GitHub account. Assign an eligible reviewer instead of waiting for the owner to find one or accumulating CI-qualified work. Verify the reviewer is not the author, implementer or the same agent/session under another name; check expertise, availability and actual target-repository access.

Request review using a real GitHub reviewer account/team when permitted. If an independent adjacent agent lacks such an account, create a linked, traceable PR/issue handoff (exact source SHA, review scope, reviewer identity, security/tests and outcome), **without pretending a GitHub review request or approval occurred**. Never grant cross-repo access by assumption, impersonate an account, expose secrets or substitute an AI review for a required human/security/owner approval. If no qualified reviewer is available, document `REVIEWER_UNAVAILABLE`, the repositories/people checked, and the smallest actionable escalation; keep required approvals and release holds intact.

Record `REVIEW_REQUIRED`, `REVIEWER_ASSIGNED`, `REVIEWED`, `REQUIRED_APPROVALS_MET`, `MERGED_MAIN`, `CI_QUALIFIED_MAIN`, `RELEASED` and `USER_VERIFIED` as distinct evidence states. Once independently approved, ship each independently qualified user-visible feature promptly via the repository's approved **main** release route; never confuse a reviewer assignment, CI success or main merge with verified production usability. Preserve stricter project security, privacy, branch, legal and production controls.

**Canonical owner policy + receipt:** [GALAPOTO-INDEPENDENT-REVIEW-001](https://github.com/galapoto/Projects/blob/main/docs/governance/GALAPOTO_INDEPENDENT_REVIEW_ASSIGNMENT_001.md).


## SMARTPLOY-OBUMBROWSER-001 — shared hosted browser, independent client (11 Nov 2026)

**Owner-approved controlled V4 amendment:** SmartPloy retains the authoritative application case, approved CV/letter/field facts, ATS policy, explicit candidate permission, and receipt reconciliation. The EXISTING Chrome MV3 extension stays independently shippable, and the separately reviewed local Playwright helper may remain as candidate-owned fallback. **Do not build, deploy or embed a second SmartPloy-owned hosted Chromium/noVNC/CDP infrastructure.** When the shared browser is qualified, integrate through an explicit SmartPloy consumer adapter against `obumai/ObumBrowser`'s independently versioned, reviewed service API, never by importing its worker or copying Floently profiles, cookies, identities, database, tunnels or secrets.

**No premature availability claims:** ObumBrowser draft PR #4 is source-ready only at adoption; its historic v0.1 cloud signaling code is NOT a stable endorsed production SmartPloy API. Until its typed session/action API, OIDC audience/scopes, native same-session Chromium+RFB, egress isolation, pause/takeover/stop, independent review, signed-in stage and production acceptance are verified, no hosted option/button may be presented as operational. The current extension and document preparation must continue to ship separately.

**Contract-first boundary:** Reuse SmartPloy's `review_handoff` and exact ATS URL validation. The `smartploy/obumbrowser_handoff.py` internal navigation intent contains public employer URL only: no applicant facts/CV, no credentials, no browser-session claim, upload permission or employer-send permission. Future session action authority must be rechecked per owner, job, packet revision and user approval on every action. ObumBrowser owns generic browser execution, SmartPloy owns job-specific field planning and decisions. Record `SOURCE_READY` versus `INTEGRATED` versus `USER_VERIFIED` honestly.

**Change receipt:** `docs/v4/SP_CR_OBUMBROWSER_001_20261111.md`. This changes only the V4 hosted browser *ownership* decision; all existing strict V4 AutoApply gates, document requirements, release/independent-review and no-unapproved-submit behavior remain in force.

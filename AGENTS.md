# Mandatory Agent Run Proof Rule (GLOBAL-AGENT-RUN-PROOF v1)

**Owner directive: 21 October 2026. Applies to every coding, planning, architecture, research, QA, review, CI/CD, deployment, orchestration and product agent, and every human-contributed agent run, in the galapoto development portfolio: `galapoto`, `obumai`, `Floently`, `komplyint`, and `Nordvantage`.** Every single run must include a truthful evidence report, even if work is blocked or no code is changed. Include this rule in new repositories when created.

**Hierarchy and safety:** This is an additional mandatory progress/provenance contract. Preserve existing per-repository `AGENTS.md`, project charter, protected approval signals, confidentiality, least-privilege repository access, production release holds, branch and CI controls. If this instruction conflicts with a more restrictive security/scope/approval rule, the restrictive rule wins. Reporting does not authorize cross-repository writes, live trading, deployments, cloud mutations or secrets access.

## At the start of EVERY run

1. **Find the plan and the exact task.** Read the authoritative project plan, requirements/acceptance criteria, current implementation and most recent delivery/agent checkpoint. Identify the exact **project plan section, subsection, requirement or milestone ID** to be advanced. Include a plan-file link + commit/ref, not only a vague feature name. If no plan exists, explicitly label **PLAN GAP**, record the intended core behavior and define/seek a tracked plan entry before treating the feature as complete.
2. **Record the previous stage.** Cite the before-state: previous baseline commit SHA, PR/issue, live deployment SHA or `unverified`, relevant current functionality, known failing cases, outstanding blockers and prior agent handoff. Distinguish source, test, integration and live states.
3. **Search for reuse BEFORE designing replacement code.** Inspect the current repository and its earlier branches/history, product siblings or previously built systems **only where read access is authorized**, and relevant upstream projects (including GitHub projects discovered through videos/articles/YouTube/TikTok when relevant). Search for working components, protocols, UI, data models, test fixtures and integrations. Record the concrete candidate URLs, file paths, revisions, ownership and licenses. Treat videos as discovery leads, not evidence that code is usable. Inspect dependency security, provenance, maintenance, test coverage, completeness, architecture fit, performance and sufficient depth/width of behavior.
4. **Make the reuse-or-build decision explicit.** Prefer (a) reuse reliable code as-is, then (b) repair/clean/refactor/test/adapt a permitted existing implementation, then (c) improve incomplete components, and only then (d) build genuinely missing parts from scratch. Identify what existed, what was reused unchanged, what was adapted and why, and what is new. If existing code is unsafe, unreliable, incomplete or too shallow/narrow for the planned core path, show objective reasons. **Never copy proprietary, unlicensed or incompatible-license source merely because it can be modified.** Comply with license conditions/attribution; use independent implementation from permissible requirements when reuse rights are absent.

## During EVERY run

5. **Advance the actual core function.** Map changed files and runtime behavior to the plan ID and the user's primary app journey. Prioritize real core components and useful vertical product slices, not cosmetic churn, documents-only activity, duplicate frameworks or auxiliary research. A test, review, security or infrastructure run qualifies only by proving which core path it protects/unblocks and how.
6. **Show an actual before/after stage change.** For each delivered item state: *Previous stage -> New stage*, what changed, affected component/file/API/user journey, acceptance evidence and whether it is currently usable by a user. Explicitly label `source-only`, `tested`, `staged` or `production-verified` as appropriate; a commit, mock, green synthetic CI or queued deployment alone does **not** prove a working live feature.
7. **Verify and preserve safety.** Run the original authoritative CI/test/deployment gates without quietly disabling, weakening or skipping tests. Cite exact commits, run IDs, failed checks, repro steps, smoke results and any retained regression. ObumAI projects should use ObumDelivery/Woodpecker where that is their designated authoritative CI; others use their documented authoritative checks. No invented pass or timing numbers, no credential exposure, and no bypass of open security/production holds.
8. **Integrate without repeating others' work.** Reconcile shared contracts and changes with the existing owner agents and plan. Do not build parallel replacement stacks where reviewed components already exist. Do not change other agents' repos or production environments outside explicit scope/authority.

## REQUIRED end-of-run report — every agent, no exceptions

Use these fields with direct links/evidence or write `unverified`/`not applicable` and explain why:

**A. Plan mapping:** Repository, agent/role, plan filename/ref + exact section/subsection/requirement/milestone ID; acceptance criteria; core user journey or protected critical path.

**B. Stage delta:** BEFORE baseline SHA, feature status, CI/deployed status and known gap -> AFTER exact commit SHA, changed paths, behavior, test result and truthful user availability. Explain specifically **what is different from the previous project stage**.

**C. Core-function proof:** Which core subsystem/function improved; how the change advances the planned main function; concrete user flow, endpoint, UI or integration proof; which functions still do not work. Distinguish vertical user journey and horizontal integration progress.

**D. Reuse-first evidence:** Search locations and candidates (own repo, existing products and relevant external source), upstream path/URL/commit/license, safety/depth/completeness review, exactly what was **reused unchanged**, **cleaned up**, **adapted** or **improved**, and links to the resulting diff. Say `no suitable reusable component found` only with documented search and rejection reasons.

**E. Scratch/new-build evidence:** Every genuinely new module, function, page or integration with paths; why available implementations were not adequate or legally reusable; what new capability it adds. Do not label a wrapper or refactor as fully built from scratch.

**F. Verification and delivery:** Test counts/outcomes (failed/pending/skipped stated), CI run URL and exact tested SHA, relevant security/recovery evidence, PR/merge SHA, deployment identity and live URL/acceptance receipt where applicable. If deployment is unverified, say so. Do not claim a release, live login or working trading feature from source tests alone.

**G. Whole-project progress:** Overall roadmap/workstream stage and planned acceptance milestones: **DONE / IN PROGRESS / NOT STARTED / BLOCKED**, what moved since last run, vertical and cross-system progress, remaining high-impact gaps, dependencies, next core task, and a grounded estimate or explicit uncertainty. Quantify percent complete, build-time savings and speed multipliers **only if the denominator and measurement evidence exist**.

**H. Ownership and safety:** What other agents' work was reused/reconciled, what awaits owner approval, license/security issues, exact handoff, and whether any real user, environment, money, data, access policy or production service changed.

### Copyable compact report format

```text
RUN: <date> | <agent/role> | <owner/repo> | <issue/PR>
PLAN: <path@ref#section / requirement ID> | CORE PATH: <expected user action>
BEFORE: <SHA, source/test/stage/live status, gap>
AFTER: <SHA + links, changed files, behavior, whether usable now>
CORE PROOF: <endpoint/UI/worker/result + acceptance receipt>
REUSE AUDIT: <searched repos/projects; upstream/path/SHA/license/security>
REUSED: <unchanged> | ADAPTED/CLEANED: <diffs> | SCRATCH: <paths + why>
TEST/CI: <authoritative check URL, exact SHA, pass/fail/pending>
DEPLOY: <source-only/staged/live-verified + evidence; safety holds>
OVERALL: DONE <...> | IN PROGRESS <...> | NOT STARTED <...> | BLOCKED <...>
PROGRESS SINCE LAST: <vertical/horizontal milestone changes; measured only>
NEXT: <highest-value core plan item + owner/dependency/estimate or uncertain>
```

**Enforcement discipline:** An agent must not call a run `completed` or report project progress as verified if it omits plan mapping, delta, core proof, reuse/scratch provenance, actual verification or whole-project status. A blocked run must report the blocker and legitimate next step instead of inventing deliverables. Keep each report on the associated PR/issue/delivery checkpoint as well as in the user-facing update. Apply the contract to every run, not only to release summaries.

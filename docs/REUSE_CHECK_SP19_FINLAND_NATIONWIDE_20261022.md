# SP19 — Nationwide Finnish IT, VAKE Planner and office-coordination coverage

Updated 2026-10-22. **Source candidate ≠ observed live Finnish vacancies.**

## Project-plan subparts implemented
- **Discovery coverage / worker ingestion:** expand the explicit seven-board reviewed IT portfolio into a **22-board Lever, Greenhouse and SmartRecruiters roster**, with a guarded private OVH cutover from the live legacy five-source selection. Remove the driving-heavy TSMG source, currently timing out.
- **Finnish relevance / personalized matching:** expand the **existing** `career_scope` and `search_preferences` title-only recognition of IT planning, office/document/intranet/communications and VAKEHYVA TKKI Planner-adjacent duties. No CV, qualification, seniority or employer permissions inferred.
- **Scale of ingestion:** avoid downloading full details for thousands of explicitly non-Finnish SmartRecruiters list items. For missing/ambiguous country, fetch the detail rather than silently losing potential Finland jobs.
- **Release operations:** re-use original private env and worker; support safe exact-roster 5→22 and 7→22 updates, repeatable dry-run and rollback, atomic 0600 env writes, no new secret, no new host service.

## Hard baseline — observed on OVH 2026-10-22
```text
active_jobs_all_sources=75
configured_ats_sources=5
Finnish matching source snapshot records=10
healthy_ats_sources=4
failed_ats_sources=1 (lever-global-tsmg: network_timeout)
jobmarket_finland_enabled=false
kuntarekry_feed_configured=false
auto_draft_enabled_in_config=true
auto_draft_task_enabled=true
auto_draft_last_status=healthy
```
Active all-source jobs are NOT 75 verified current Finnish openings; source counts may overlap, and an ATS config listing 22 providers is NOT 22 healthy feeds or proof of any newly fetched jobs.

## Reuse-first proof

| Existing code reused/adapted | How |
| --- | --- |
| `smartploy/sources/public_ats.py`: Lever, Greenhouse, SmartRecruiters official public GET adapters | Configure additional operator-selected tenants; only adapt pre-detail country filtering in SmartRecruiters |
| `config/finland_it_public_ats_portfolio.json` | Preserve its seven reviewed original employers, add 15 candidates |
| `scripts/configure_finland_ats_pilot.py` | Reuse atomic private env staging (backup by operator), exact-input comparison, same `--apply` flag, and previous 5/7 source registries |
| `smartploy/worker_runtime.py`, `worker_schedule.py`, Postgres job/source-health/retirement logic | No extra polling engine, untrusted web crawler, separate queue or table |
| `smartploy/search_preferences.py`, `career_scope.py` | Expand title/translation conditions; preserve exact account preferences and opt-in draft guards |
| `scripts/check_ats_readiness.py`, `compare_ats_readiness.py` | Existing read-only live counts/health/timestamps; no fabricated metrics |

## New code, not reused
- `config/finland_nationwide_ats_portfolio.json`: 22-source static list (9 Lever, 7 Greenhouse, 6 SmartRecruiters), 20 nationwide/city markers per source; 15 are **candidate employer slugs**, not confirmed live production successes.
- `reviewed_nationwide_portfolio()`, `plan_nationwide_portfolio_upgrade()`, new CLI flags to safely stage/undo exact reviewed 5/7/22 configurations. Uses only stdlib on OVH.
- Read-only SmartRecruiters list-time country filter: fewer foreign detail requests; incomplete/failed snapshots retain existing non-retirement rule.
- More precise Finnish/English IT planning, office coordinator, information management, knowledge/content/intranet, digital communication and VAKE Planner-adjacent title patterns.
- Synthetic regression tests: roster limits/uniqueness, privacy, no TSMG, staging dry-run/apply/rollback, non-FI SmartRecruiters skip, title positives & driver/warehouse negatives.

## Candidate roster, not claimed live
**Lever (9):** Upright Project, Brightly Works, Netlight, Rovio, Alif Semiconductor, Dun & Bradstreet, Jobgether, Welo Global, Quadcode (EU).

**Greenhouse (7):** Oura, Wolt, Smartly, AlphaSense, EnergyHub / Kapacity.io, Yousician, Pronto.

**SmartRecruiters (6):** AFRY, Deloitte Nordic, Ramboll, YIT, Tieto, Turner & Townsend.

An ATS API permits public read discovery only subject to published terms and policy; does not confer permission to submit a job application, scrape login-protected boards or forward user CV data. The chosen roster is a **high-coverage discovery trial**, not a legal warranty, up-to-date jobs guarantee or identity/qualifications audit. Each failure remains visible in source health; one bad board must not hide other healthy results.

**Limitations:** Source rosters alone cannot provide all Finnish vacancies. Official national Job Market Finland's KIPA P67 retrieval requires KEHA onboarding/credentials; Kuntarekry employer RSS requires authorized feed; Duunitori/LinkedIn unrestricted scraping is not enabled. More adapters and licensable national aggregators are separate work. A third-party free/commercial jobs API is not automatically licensed for production. Existing max 20 city/region markers and structured location-only filters can omit postings that say only an unlisted municipality; future nationwide municipal data and nationally authorized sources should improve recall.

## Deployment and rollback plan
1. On root-managed OVH `/srv/obum/stacks/smartploy`, verify deployed baseline exactly `c2c5377e6279131cbf7ed12a19c004cb4b84ce48` and recorded OIDC, no dirty tracked tree, compare `origin/main` with approved exact new main SHA, ensure private 0600 env. Independently verify exact-head CI green.
2. Create a root-only `0600` backup of existing `deploy/personal/env`; **never print or commit private environment**. Run `python3 scripts/configure_finland_ats_pilot.py --upgrade-nationwide-portfolio` dry-run and review its sanitized receipt; apply with `--apply`.
3. Preserve `SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc` and `SMARTPLOY_RELEASE_APPROVED_SHA=<exact-main-SHA>`, invoke the existing guarded `deploy/personal/scripts/deploy.sh`. This backs up PostgreSQL, rebuilds, migrates, restarts worker, validates Caddy/OIDC/TLS/source provenance and commits SHA receipt.
4. Read-only snapshot `docker exec smartploy-worker-1 python scripts/check_ats_readiness.py --require-fresh-hours 6`; don't hide failed boards or claim they were ingested. Let worker naturally poll 22 tasks within schedule, monitor upstream timeouts/rate limiting; no login/applicant data in operator output.
5. Roll back only with an explicit approved rollback operation (`--rollback-nationwide-to-five` or `--rollback-nationwide-to-seven`) and original guarded `deploy.sh <approved-old-SHA>`. Do not blindly restore DB or delete jobs merely because a new source fails; retained source health provenance matters.

## Real AutoApply truth
AutoDraft remains a local per-user opt-in shortlist/draft step for approved facts and recently verified jobs (within 48 hours), with no external employer POST. Activating more source adapters will not itself send CVs or cover letters. A real end-to-end applicant path (signed-in search→verified match→draft→review→authorized provider ACK) requires independent acceptance; no claim of broad unattended submission.

## Evidence state
- Base main before SP19: `c2c5377e6279131cbf7ed12a19c004cb4b84ce48`.
- Working branch: `feature/sp19-finland-nationwide-coverage-20261022`.
- CI candidate and merged exact SHA must be recorded from GitHub Actions and PR, not inferred.
- OVH live source count after this commit: **unverified pending guarded operator rollout**.
- Actual Finnish posting increase after source activation: **unverified**. It depends on which ATS tenants accept public GET and the latest live employer inventories.

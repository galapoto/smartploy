# SP20 — Finland traineeship radar and Ashby nationwide coverage

Date: 2026-10-22. Source baseline: exact deployed SP19 `e1af89af7d9be191f48db84a2eee64db9d879320`.

## Project-plan core work implemented
- **Source adapters / nationwide discovery:** support **Ashby published Jobs GET API** on fixed vendor domain; configure seven candidate real employer boards: Hoxhunt, Reaktor, Skylo, Swarmia, Distance Technologies, ZEAL Network and n8n. These extend the existing 22 reviewed ATS configs to **29 candidate feeds**. The normal continuous source worker polls them; their actual Finnish vacancies and success must be measured live.
- **Trainee opportunities:** a distinct first-party **Training & traineeships** page and read-only `GET /api/v1/training-programs` exposing twelve official programme provider *destinations* (including three specifically source-checked Saranen intakes with dated deadlines), including Saranen RekryKoulutus/aikuiskoulutus, Academic Work Academy, Siemens Software, Nokia early careers, Valtiolle.fi and Kuntarekry. These links **are not declared as open intakes, are not counted as live jobs, and cannot trigger AutoApply**.
- **Source-backed trainee/graduate jobs:** classify advertised titles plus documented employer ATS employment type as internship / traineeship / graduate / ordinary job; expose on normal job cards and add client-side type filter in General search. Title/ATS classification is **not** eligibility, salary or an active recruitment-training intake.
- **Deployment operator guard:** reuse 0600 private env atomic staging with a new explicit `--upgrade-ashby-trainee-portfolio` / `--rollback-ashby-trainee-portfolio`; refuse arbitrary old/custom configurations, preserve the exact existing 22 entries, and require no new host Python package.

## Reuse-first evidence
| Existing functionality | Reused/adapted | New code |
| --- | --- | --- |
| `PublicATSAdapter`, `_get_json`, fixed allowed endpoints, `PublicATSSourceConfig` | Original source read, host checks, bounded full snapshots and source health | `AshbyAdapter` GET, published-only jobs + structured Finland location, stable source ID |
| `poll_public_ats`, `worker_runtime`, `worker_schedule`, PostgreSQL | **Unmodified** worker and schedule, retries, health and safe retirement | No new task scheduler or database |
| Source `2026-10-22` SP19 22-boarding policy | 22 unmodified entries | Seven extra reviewed boards and reversible 29-source upgrade |
| `career_scope`, `search_preferences._job_card` | Existing title-only matching and company source provenance | Explicit internship/trainee/graduate indicator, no CV inferencing |
| `SearchResultsPanel` React and `App` navigation | Existing authenticated SPA and read-only searches | Job-type filter and new training-provider page |
| `smartploy.api` / local JSON configs | Existing same-origin API and deployment packaging | Static validated programme destination directory, no scraping or private processing |

## Source links and explicit limitations
Official Ashby published-job API: https://developers.ashbyhq.com/docs/public-job-posting-api
- GET `https://api.ashbyhq.com/posting-api/job-board/{tenant}`
- `isListed=false` or absent is excluded; the source URL must belong to exactly the named board on `jobs.ashbyhq.com`, no redirects or arbitrary hosts.
- Include only explicitly Finnish structured locations. Remote alone never means Finland. No new employer-posting or applicant submission grants.
- A 29-source config is **potential**, not measured 29 successful feeds. Some ATS identifiers may no longer be active; failed feeds must stay visible in readiness metrics, rather than fabricated listings.

Official programme references:
- Saranen: https://www.saranen.fi/aikuiskoulutus and https://www.saranen.fi/tyonhakijalle/toihin-koulutuksesta
- Academic Work Academy: https://www.academicwork.fi/academy/koulutukset
- Siemens early careers: https://www.siemens.com/fi-fi/company/siemens-software-student-talent-programs/
- Nokia early careers: https://www.nokia.com/careers/students-and-graduates/
- Kuntarekry: https://www.kuntarekry.fi/fi/tyopaikat/
- Valtiolle.fi: https://valtiolle.fi/fi/

**Not included:** automatic crawling of Saranen or Siemens programme pages, KEHA workforce-training API (separate permission), LinkedIn/Glassdoor scraping, employer application submission. These are future separate connectors with explicit source permissions.

## Tests and acceptance
- Synthetic Ashby published/intern/graduate/secondary Finnish location, false remote anywhere, unlisted and foreign rejection, invalid hosted board URL, overlarge board and upstream failure preserving existing jobs.
- Directory validation rejects counterfeit source host and duplicated IDs, non-vacancy schema, never called employer endpoints, read-only no-store API.
- 22-to-29 exact-source upgrade/dry-run/rollback with private env preservation and `python -I -S` stdlib-only host execution.
- React separate programme page, provider/category/search filter, secure links and no false active-jobs count; normal listing early-career filter.
- Exact head GitHub CI + PostgreSQL tests + browser + web + Docker simulation + review receipt required before merge.
- Current verified production state: SP19 22 candidates, not yet measured live successful feeds. SP20 live success **not claimed** until an exact merged SHA is deployed on OVH and all new sources have had a chance to poll.

## Rollout
1. Get final verified merged main SHA and all 5 CI jobs green. No unreviewed side branches.
2. On `obum-core-01`, backup `deploy/personal/env` mode 0600, ensure source exactly equals reviewed 22 candidate config, stage `--upgrade-ashby-trainee-portfolio --apply`, run preflight + guarded `deploy.sh <exact SHA>`; retain OIDC and AutoDraft env.
3. Verify `/api/v1/training-programs` via signed-in SmartPloy SPA; open Training & traineeships page. Check Source monitor: actual `ashby-*` healthy status / count. Run `scripts/check_ats_readiness.py` after scheduled source polls to count unique Finnish postings, not only configured sources.
4. If a newly added board is invalid or unavailable, keep it in failed source health for diagnosis; roll back only the 29-to-22 source configuration and redeploy exact approved previous SHA if needed.
5. Next core work: add employer-enabled Personio XML, published Recruitee XML, KEHA P67 v2 backfill after credential approval and authorized multi-employer Kuntarekry access. Maintain separate *training programme landing page* and *source-backed live job* counts.

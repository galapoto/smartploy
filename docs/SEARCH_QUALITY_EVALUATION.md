# Offline bilingual job-search quality evaluation (SP-14)

This is a **reproducible regression suite**, not a claim about real-world
recommendation accuracy, employment eligibility, or live ATS coverage.

## Scope

- 36 fictional, labeled search and approved-evidence examples covering
  English/Finnish job titles, Finnish junior/senior words, EN/FI/SV labels,
  unknown metadata, Finnish city boundaries, remote/hybrid work, career-switch
  discovery, false substring matches, and degree-level/subject checks.
- No user profile, real CV, employer ATS response, applicant identity,
  external LLM, cloud endpoint, browser profile, database or OAuth credentials
  enter the benchmark. The manual source URLs use the reserved
  `jobs.example.invalid` domain, which is never fetched.
- It evaluates the existing `search_jobs` search preference alignment and
  `score_candidate` approved-evidence fit independently. The former **must
  not** be called a verified qualification score.
- A single candidate per fixture avoids ranking-order ambiguity. This is a
  controlled *classification* regression suite, not search-ranking NDCG or an
  empirical relevance study.
- Synthetic expectation labels were specified before executing this runner
  against the implementation. Neither a passing fixture nor `100%` synthetic
  precision proves a recommendation is correct for actual Finnish vacancies.

## Run locally or in normal repository CI

~~~bash
python -m scripts.evaluate_search_quality
python -m scripts.evaluate_search_quality --json
pytest -q tests/test_search_quality_evaluator.py
~~~

Expected machine contract: `smartploy.search-quality.synthetic.v1`.
Results include total search/fit cases, per-category pass counts and
recommendation TP/FP/FN/TN with synthetic precision/recall. Failures show
**case IDs and assertion labels only**, not job descriptions, profile evidence
or URLs. The process exits nonzero on any failed label, and fails closed on an
invalid/duplicate/empty fixture.

The `--fixture` flag supports an *offline*, separately curated anonymized
case set using the same contract. Do not commit real personal CVs, applicant
identities, cookies, internal application answers or restricted Job Market
Finland source records. Validate provenance and source permissions first.

## Additional SP-14 release acceptance (not satisfied by this fixture)

1. Independent ObumBench or authorized evaluators create a provenance-tagged,
   legally usable labeled sample of current Finnish/English vacancies and
   approved *synthetic* applicant profiles.
2. Freeze a rubric: relevant/related/unrelated, junior/experienced conflict,
   allowed work modes, verified versus missing mandatory requirements,
   explicit language preference, current country/city and temporal freshness.
3. Report precision at recommended and Explore-more lane, recall, unknown
   classification accuracy, fatal false-qualification count, subgroup metrics
   (Finnish, English, healthcare career switch, environmental and public
   sector) and disagreements requiring human adjudication.
4. Establish *pre-registered* minimums and a documented error budget on
   withheld validation examples. Avoid scoring the real sample after using it
   to tune the rules.
5. Verify owner/browser acceptance and actual OVH deploy separately.
   Employer submissions remain disabled without case-specific user approval;
   an automatic draft recommendation is **not** a submission.

## Editing discipline

Keep each fixture synthetic and labeled with a stable, nonidentifying ID.
New rules should be accompanied by positive cases, negative cases and
unknown-information cases, not only impressive examples. Track observed
source counts and legal permission separately from quality scores. Update
[the master tracker](https://github.com/galapoto/smartploy/issues/88)
without marking SP-14 complete until real, legally sourced evaluation exists.

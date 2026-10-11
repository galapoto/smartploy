# Finnish/English matching quality benchmark (synthetic v1)

**Project milestone:** SP-14, tracked in [#88](https://github.com/galapoto/smartploy/issues/88).

This versioned, offline acceptance set catches regressions in **job-search preference
alignment** and the separate **approved-evidence Fit** boundary. It is an
engineering regression test, **not** calibrated precision or recall on real
employers, a measurement of actual hiring outcomes, or an automated legal
eligibility determination.

## Run locally

From the repository root, with development dependencies installed:

~~~bash
python scripts/evaluate_matching_quality.py
pytest -q tests/test_matching_quality_benchmark.py
~~~

The evaluator prints a machine-readable JSON report and exits:
- **0** when every synthetic case passes;
- **1** when at least one expectation fails;
- **2** on an invalid/unreadable fixture or evaluator contract.

CI executes the evaluator in addition to unit tests, web and Chromium jobs,
and the protected Docker stack. A passing PR must subsequently pass
**push-to-main CI on the exact merge SHA** before an OVH release can be considered.

## Data scope

All 22 cases are manually written synthetic examples in
\`benchmarks/matching_quality_fi_en_v1.json\`. They include no real names, CVs,
candidate sessions, employer applications, authenticated API requests, stored
user search preferences or live fetched job descriptions. They have a fixed
evaluation timestamp and synthetically generated application URLs on
\`synthetic.example.invalid\`, which the evaluator does **not** visit.

The v1 coverage categories include first-use vs General mode, English/Finnish
job title equivalence, seniority inferred only from explicit user choices,
unknown job language/location/work metadata, preference differences,
remote/hybrid arrangements, complete-word role/keyword/skill boundaries,
posting-date ordering, degree-level requirement evidence, and a career-switch
mandatory-skill gap.

A search result **recommended** in this benchmark means only that the
algorithm would show it in the top preference-alignment lane. It does not
establish that the person is qualified, legally eligible, or likely to receive
an interview. The separate evidence cases check that an unapproved qualification
cannot pass, that a Bachelor's plus unrelated skills cannot prove a Master's,
and that missing mandatory approved evidence never authorizes auto-preparation.

## Interpreting reports

\`passed_cases/total_cases\` is the **synthetic fixed-case regression pass
rate**. A 100% score means only that the implementation still satisfies the
hand-authored expected behaviors. It must **not** be relabeled user match
accuracy, recruiter relevance, CV suitability, or employer verification.

The report lists individual failed fixture IDs, classifications and expected
vs observed behavior. Categories are required so a superficial change cannot
silently delete difficult cases. Changing gold labels or categories requires
code review explaining the acceptance policy change, not a blanket update to
make tests pass.

## Next evaluation tiers (not yet completed)

1. Independently reviewed and anonymized Finnish/English production job
   examples with valid acquisition/retention and permission basis.
2. Human relevance labeling with explicit inter-rater disagreement and role/
   seniority diversity, kept apart from self-reported qualifications.
3. Before/after slice metrics, error bars, coverage monitoring, fairness review
   and user-facing explanation clarity.
4. Separate authenticated-browser acceptance (#91) and authorized employer
   submission acceptance (SP-16). Synthetic CI never replaces these gates.

Never forward a user's CV or a source-restricted job posting to cloud AI merely
to improve benchmark scores.

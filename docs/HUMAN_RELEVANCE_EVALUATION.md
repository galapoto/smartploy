# Independent Finnish/English relevance review (SP-14, offline v1)

This complements the 36-case synthetic regression evaluator in
[SEARCH_QUALITY_EVALUATION.md](SEARCH_QUALITY_EVALUATION.md). That regression
suite tests rules against prewritten answers. The human-review workflow below
can **later** measure SmartPloy's precision and recall **within a frozen,
reviewed sample of lawfully usable job examples**, including Finnish and English.
It does not measure hiring success, confirm employment eligibility or justify
a generalized claim of market-wide job matching accuracy.

**Current implementation state:** the repository includes only 12 **fictional**
anonymous examples demonstrating the workflow. No employer data, user CV,
production database, web browsing, AI provider or external ATS is involved.

## Review lifecycle

1. **Source approval and anonymization:** the owner and source-rights reviewer
   choose job examples with documented rights for this *specific* evaluation.
   Restricted third-party job text, applicant CVs, contact details, private
   profile features, account identifiers, form answers and access tokens are
   never copied into the evaluation inputs or CI artifacts. Store original
   permitted job materials in separately access-controlled private storage.
   Assign random non-identifying IDs such as \`case-00001\`, not titles or URLs.
2. **Freeze a dataset manifest** (\`smartploy.human-relevance.set.v1\`) with
   \`dataset_id\`, categorical slice flags, a timestamp and reviewed provenance
   booleans. Real datasets require the source-rights approval attestation,
   confirmation that applicant/restricted content is excluded, at least
   30 anonymous cases, and at least five Finnish and five English cases.
   These booleans are operator **attestations**: the program cannot perform
   legal review.
3. **Freeze SmartPloy predictions** before the human reviewers start, in
   \`smartploy.human-relevance.predictions.v1\`. Pin the complete 40-character
   model/code commit SHA, timestamp and the per-case **recommended** or
   **broader** lane. All predictions must explicitly set
   \`qualification_verified: false\`; the search match is *not* a skill,
   degree, legal eligibility or employment outcome verdict.
4. Have **two independent reviewers** label relevance as **relevant**,
   **related**, **unrelated**, or **insufficient**. Reviewers assess the
   original separately stored, approved job/target context without seeing
   SmartPloy's predicted lane or the other reviewer's label. Their separate
   files contain only case IDs and categories. The runner requires
   \`blind_to_predictions: true\`, a reviewer self-attestation, but cannot
   independently prove blindness or reviewer identity.
5. If any labels differ, a **third, distinct adjudicator** resolves exactly
   those cases without changing the raw reviewers' agreement. A missing or
   incomplete adjudication returns code **3**, lists only anonymous case
   IDs, and deliberately emits **no** precision/recall figures.
6. After adjudication, use the offline evaluator for anonymized aggregate
   counts, raw reviewer agreement, Cohen's kappa, per-slice metrics, and
   conservative precision-at-recommended and recall-of-relevant **within
   this particular labeled sample**. Do not promote these figures to
   generalized precision, hiring probability or verified qualifications.
7. Review and preregister an acceptable error budget on a separate withheld
   validation set; track recruiting field coverage, reviewer disagreements
   and failure analysis. SP-14 stays open until real approved data, actual
   independent reviewer evidence and withheld evaluation exist.

## Safe CLI and contracts

From repository root, default synthetic-only demonstration:

~~~bash
python -m scripts.evaluate_human_relevance
python -m scripts.evaluate_human_relevance --no-adjudication
pytest -q tests/test_human_relevance_evaluation.py
~~~

The demonstration's five JSON documents live in
\`tests/fixtures/human_relevance/\`: \`set.json\`, \`predictions.json\`,
\`review-a.json\`, \`review-b.json\`, \`adjudication.json\`.

For privately approved source samples, keep the five files **outside the
repository** and pass explicit paths:

~~~bash
(
  set -Eeuo pipefail
  umask 077
  python -m scripts.evaluate_human_relevance \
    --set /private/approved/set.json \
    --predictions /private/approved/predictions.json \
    --review-a /private/approved/review-a.json \
    --review-b /private/approved/review-b.json \
    --adjudication /private/approved/adjudication.json \
    > /private/approved/aggregate-report.json
)
~~~

Don't paste or commit the private review files, their parent directories, or
underlying job descriptions. The evaluator accepts only strict schemas and
bounded (256 KiB) nonsymlink local files; inputs have no free-text notes,
employer URLs or applicant fields. It does no I/O besides reading the
specified JSON files and printing one aggregate JSON report. On invalid data,
errors include only a fixed contract and error *type*, never untrusted input.

Exit codes: **0** = reviewed sample complete; **3** = disagreement awaits
adjudication (no metrics); **2** = malformed, oversized or unsafe evidence.

## Metric interpretation

The conservative \`precision_at_recommended_in_reviewed_sample\` is the
fraction of all recommended cases explicitly adjudicated **relevant**.
A \`related\`, \`unrelated\`, or \`insufficient\` case does not count as a
positive. \`recall_of_relevant_in_reviewed_sample\` measures the fraction of
all explicitly relevant cases appearing in the recommended lane. If either
denominator is zero, the rate is **null**, never 100% by default.

The report separately counts unrelated cases wrongly recommended, insufficient
evidence recommended and related jobs shown in the broader lane. Agreement
is measured from the *original* two reviewers, not the third adjudicator.
Small real-sample slice outputs (under five observations) are suppressed.
The anonymized case IDs for unresolved disagreements are intended for
private adjudication only.

**Never interpret any metric here as real employer eligibility or hiring
outcome evidence.** Actual permission review, live website/browser acceptance
(#91), the employer application pilot (SP-16) and source commission (#99)
remain separate gates. The current ObumAI model endpoint is not used or
authorized by this evaluator.

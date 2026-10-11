# Fit Score and Priority Score

Smartploy keeps two different scores.

## Fit Score

Fit answers: **how well does approved candidate evidence match this role?**

Only approved profile facts participate. Unapproved notes are invisible.

Components are reweighted when a posting does not provide a field:

- mandatory requirements: 35
- preferred requirements: 10
- known skill overlap: 20
- language: 10
- seniority: 8
- location: 5
- work mode: 4
- education/domain: 4
- evidence quality: 4

Mandatory and preferred requirements are never collapsed into one category. Every result returns
matched evidence IDs plus mandatory/preferred gaps.

## Evidence-bound degree and skill safeguards

A score is **not** an employer's eligibility or a verified diploma check.
Candidate evidence must first be explicitly approved; raw uploads and
unapproved facts never count as confirmed career evidence.

- Skill aliases use complete normalized word/phrase boundaries, not raw
  substrings: `NoSQL` is **not** evidence of `SQL` and `pythonic` is not
  evidence of `Python`. Explicit punctuation variants such as `Power-BI`
  remain recognizable.
- A stated degree-level requirement such as *Master's in Data Science* is
  supported only by an **approved education fact** explicitly containing the
  same degree level and sufficiently matching the stated subject. A Bachelor
  in that subject plus unrelated experience or an unrelated MSc does not
  satisfy a Master's subject requirement.
- Approved candidate facts are still **self/owner-approved**, not externally
  verified diplomas, licenses, work authorization or employer decisions.
  Ambiguous degrees, equivalence clauses, Finnish degree classifications,
  career changes and regulated occupations require a manual requirement
  review. Conservative gaps should not be automatically overridden.
- Mandatory gaps continue to block the automatic *draft-preparation*
  recommendation; no score ever authorizes an employer submission.

The safeguards use deterministic local comparisons; no external LLM,
credential service or private data forwarding is introduced.

## Priority Score

Priority answers: **how worthwhile is it to act on this job now?**

- Fit: 65
- freshness: 15
- deadline urgency: 8
- source confidence: 5
- career alignment: 5
- application effort: 2

Freshness changes Priority, not Fit.

## Queues

- exceptional: Fit >= 90 and Priority >= 90, no mandatory gaps
- auto_prepare: Fit >= 82 and Priority >= 82, no mandatory gaps
- review: Fit/Priority >= 72 or an otherwise strong role with a mandatory gap
- possible: Fit >= 60
- low: below 60

A mandatory gap prevents automatic preparation even when other evidence is strong.

## AI boundary

Smartploy owns these deterministic scores. ObumAI may explain a score or help interpret ambiguous
requirements, but it does not decide that an unverified candidate claim is true.

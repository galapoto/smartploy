# Application draft preparation

Smartploy can automatically prepare application drafts for high-confidence jobs without submitting an application.

## Default gate

A job is eligible when:

- Fit Score >= 82;
- Priority Score >= 82;
- there are no mandatory requirement gaps;
- the job is still current;
- Smartploy has approved candidate evidence.

This corresponds to the `exceptional` and `auto_prepare` queues.

## Immutable package identity

Package identity is derived from:

- the canonical job key;
- an application-relevant normalized job-content snapshot;
- the approved Smartploy profile-evidence snapshot;
- the package contract version.

Discovery timestamps are excluded. A job becoming an hour older does not create a duplicate package.

## ObumAI

Smartploy submits action `application_package_v1` through the ObumAI durable text-job API.

The requested draft schema contains:

- fit summary;
- CV tailoring plan;
- cover letter;
- application answers;
- gap framing;
- risks;
- review checklist.

Candidate claims must cite approved Smartploy evidence fact IDs. The package explicitly grants no browser,
upload, send, or final-submit authority.

## Completion truth

Creating an Obum job only means queued work exists. Smartploy stores that as `queued`.

Smartploy marks a draft complete only when ObumAI returns durable `state=completed` and its
`output_text` parses as `smartploy.application.draft.v1`.

If ObumAI completes with invalid or wrong-schema JSON, Smartploy records `completed_unparsed` and keeps
the raw output for human review. It does not fabricate a structured success.

## Operator workers

Queue eligible jobs:

```bash
python scripts/prepare_eligible.py
```

Refresh queued/running package states:

```bash
python scripts/refresh_preparations.py
```

These are safe to schedule. Deterministic package/request identities prevent duplicate preparation jobs for
unchanged job/profile evidence.

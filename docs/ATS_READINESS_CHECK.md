# Public ATS worker readiness — no-secret operator report

The read-only worker diagnostic `scripts/check_ats_readiness.py` summarizes
configured public ATS sources, their persistent scheduler tasks, source poll
health, and overall active job-record count without printing environment
variables, database credentials, CV text, applicant facts or job descriptions.

## Why this is separate from Docker health

A Docker-healthy worker means that its foreground process and database
connection are alive. It does not prove that external vacancies were fetched,
parsed, stored, or displayed to a signed-in user.

To test whether the five-source Finnish employer pilot is actually ingesting
vacancies, run **inside the existing SmartPloy worker container**:

```bash
sudo docker exec smartploy-worker-1 python scripts/check_ats_readiness.py
```

Optional strict checks:

```bash
sudo docker exec smartploy-worker-1 python scripts/check_ats_readiness.py --require-healthy
sudo docker exec smartploy-worker-1 python scripts/check_ats_readiness.py --require-jobs
```

Each source reports its persistent task state (`healthy`, `failed`,
`awaiting_first_poll`, etc.), last completion and success times, Finnish
matching postings, upstream total, excluded locations, and failure counts.

The aggregate `last_finnish_matching_postings_sum` is a **sum of observed
source snapshots**, not necessarily unique current jobs. The separate
`active_jobs_all_sources` includes manual imports and other sources. A
healthy zero result must never be reported as an error or as successful job
discovery.

The CLI runs no polls, writes nothing to PostgreSQL, and has no outward HTTP
calls. The underlying source adapter still controls rate limits, permitted
hosts, source policy and retirement.

### Reading common results

- `task_not_registered`: worker has not registered this configured source.
  Inspect worker restart/configuration and task startup.
- `awaiting_first_poll`: task exists but no completed run is recorded.
  Allow a normal polling interval; inspect worker logs if persistent.
- `poll_failed`: scheduling/connector failure. Review bounded recent worker
  output on the host and the provider's official API availability.
- `healthy_zero_matching_jobs`: successful complete poll, but no currently
  matching Finnish locations. Do not fabricate a job count.
- `healthy_with_matching_jobs`: actual observed Finnish vacancies available;
  verify app job listing and authenticated CV/profile.
- `degraded`: one or more records were blocked; source lifecycle may not
  be fully updated.

A production release must still separately pass preflight, image-provenance,
health, live acceptance and online release-evidence checks. This diagnostic
does not automatically enable source feeds, ObumAI or employer submission.

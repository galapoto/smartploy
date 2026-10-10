# Smartploy

Smartploy is a standalone job-intelligence and application orchestration product for Finland, powered by ObumAI.

Smartploy discovers and normalizes jobs, deduplicates repeated listings, tracks freshness and source
health, ranks opportunities, prepares application work and maintains the application pipeline. ObumAI
supplies bounded reasoning and later controlled execution through a versioned API boundary.

## Repository separation

Smartploy is **not** an ObumAI submodule.

- Smartploy owns job sources, job data, ranking, profile/application state and product UX.
- ObumAI owns reusable AI reasoning/execution capabilities and consequential-action controls.
- Smartploy does not import `obumellm` and does not share ObumAI's database.
- If ObumAI is unavailable, Smartploy's discovered jobs remain available.

## Current capability

- Smartploy-native job/source domain;
- raw source evidence hashing;
- canonical URLs and cross-source deduplication;
- first-seen / last-seen / posted / verified freshness;
- saved hard filters;
- PostgreSQL durable repository plus in-memory development mode;
- durable source-health state;
- authorized/configured Kuntarekry RSS/XML parser and worker;
- FastAPI job/source-health service;
- ObumAI durable-job client using deterministic request IDs;
- fail-closed separation between AI reasoning and external application actions;
- approved-evidence Fit/Priority scoring;
- immutable application-draft packages for eligible 82%+ jobs;
- ObumAI-backed CV-tailoring/cover-letter/application-answer draft contract;
- duplicate-safe preparation queue and refresh workers;
- auditable application CRM with append-only preparation events;
- dashboard/summary APIs that keep prepared vs actually submitted distinct.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn smartploy.api:app --reload --port 8090
```

Without `SMARTPLOY_DATABASE_URL`, Smartploy uses in-memory development storage.

For PostgreSQL:

```bash
export SMARTPLOY_DATABASE_URL='postgresql://smartploy:...@127.0.0.1:5432/smartploy'
python scripts/migrate.py
uvicorn smartploy.api:app --port 8090
```

Run one authorized Kuntarekry feed poll after provisioning `KUNTAREKRY_FEED_URL`:

```bash
python scripts/poll_kuntarekry.py
```

Smartploy does not automate Kuntarekry login or invent a public feed URL.

## Verification

```bash
python -m compileall smartploy scripts tests
pytest -q
ruff check smartploy scripts tests
```

CI additionally starts a real PostgreSQL service and tests persistence/migrations.

## ObumAI

Set `OBUMAI_BASE_URL` to enable AI reasoning. Authentication headers are supplied at runtime through
`OBUMAI_HTTP_HEADERS_JSON`; secrets are never committed.

Current durable product-agent endpoints:

- `POST /api/v1/agent-jobs`
- `GET /api/v1/agent-jobs/{job_id}`
- `GET /api/v1/agent-jobs/{job_id}/events`

See `docs/ARCHITECTURE.md`, `docs/PERSISTENCE.md`,
`docs/OBUMAI_INTEGRATION.md`, and `docs/SOURCE_STRATEGY.md`.


## Application draft preparation

After PostgreSQL migrations and an approved profile are configured, queue high-confidence jobs:

```bash
python scripts/prepare_eligible.py
```

Refresh queued/running ObumAI draft jobs:

```bash
python scripts/refresh_preparations.py
```

The default automatic gate is Fit >= 82, Priority >= 82, no mandatory gaps, and a current job source.
This creates drafts only. Smartploy does not upload or submit applications in this workflow.

See `docs/APPLICATION_PREPARATION.md`.


## Application CRM and dashboard

Read application pipeline state:

```text
GET /api/v1/applications
GET /api/v1/applications/summary
GET /api/v1/applications/{application_id}
GET /api/v1/applications/{application_id}/events
GET /api/v1/dashboard
```

Backfill CRM records from existing preparation packages after migration:

```bash
python scripts/sync_applications.py
```

A prepared application is never counted as submitted. Submission/outcome states are reserved for future
verified ObumAI confirmation and communication integrations.

See `docs/APPLICATION_CRM.md`.

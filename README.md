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
- authorized/configured Kuntarekry RSS/XML parser and worker;\n- credential-gated Job Market Finland P67 v2 national job-source adapter;\n- read-only SmartRecruiters and Lever direct-employer ATS connectors;\n- PostgreSQL-leased continuous source/application worker;
- FastAPI job/source-health service;
- approved-evidence Fit/Priority scoring;
- immutable application-draft packages for eligible high-confidence jobs;
- ObumAI-backed CV-tailoring/cover-letter/application-answer draft contract;
- auditable application CRM with append-only preparation events;
- dashboard/summary APIs that keep prepared vs actually submitted distinct;
- responsive React web dashboard with heatmap/percentage ranking and Public/Private/Unknown filters.

## Run locally

Backend:

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn smartploy.api:app --reload --port 8090
~~~

Web:

~~~bash
cd web
npm install
npm run dev
~~~

Vite proxies /api and /healthz to the local FastAPI service.

Without SMARTPLOY_DATABASE_URL, Smartploy uses in-memory development storage.

For PostgreSQL:

~~~bash
export SMARTPLOY_DATABASE_URL='postgresql://smartploy:...@127.0.0.1:5432/smartploy'
python scripts/migrate.py
uvicorn smartploy.api:app --port 8090
~~~

Run one authorized Kuntarekry feed poll after provisioning KUNTAREKRY_FEED_URL:

~~~bash
python scripts/poll_kuntarekry.py
~~~

Smartploy does not automate Kuntarekry login or invent a public feed URL.

## Verification

Backend:

~~~bash
python -m compileall smartploy scripts tests
pytest -q
ruff check smartploy scripts tests
~~~

Web:

~~~bash
cd web
npm run test
npm run build
~~~

CI starts PostgreSQL 17 and runs both backend and frontend gates.

## Application preparation

Queue high-confidence jobs:

~~~bash
python scripts/prepare_eligible.py
~~~

Refresh queued/running ObumAI draft jobs:

~~~bash
python scripts/refresh_preparations.py
~~~

Preparation creates drafts only. Smartploy does not currently upload or submit applications.

## Application CRM

Read pipeline state:

~~~text
GET /api/v1/applications
GET /api/v1/applications/summary
GET /api/v1/applications/{application_id}
GET /api/v1/applications/{application_id}/events
GET /api/v1/dashboard
~~~

A prepared application is never counted as submitted. Submission/outcome states are reserved for future
verified ObumAI confirmation and communication integrations.

## ObumAI

Set OBUMAI_BASE_URL to enable AI reasoning. Authentication headers are supplied at runtime through
OBUMAI_HTTP_HEADERS_JSON; secrets are never committed.

Current durable product-agent endpoints:

- POST /api/v1/agent-jobs
- GET /api/v1/agent-jobs/{job_id}
- GET /api/v1/agent-jobs/{job_id}/events

See docs/ARCHITECTURE.md, docs/PERSISTENCE.md, docs/SCORING.md,
docs/APPLICATION_PREPARATION.md, docs/APPLICATION_CRM.md, docs/WEB.md,
docs/OBUMAI_INTEGRATION.md, and docs/SOURCE_STRATEGY.md.


## Job Market Finland national source

After KEHA Centre onboarding and receipt of a KIPA subscription key:

~~~bash
export SMARTPLOY_DATABASE_URL='postgresql://...'
export JOBMARKET_FINLAND_API_ENABLED=true
export JOBMARKET_FINLAND_ENVIRONMENT=test
export JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY='...'
python scripts/poll_jobmarket_finland.py
~~~

Use the test environment until KEHA authorises production. Smartploy queries PUBLISHED and ARCHIVED
incrementally and never treats absence from a partial query as deletion.

Retrieved Job Market Finland postings are currently display/score-only in Smartploy: application
preparation via ObumAI is blocked by default because the API terms restrict third-party forwarding.


## Direct employer ATS polling

Create a local registry from `config/public_ats_sources.example.json`, then:

~~~bash
export SMARTPLOY_DATABASE_URL='postgresql://...'
export SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=config/public_ats_sources.json
python scripts/poll_public_ats.py
~~~

The current direct ATS connectors read public SmartRecruiters/Lever postings only. They do not call
application-submission APIs. Missing postings are retired only after a complete successful tenant
snapshot.


## Continuous worker

After applying migrations and configuring sources:

~~~bash
python scripts/migrate.py
python scripts/source_worker.py --once
python scripts/source_worker.py
~~~

The worker persists task cadence and leases in PostgreSQL. Multiple worker processes may run, but a
non-expired task lease can be owned by only one worker at a time. Failed tasks back off exponentially
up to the configured maximum while unrelated due tasks continue to run.

The worker schedules only configured sources. ObumAI preparation/refresh tasks appear only when
OBUMAI_BASE_URL is configured, and they remain draft-only: final external application actions are not
authorized.

For an always-on Ubuntu/OVH deployment, see docs/CONTINUOUS_WORKER.md and
deploy/systemd/smartploy-source-worker.service.example.

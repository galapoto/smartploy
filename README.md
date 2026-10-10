# Smartploy

Smartploy is a standalone job-intelligence and application orchestration product for Finland, powered by ObumAI.

Smartploy continuously discovers and normalizes jobs, deduplicates repeated listings, tracks freshness,
ranks opportunities, prepares application work and maintains the application pipeline. ObumAI supplies
bounded reasoning and later controlled execution through a versioned API boundary.

## Repository separation

Smartploy is **not** an ObumAI submodule.

- Smartploy owns job sources, job data, ranking, profile/application state and product UX.
- ObumAI owns reusable AI reasoning/execution capabilities and consequential-action controls.
- Smartploy does not import `obumellm` and does not share ObumAI's database.
- If ObumAI is unavailable, Smartploy's discovered jobs remain available.

## Current bootstrap capability

- source policy and acquisition-mode validation;
- raw source evidence hashing;
- canonical URLs;
- Smartploy-native `JobRecord`;
- cross-source deduplication;
- first-seen / last-seen / posted / verified freshness;
- saved hard filters;
- closed-job handling;
- FastAPI service;
- ObumAI durable-job client using deterministic request IDs;
- fail-closed separation between AI reasoning and external application actions.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn smartploy.api:app --reload --port 8090
```

Then open `http://127.0.0.1:8090/docs`.

Run verification:

```bash
python -m compileall smartploy tests
pytest -q
ruff check smartploy tests
```

## ObumAI

Set `OBUMAI_BASE_URL` to enable AI reasoning. Authentication headers are supplied at runtime through
`OBUMAI_HTTP_HEADERS_JSON`; secrets are never committed.

Smartploy currently targets ObumAI's durable product-agent endpoints:

- `POST /api/v1/agent-jobs`
- `GET /api/v1/agent-jobs/{job_id}`
- `GET /api/v1/agent-jobs/{job_id}/events`

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/OBUMAI_INTEGRATION.md](docs/OBUMAI_INTEGRATION.md), and
[docs/SOURCE_STRATEGY.md](docs/SOURCE_STRATEGY.md).

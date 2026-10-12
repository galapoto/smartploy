# Smartploy web dashboard

The Smartploy web client lives in web/ and consumes only the Smartploy FastAPI service.

## Development

Start the API:

~~~bash
uvicorn smartploy.api:app --reload --port 8090
~~~

Then:

~~~bash
cd web
npm install
npm run dev
~~~

Vite proxies /api and /healthz to 127.0.0.1:8090.

## Production

The browser must never receive ObumAI service credentials.

Recommended routing:

~~~text
https://smartploy.example/
  /                  -> static web build
  /api/*             -> Smartploy FastAPI
  /healthz           -> Smartploy FastAPI
~~~

If web and API cannot share an origin, build with VITE_SMARTPLOY_API_BASE set to the public Smartploy API origin and configure CORS separately.

## Truth boundary

The interface deliberately distinguishes application preparation, review, and actual submitted applications.

The Actually submitted metric is read only from the CRM actually_submitted value. A completed draft package never increments it.

The current web slice has no final-submit control.


## Continuous worker visibility

The dashboard shows a read-only Continuous worker card when PostgreSQL worker scheduling is configured.

It displays:
- registered task count;
- running lease state without exposing the lease-owner identifier;
- last result;
- next run;
- cadence;
- consecutive failure count;
- bounded last error.

If PostgreSQL is not configured, the card truthfully reports the worker as unconfigured. If the API can
run but the worker schema is unavailable, the dashboard reports worker status unavailable without
pretending the API itself is down.

The browser has no endpoint to claim, retry, reschedule or trigger worker tasks.


## ObumAI product navigation

SmartPloy is a standalone ObumAI product at `https://smartploy.obumai.com`.

Its header includes a fixed same-tab return link to:

`https://app.obumai.com/`

The link contains no token, query string or cross-product session material. Authentication federation is a
server-side identity concern and must not be encoded into product-navigation URLs.


## Honest listing dates and source-observation freshness

General and Personalized job cards now display **two separate timestamps**:

- **Posted** when the source provides a parseable genuine `posted_at`; otherwise **First discovered** from SmartPloy's `first_seen_at`; if neither is trustworthy, **Publication date unknown**. No source modification timestamp is treated as a posting date.
- **Last observed** from `last_seen_at`, meaning the most recent SmartPloy observation of the particular listing. This is not an independent check that an employer is still accepting applications.

If `last_seen_at` is missing, invalid, implausibly future-dated, or at least 72 hours old, the card conservatively asks the user to check the original employer posting. These warnings appear in both browsing modes, do not include account/profile data, and do **not** hide jobs, create fit scores in General mode, or claim that a job has been removed. They also do not automatically authorize any external application or AI processing.

The source's overall worker health and freshness are a **different** signal: the optional read-only `check_ats_readiness.py --require-fresh-hours` evaluates the last successful source poll, not whether one job posting was recently observed. Operators must review source cadence and perform real browser/source acceptance separately; synthetic freshness tests are not proof of live hiring availability.

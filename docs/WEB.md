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


## Session-bound private workspace refresh

SmartPloy's frontend requires the backend's stable session user/profile identity.
An email address by itself is **never** sufficient evidence that two views
belong to the same account; the backend remains authoritative for tenant
isolation. The frontend checks the session **before** making any tenant-scoped
workspace reads, verifies it again after essential search/dashboard results
and again before publishing optional private CV, facts and application-history
results. A mismatch is **fail-closed**: the page clears old workspace data
and asks for a reload rather than mixing responses across account identities.

When an authenticated account changes during a live SPA session, SmartPloy
also returns to the dashboard, clears unsaved text-entry state and the prior
CV preview, and remounts its application editor using the new server identity.
This prevents locally cached, unsaved CV/cover-letter text and browser packet
state from being presented in the new account's application editor. Old
background response generations cannot repopulate the new workspace.

Browser and unit tests use synthetic two-account identities (including the
same email under distinct user IDs) and fictional CV/letter text. This is
**client-side defense in depth**, not a substitute for server tenant
authorization or [real, approved two-account browser acceptance
(#91)](https://github.com/galapoto/smartploy/issues/91). Authenticated
mutating requests, login-cookie changes outside the SPA and real backend
permission boundaries require separate review. No additional employer
application or external AI permissions are granted.

## Disabled-account and OIDC session status enforcement

For authenticated OIDC, Cloudflare or hybrid traffic, SmartPloy now resolves
the stable server-side user identity and checks the authoritative account's
`active` status **on every protected HTTP request**, including read-only
catalog and profile endpoints. A disabled account receives a no-store
`403 account_disabled` response, even when its browser has a previously
valid OIDC cookie or a still-valid Cloudflare assertion. An unavailable
identity database fails closed with a no-store `503 identity_unavailable`;
it does not restore cached account privileges.

OIDC sessions also bind to their originally issued server user ID. If a
verified provider identity is subsequently relinked to a different SmartPloy
user, the old session returns `401 session_identity_changed`, rather than
silently opening a different account. The affected OIDC cookie is revoked
server-side. A cookie observed for a disabled user is likewise revoked;
re-enabling that user requires a fresh sign-in. The OIDC callback will not
issue a new session for an already-disabled account. Logout and the public
health endpoint remain accessible during account suspension.

This is **request-boundary** enforcement; it does not interrupt an operation
that began before disabling an account, and it does not enable client-driven
role grants or modify Cloudflare Access or provider identity policy. Account
status must only be changed by an authorized backend administrator; the
public API exposes no account re-enable endpoint. Cloudflare tokens remain
provider-managed, so a new valid assertion is still checked against status
on every request. Full authenticated A1–A7 acceptance, including real
account switching, is tracked separately in
[#91](https://github.com/galapoto/smartploy/issues/91).

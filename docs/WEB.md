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

## Search-preference saves across session changes

Changing from Personalized to General search (or editing search criteria)
writes private account preferences and then retrieves matching search results.
The SPA now verifies its stable server-issued user/profile identity **before**
the preferences PUT, **after** the PUT response, and **after** the corresponding
discovery GET. If that identity is different or cannot be re-verified, the
client clears the private workspace and requires a manual retry rather than
showing a previous account's preference/result response. Email equality is
not sufficient to treat two accounts as the same identity. Concurrent
workspace refresh remains suspended during the save.

**Limitations:** This is UI defense in depth, not a server transaction or a
guarantee that a PUT never reached the backend before a session change. The
backend must authorize each mutation and all private reads against the actual
authenticated account, and a user should reload to inspect saved preferences
after changing accounts. Synthetic React and built-Chromium tests cover the
different-user-ID / same-email race; production two-account sign-in and data
isolation acceptance under [SP-10 #91](https://github.com/galapoto/smartploy/issues/91)
is still required. No third-party job applications or external AI sending
become authorized.

## Account-switch safety for private application actions

Private mutations initiated from the main SPA now revalidate the stable
backend-issued session identity before invoking the API and again before
publishing any successful result. The covered actions are CV upload/deletion,
adding/approving/deleting profile facts, adding a manual job and opening a
private application draft. If account verification fails, the SPA invalidates
in-flight read generations, clears private editor fields, selected drafts,
upload controls and busy indicators, and asks the user to reload. Stale
operation errors are not displayed as if they belonged to the new account.
An old action's completion cannot remount another account's application
workspace.

These frontend checks are **not** authorization, transaction isolation,
request cancellation or evidence that the backend reversed a completed
operation. An in-flight upload or mutation may already have reached the server
before session verification failed. The FastAPI access middleware and
profile-specific backend repositories must still enforce server-side
authorization for every endpoint. A browser session switch between
verification and sending a request remains a possible TOCTOU window until
there is stronger backend request binding. Account IDs are never derived from
email, and neither CV text nor submission authority is forwarded externally.

Synthetic Vitest/Chromium checks reproduce a **same-email, different-user-ID**
account change while CV, profile or draft actions are awaiting a response.
They do not count as owner-authenticated live A1–A7 acceptance under
[#91](https://github.com/galapoto/smartploy/issues/91). This implementation is
reviewed separately under [#113](https://github.com/galapoto/smartploy/issues/113)
and depends on prior [PR #112](https://github.com/galapoto/smartploy/pull/112).

## Private user-saved job API — backend foundation

A user-saved job is **not** an ATS feed observation and must not be stored in the
shared discovery table. The new account-scoped `/api/v1/private-jobs` endpoints
create, list (at most 100 per response) and delete private saved opportunities,
identified by a server-generated opaque ID. Requests resolve a trusted
authenticated user's profile; neither supplied profile IDs nor email addresses
can choose the owner of a record. The backend uses a dedicated PostgreSQL
table (migration `014_private_saved_jobs.sql`) or development-memory store.
Responses include `Cache-Control: private, no-store`, and availability and
external actions remain **unverified/unauthorized**.

Private records never enter the global ATS source registry, source-health counts,
public job discovery or personalized match scores. They are useful as private
bookmarks until their full employer-source and matching requirements can be
validated; they must not be counted as currently verified vacancies or
application receipts.

**Rollout boundary:** the current frontend's legacy *Add job* still calls
`POST /api/v1/jobs/ingest`, which is a shared source-ingestion endpoint.
The new private API is a backend foundation, not a completed user-facing
migration. Do not switch the user interface or deploy multi-user OIDC until
the client is rewired to private endpoints and privileged ingestion/source
registration are secured separately. Real two-account user acceptance and
operator-approved release are required. Track
[issue #116](https://github.com/galapoto/smartploy/issues/116) and
[issue #91](https://github.com/galapoto/smartploy/issues/91).

## Operator-only global job ingestion and source writes

Shared employer-source mutations are privileged operations, not jobseeker
features. In any authenticated Cloudflare Access, hybrid, or OIDC deployment,
`POST /api/v1/sources` and `POST /api/v1/jobs/ingest` require an **explicitly
authorized backend-resolved user ID** in `SMARTPLOY_OPERATOR_USER_IDS`.
This is a comma-separated list of at most 16 stable `usr-...` IDs, never
emails, identity-provider roles, HTTP headers or frontend profile fields.

The default is empty: even an authenticated owner **cannot** modify global
sources using the HTTP API without explicit operator approval. Fetch your
own verified `user_id` from `GET /api/v1/session` through the existing
authenticated connection and have an authorized server operator populate
`deploy/personal/env` (mode 0600) before intentionally enabling these
privileges. Production refuses malformed/wildcard/email entries. The
allowlist passes only to the API container; it is not available to the
browser or worker.

The existing private source worker uses direct, independently configured
Python ingestion and continues operating with its preapproved feeds. The
read-only source-health and job search APIs do not require operator roles.
The legacy unauthenticated **development/test-only** mode preserves local
fixture ingestion; production rejects disabled authentication entirely.

These checks protect shared API writes but do not establish full
multi-tenant isolation, live job availability, or authentication recovery.
Do not merge or deploy a new OIDC public access policy until source/operator
permissions, account-private saved jobs (#116), verified sign-in (#91),
and release evidence are accepted. No automatic employer submission, new
ATS activation, or external AI forwarding is authorized by this feature.

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

## Same-origin protection for OIDC cookie mutations

SmartPloy's first-party OIDC session uses an HTTP-only host-only
`__Host-smartploy_session` cookie with `Secure` and `SameSite=Lax`.
These cookie flags do **not** by themselves protect an account-changing
request initiated by another same-site subdomain. For protected
`/api/*` POST/PUT/PATCH/DELETE actions authenticated with an active
OIDC session, the backend therefore requires an exact `Origin` matching
the configured HTTPS `SMARTPLOY_PUBLIC_ORIGIN`. Requests with missing,
opaque, sibling, HTTP or otherwise different origins are denied with a
no-store `403 csrf_origin_denied`. Conflicting `Sec-Fetch-Site`
headers are denied too. The server never trusts caller-supplied `Host`
or `X-Forwarded-Proto` to decide the allowed origin.

The regular browser application uses same-origin fetch and supplies the
required Origin automatically. An API script that deliberately uses a
browser session cookie must explicitly send the correct Origin; only
non-cookie Cloudflare Access bearer assertion flows retain their
existing authorization rules. The guard does not grant source-operation
privileges, change operator IDs, permit cross-user data access or
authorize external employer submissions.

**Scope:** This protects authenticated **API mutations**, not all possible
browser CSRF surfaces. Public OIDC callback and logout redirects keep
their existing provider flow; anti-forgery for logout navigation requires
a separate design before public multi-user launch. This is code-only
synthetic test evidence, not proof of production OIDC or Cloudflare
configuration. The account-suspension middleware change in
[PR #121](https://github.com/galapoto/smartploy/pull/121) must be
independently reviewed and integrated first. Owner-approved real A1–A7
browser verification under issue #91 is still required.

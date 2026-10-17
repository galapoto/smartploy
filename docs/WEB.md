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

## Confirmation-first OIDC sign-out

The SmartPloy Settings page shows **Sign out securely** when the active
workspace uses a first-party OIDC application session. This link opens
`GET /auth/logout`, an inert no-store confirmation page. It never revokes
a cookie or contacts the identity provider merely because a user or external
website navigated to the URL.

The confirmation form uses `POST /auth/logout`, which requires an
`Origin` exactly matching the configured HTTPS
`SMARTPLOY_PUBLIC_ORIGIN` and rejects conflicting `Sec-Fetch-Site`.
A successful explicit POST revokes the server-side SmartPloy session
**before** initiating provider end-session and clears the host-only browser
cookie. Cross-site POSTs are denied with `403 csrf_origin_denied`, with
no user-data or session changes. The public `GET /auth/logged-out` page
is also inert: merely visiting it cannot revoke a session or clear cookies.

If the session store cannot confirm revocation, the server returns a
no-store 503 page, clears the browser cookie, and **does not claim**
server revocation or provider logout. A provider redirect failure after a
successful revocation falls back to the neutral logged-out information
page; this does not prove the identity provider itself signed out.
The confirmation POST can still work when the application account has
been administratively disabled, because the logout route deliberately
does not require an active account binding.

Logout safety is specifically a first-party **browser OIDC session** feature.
It does not change Cloudflare Access owner policy or independently sign a
user out of other ObumAI tools. Exact-head CI and signed-in owner/browser
acceptance remain separate requirements before any public OIDC cutover.
See [issue #124](https://github.com/galapoto/smartploy/issues/124)
and [PR #123](https://github.com/galapoto/smartploy/pull/123).

## Public health privacy boundary

`GET /healthz` is intentionally available without a login for load balancers,
container health checks and the pinned OVH release evidence contract. It
returns only the stable, bounded status needed for those checks: `ok`,
service, public origin, storage mode/readiness, worker readiness and task count,
approved-edge Access posture, optional ObumAI availability, and the explicit
`external_actions_authorized=false` flag.

**It never returns** a candidate's profile ID, fact counts/types, CV data,
private applications, raw worker/database errors, task metadata or
internal authentication configuration. Public health responses have
`Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
Authenticated users can use `/api/v1/profile/status` and the dashboard or
`/api/v1/worker/tasks` for their permitted diagnostics; those URLs remain
under the configured authentication middleware. Public health is not a
substitute for real login or job availability tests.

The retained status keys deliberately preserve
`smartploy.live_acceptance.validate_origin_health` and the operator's
`deploy/personal/scripts/release-evidence.sh` read-only contract. The
release still requires separate backup, provenance, TLS/Cloudflare and
signed-in A1–A7 checks. No source activation, identity cutover or employer
application sending is authorized by this change.

## Private saved-jobs view (dependent frontend)
The **Find jobs** page now includes **Your saved opportunities** in a separate
private panel. The Add/Save job modal sends a validated bookmark to
`POST /api/v1/private-jobs` rather than the privileged shared
`/api/v1/jobs/ingest` endpoint. Saved entries can be deleted from their
own account and optionally opened at the supplied employer link. They do
not add to the number of current public listings, source-health counts,
personalized match percentages, draft packages or application receipts.
Employer availability remains unverified.

This frontend PR depends on the backend private-job API in [PR
#117](https://github.com/galapoto/smartploy/pull/117) and the preceding UI
account-switch protections in [PR #115](https://github.com/galapoto/smartploy/pull/115).
Its synthetic browser test switches same-email accounts and asserts saved
bookmarks never cross the account boundary. This is not real SSO acceptance.
Merge all dependencies and verify the integrated **exact main SHA** with
separate CI before considering an operator-reviewed production release.
Privileged shared source endpoints remain a distinct authorization task
under [#116](https://github.com/galapoto/smartploy/issues/116).

## Reproducible npm installs (SP-11)

The React/browser dependency graph is pinned in `web/package-lock.json` (npm lockfile v3), generated with **npm 10.9.2** on Node 22. All GitHub Actions web and Chromium jobs and the production web Docker image run `npm ci --no-audit --no-fund` instead of resolving floating semver ranges via `npm install`. An explicitly mismatched manifest/lockfile must make the CI negative-control test fail; `npm ci` must not edit either tracked package file.

To reproduce locally with Node 22: `npm install --global npm@10.9.2`, then `cd web && npm ci --no-audit --no-fund && npm run test && npm run build`. Only update the lockfile in a separate reviewed dependency-update PR, inspect its resolved package versions and vulnerability/license inventory, rerun the complete React/Chromium/Docker/backup CI, and pin the resulting NEW Git tree before any approved release. `npm audit` evidence does not substitute for application tests or independent source review.

## Cloudflare Access browser-origin guard (review candidate)

A verified Cloudflare Access assertion proves who the requester is, not that a
state-changing browser request came from SmartPloy's own page. In Cloudflare-only
mode and in hybrid mode without a valid OIDC cookie, the app now rejects API
`POST`/`PUT`/`PATCH`/`DELETE` requests carrying a foreign/opaque
`Origin` or suspicious `Sec-Fetch-Site` (`same-site` or `cross-site`).
The origin is compared with the configured exact `SMARTPLOY_PUBLIC_ORIGIN`,
not with user-controlled Host or proxy headers. The production Compose file
supplies the canonical SmartPloy origin.

OIDC cookie mutations **still require** an explicit same-origin `Origin`;
the Cloudflare assertion path intentionally preserves *originless* authenticated
machine/API clients until a separate machine-authentication contract can be
introduced. This means this Access-path change is **defense in depth, not a
complete CSRF guarantee** for legacy browsers/clients sending neither header.
Keep Cloudflare Access edge policy, operator-only ingestion authorization and
per-mutation account binding enabled. Do not claim first-party identity cutover
or live browser acceptance from these synthetic tests.

## Invalid/revoked OIDC cookies in hybrid authentication (review-only)

In `hybrid` mode, a **valid** OIDC cookie takes precedence over a Cloudflare
Access assertion. Previously, an **unknown, expired or revoked** OIDC cookie
could instead fall through to the Cloudflare identity on that same protected
request. If their backend identities differed, a stale session could
unexpectedly open the other person's workspace or mutate it through older
API clients without an account precondition header.

The middleware now responds `401 session_expired` with a safe
`/auth/login` pointer and expires the invalid host-only cookie **before**
considering any Cloudflare identity. It does not resolve or mutate private
tenant state on that request. This also applies in OIDC-only mode. A request
with **no OIDC cookie** can still explicitly follow the configured Cloudflare
fallback, and an **unavailable session store** still returns `503` without
clearing the cookie. Same-email synthetic users, revoked/expired/unknown
cookie variants, safe GET/POST behavior, and the subsequent cookie-free
fallback are covered by regression tests.

This avoids one specific silent account downgrade; it does not prevent
ordinary fallback on an already cookie-free browser, replace the source
of user authentication, or count as real two-account browser acceptance.
Do not disable Cloudflare Access or enable first-party production OIDC
based on these tests alone.

## Application Studio private read-publication boundary (review-only)

The parent React workspace already verifies a stable server user before and
after loading its main dashboard and before/after account-bound mutations.
The child Application Studio had a narrower gap: its standalone **Refresh
drafts** request and selected draft's receipt/handoff reads could complete
after a browser login switch without independently verifying that the
responding account matched the parent's captured user. Backend GETs still
enforce the authenticated tenant; the risk was publishing an unexpected
account's read response in a previously mounted editor (not bypassing
backend tenant authorization).

The editor now checks `getSession()` on both sides of its private draft GET
and on both sides of the selected-draft receipt/handoff GETs, matching the
server-issued `user_id` **and** `auth_source` against the parent account.
Missing/failed or changed identity invalidates pending reads, clears local
CV and letter text, AI suggestions, browser packet and receipt state and
blocks the editor with an account-verification warning. A second refresh
cannot be overwritten by an older completed refresh. The normal same-user
path preserves unsaved edits when the selected draft revision is unchanged.

Synthetic React regression checks exercise real account A/B values with the
same email, identity changes before and during manual refresh, identity
lookup errors, overlapping refreshes and delayed receipt/handoff reads.
They do **not** replace live A1–A7 browser acceptance or prove that another
device/browser's session changed. Server authorization, account-precondition
headers on mutations, and the explicit per-application employer-submit
consent remain required. This candidate is still a draft; no production
auth/ingress change or employer action is authorized.

## Application Studio delayed private-action responses (review-only)

In the same Application Studio component, authenticated reads were guarded
but mutation responses (draft save/delete, suggested wording, account-local
browser handoff packet, browser-observed receipt import and manual
application-status updates) could still update React after a browser account
switch. Each backend mutation already has a server-checked expected-user
precondition; this was a **client-side stale-response publication** issue,
not evidence of cross-tenant server authorization bypass.

These editor actions now verify the server-issued stable user ID and
authentication source **before dispatching** and **after completing**, including
when the underlying API returns a failed request. A mismatch or unverified
session clears the old private draft/AI/receipt/handoff UI and blocks the
editor. Private packets are not shown or copied when a mismatch is discovered
before the clipboard write. The result of an in-flight clipboard write is
also followed by identity verification before showing a copy-success message.
A clipboard write that finishes *during* an external sign-in change cannot
be retroactively retracted; users should still treat manually copied packets
as sensitive. Applying a local AI suggestion also verifies the session after
the user's confirmation.

A successful backend mutation may already have been committed when the
browser account changes. UI protection does **not** roll it back. Application
sending is still external and manual; browser-observed confirmations remain
unverified and no employer submission is authorized by this change.
Only synthetic tests and the exact candidate CI run establish code-level
behavior. Independent review, merge, release and real authenticated two-user
A1-A7 acceptance remain required.

## Application Studio per-draft delayed results (review-only)

Private account verification does not by itself prevent mixing *different job
drafts belonging to the same account*. Before this change a user could click
from draft A to draft B while a save, local AI generation, handoff packet,
browser-observed receipt import, manual-applied status update or deletion was
pending. The late A result might then reselect A, show A's sensitive packet in
B's editor, or present A's AI text/receipt as if it belonged to B.

The editor now captures a **workspace ID + revision + selection epoch** for
every private action and checks it both after the identity preflight and after
the action. Switching drafts immediately invalidates the previous epoch;
switching away and back does not revive stale results. Account-bound mutation
authorization and explicit user confirmation remain unchanged. The optional
clipboard is never written with an old draft's packet after a *detected*
selection change, including if the packet generation finished later. Manual
AI proposal insertion rechecks the same draft context after its session
lookup, before changing CV/letter fields.

A successful backend save/delete/status mutation cannot be undone by
discarding its stale response. If the user switches while a mutation runs,
the current draft remains visible without an unrelated result; use Refresh
drafts to reconcile old draft state. This does **not** submit applications
to employers and does not independently verify browser receipts. Deterministic
synthetic React tests cover both same-account drafts, including late AI,
packet, receipt, save, delete, reported-applied and AI insertion cases.

## Switching between drafts during pending actions (review-only)

The Application Studio now resets draft-specific busy indicators
(`busy`, `aiBusy`, `handoffBusy`, `receiptBusy`) *before paint* when the
selected workspace or revision changes. It also clears local AI proposals,
CV/letter editor snapshots and any private handoff or receipt preview at this
layout boundary. Previously Job A's slow save/AI/packet/receipt could hold Job
B's controls disabled, or Job A's late `finally` block could erroneously
unlock an unrelated in-flight Job B action.

Each completion now clears its loading flag only if its original
workspace+revision+selection-epoch ticket is still current. Selecting B allows
a new action even when A's request is stuck; late A completion cannot clear
B's active pending flag or publish A content. No network call is silently
canceled or backend mutation rolled back. Synthetic two-draft React tests
exercise overlapping saves and AI suggestions in both completion orders.
This fix is on the **draft review branch only**, not production.

## Safe employer links and nonblocking local-AI availability (review-only)

Employer posting URLs from public ATS listings and private bookmarks are
untrusted data. Browser links only render for absolute HTTP(S) URLs without
embedded credentials, control characters or malformed URL syntax. Invalid
links are displayed as unavailable instead of creating executable,
protocol-relative or unreviewed browser-navigation targets. Application Studio
uses the same single validator. This is defense-in-depth and does **not**
replace server-side source validation or independently verify a vacancy.

The UI now starts the global, non-private local Ollama availability check
concurrently with other reads but resolves it **independently** from the
user's CV, facts, applications and saved jobs. Slow or unavailable local model
status cannot prevent those basic features from becoming visible. The model
result is published only when its original authenticated load generation is
current; a rejected status shows a nonblocking warning. AI generation remains
opt-in and does not send user data or submit employer applications.

The review branch includes deterministic synthetic tests for safe/unsafe links,
profile hydration under a stalled AI endpoint, and superseded account/AI
status responses. Live signed-in two-user acceptance, human review and
operator-approved deployment are still required.

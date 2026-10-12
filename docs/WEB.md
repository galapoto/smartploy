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

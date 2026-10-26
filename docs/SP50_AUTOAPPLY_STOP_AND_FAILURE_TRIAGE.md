# SP50 — Stop-after-current and explicit per-job AutoApply triage

**Date:** 26 October 2026 · **Plan:** SP21 P0-B selected-job application preparation and Agent Zero lifecycle  
**Baseline:** `main@3f0753be94495ebea6251f58a18f460fcbc8e902` (SP49).  
**Scope:** reviewed source and synthetic CI. **No OVH deployment or actual employer submission is claimed.**

## Core defect found after SP49

SP49 made selected AutoApply preparation independent and retryable: one
failure no longer starved the remaining selected jobs. Two gaps remained:

1. After starting a 15-job batch, a user **could not stop** the outstanding
   private-workspace creations without leaving/signing out. There was no
   cooperative stop boundary at the next exact job.
2. The UI treated every failed job alike. A 404 retired job, 409 stale
   document, 422 unapproved profile and 503 temporary worker outage all
   appeared as *Retry*, encouraging repeated attempts when the applicant
   first needed to reselect or review the posting and CV. A later retry of
   a transient failure also cleared an earlier retired-job warning.

## Reuse and original changes

**Original components reused unchanged:** owner-scoped OIDC session,
`runPrivateMutation`, already idempotent original
`/api/v1/jobs/{canonical_key}/application-workspace`, exact canonical job
selection, saved workspaces, durable Agent Zero per-job cases, React
`ApplicationJourney`, private document review queue and existing worker.
The original issuer/middleware, migration, DB, job matcher and independent
employer-final-action claim/permission ledger are not modified.

**New glue only:**

- Extend original `api.ts` Error with read-only HTTP status metadata.
  Existing error message, expected-owner header and login behavior are
  preserved.
- Add a pure, static allowlisted job-failure classifier. Never echo
  raw employer data, candidate details or arbitrary HTTP error text in the
  per-job list. 404/410 are nonretryable missing jobs; 400/409/422 require
  review or refreshing the posting; 408/429/502/503/504 are user-retryable
  *private preparation* problems; other/unknown outcomes require checking
  the workspace before an explicit retry.
- Treat 401/403 as a **batch-wide permission problem**, immediately stop
  before a second job, and display a safe access message. This is not an
  entitlement or an employer submit grant.
- Add a visible **Stop after current job** control. Requests already
  pending may complete, but no later selected job is started. All untouched
  exact keys remain selected, and the user can explicitly continue.
- Preserve the earlier nonretryable job diagnostics through a retry of
  another exact job. Only attempted exact keys update their previous
  outcomes; a successful key is never retried. Do not navigate away from
  the blocked-jobs screen after a successful *subset* retry.
- Guard scope by the signed-in user and current CV digest. Switching
  accounts or replacing the CV while running stops further preparation.
  Both parent and child use a per-run token so old asynchronous `finally`
  cannot release a newer run's lock.
- The status counts distinguish prepared, failed and **not attempted**.
  The Stop action never claims to cancel a request that may already have
  created one private workspace. No background submit or silent retry.

## Tests

- Original API test confirms status 404/409/503 and the same owner header.
- Pure test covers permitted failure categories, safe fixed messages,
  malformed metadata and uncertain network outcomes.
- Real `App` React tests simulate a three-job batch; Stop while job #1
  is awaiting HTTP; assert #2/#3 never POST, #1 finishes once and they
  remain selected; resume explicitly reuses the original workspace API.
- Real `App` React tests simulate 404 + 503; the expired job is
  blocked, transient job retries only once, prior blocked guidance survives,
  and no success/final submission is invented.
- Real `App` React test confirms a 403 stops before the second job and
  never leaks a raw error response.
- Component tests prove stop intent is visible and passed to the parent,
  and that unstarted exact keys remain selected without employer actions.
- Preserve all original Python+PostgreSQL, three-case synthetic
  AutoApply E2E, React, MV3 companion, 61 Chromium and isolated Compose
  Docker checks at the exact PR SHA and independently after merge.

## Scope boundaries and production gate

**Not implemented:** employer-initiated automatic applications, signed-in
headless ATS browser execution, CAPTCHA/MFA bypass, verification of real
employer acknowledgments, outgoing agent follow-up email/calls, or account
permissions to an independently controlled provider.

Greenhouse's documented Job Board application POST requires an
employer-issued API key and may not validate required fields on behalf of
the client. Any future Greenhouse adapter must obtain independent employer
rights, exact per-posting form review, fresh user approval and a trustworthy
provider acknowledgment; SP50 does not bypass those gates.

As of this run the verified public health endpoint did not expose
`release_revision`, SmartPloy remained `enabled: false` in the
ObumDelivery project inventory, and the delivery controller required
authenticated access. CI is not OVH deployment. Production needs the
reviewed ObumDelivery native controller admission, exact-SHA
qualification, guarded OVH backup/rollout, public revision + companion
attestation, and authorized signed-in employer acceptance.

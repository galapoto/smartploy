# SP42 — Persist applicant-observed manual Ashby confirmation without claiming employer ACK

**Baseline:** SP41 `main@347f1673ec69232987dcd4ebc9184d261107d047`.
**Plan:** SP21 P0-C employer outcome tracking and Agentic SmartPloy Gate 1
(application lifecycle). **Date:** 25 October 2026.

## Verified problem

SP41 lets an opted-in applicant take a reviewed Finnish Ashby draft to an
exact hosted `/application` form, fill approved ordinary fields and attach a
reviewed PDF. Ashby final submission stays **manual**; the old browser receipt
flow required a previous Lever-only one-use local attempt marker and its Python
validator rejected non-Lever hosts. A person who had submitted an Ashby
application could not carry even the visible employer reference back into
their owner-bound application workspace.

## Reuse-first implementation

- **Reuse** the original `BrowserReceipt`/PostgreSQL storage, already
  owner-bound `POST /application-workspaces/{id}/browser-receipt`,
  exact document revision/digest and explicit `confirm_user_observed`,
  idempotent one-receipt-per-workspace uniqueness and zero independent-ACK
  counter contract. No schema change.
- **Reuse** original MV3 `inspectReceipt` browser script, only allowing
  exported observations with BOTH a recognizable confirmation phrase and
  bounded visible employer reference, and rejecting live Submit controls.
  Reuse its page text SHA-256 to record evidence, but never transmit page
  content, cookies, credentials or CV to SmartPloy.
- **Reuse** SP41 reviewed, time-limited signed-in first-party packet
  fingerprint, exact Ashby source URL and no-active-tab background access.
- **New code:** one narrow Ashby same-job origin+path branch on each side of
  the original receipt validator, a manual-submission confirmation in the
  existing popup, source tests and source guidance.
- **Retain unchanged**: Lever only independent employer-action rights,
  `oneAttemptKey`, `withSubmissionLock`, `submitReviewedLeverOnce`
  and durable one-use claim. NO new Ashby submit or provider acknowledgment.

## Applicant-visible path

1. Open *My applications* and a current Finnish Ashby draft, review/save
   the original CV and letter, record signed-in job/CV review, copy
   the 15-minute browser packet, and verify in the companion.
2. Use the existing reviewed form helper and **personally submit** the form
   on the real Ashby site, with consent/legal answers under personal control.
3. If a visible same-job confirmation containing a recognizable application
   reference appears, open the companion with the same packet and click
   **Check a prior Lever attempt or manual Ashby confirmation**. Confirm
   that YOU personally submitted the job. The companion performs a
   read-only same-job check; it never invokes a submit action.
4. Copy the private observed-receipt JSON. In Application Studio import it
   using the existing **Store observed confirmation** action and explicit
   user acknowledgment. A browser observation remains
   `browser_observed_unverified`; the `actually_submitted` metric is
   unchanged, and the original documents become read-only.
5. Confirm the result using **I applied on employer site**, which records
   a self-report and causes the existing application-agent status
   reconciliation/follow-up workflow to advance without claiming a provider
   delivery receipt. If no reference, simply self-report; do not guess.

The 15-minute packet, user review and 5-minute local verification may expire
before the employer's confirmation appears. In that case **do not replay**
a submission; report the application manually and retain the confirmation
email yourself. Unknown confirmation forms or redirect hosts remain manual.

## Trust, privacy and idempotency

- Strict HTTPS `jobs.ashbyhq.com` and **exact board+job path prefix with
  a slash boundary** (not just tenant-level matching). A sibling job,
  another board or a lookalike subdomain cannot be imported. The visible
  confirmation query/fragment is never stored.
- The selected draft must still be owned, status `draft`, with the same
  application URL, revision and exact current CV/letter digest; a changed
  or stale document is refused. The private API requires an explicit
  `confirm_user_observed=true`; read-only status does not grant permission.
- No submit button click or new application attempt marker is ever made
  for Ashby; a hidden attachment may already have sent bytes due to the
  employer page's own event handlers as described by SP41.
- A browser reference is **not independently authenticated**. A hostile
  browser or user could falsify a page; no provider-confirmed submission
  counter or automation consent is derived from this observation.

## Core acceptance tests and release gates

- Python validator: same Ashby job accepts recent reference and strips
  URL query+fragment; cross-job/sibling-prefix, cross-board, offsite and
  HTTP are refused; revised CV, stale status and invalid receipt rejected.
  Existing persisted repo and HTTP API return unverified status only.
- Node: strict same-job Ashby confirmation path without enabling Lever
  final-click recognition.
- Chromium: the **actual original inspector** sees a confirmation phrase
  and reference on a synthetic Ashby page, refuses sibling jobs,
  unfinished forms with live Submit, missing references; checks legacy Lever
  receipt extraction still works. Zero external employer traffic.
- Static contract verifies user confirmation and signed-in review gate,
  and ensures Ashby receipt code cannot run Lever final-click or reserve.
- PR-head full CI 5/5; merge only after green, then independent merged-main
  exact SHA 5/5. Native **ObumDelivery/Woodpecker** qualification, guarded
  OVH production deploy and a signed-in real-user consenting employer
  browser test remain independently unverified until operator evidence
  exists.

**Production truth:** Public `/healthz` previously reported healthy storage
and worker but no running `release_revision`. The source already implements
`release_revision` and `deploy.sh` checks exact reviewed SHA. This run does
not pretend the running OVH service has been upgraded.

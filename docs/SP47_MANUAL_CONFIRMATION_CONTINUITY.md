# SP47 — Manual confirmation continuity for supported application forms

**Date:** 26 October 2026, Finland  
**Baseline:** SP46 `d6653f83a2fa44f148d520805b2af08bdfa85c04`  
**Plan:** SP21 P0-C browser outcome tracking; Agentic SmartPloy case continuity  
**Companion version:** 0.5.1

## The core problem and resulting behavior

SP46 connected the existing CV-first application engine to a synthetic
authorized Lever provider acknowledgment. The assisted browser path still
had two gaps: a person who submitted a Lever form manually could not export
confirmation evidence because no automatic attempt marker existed, and
Greenhouse form assistance had no observed-confirmation path. Lever also
accepted any confirmation under the same employer account, which could
associate a different job's confirmation with the selected workspace.

SP47 completes manual observation for the three already supported hosted
providers and requires exact job identity in both browser and server.
It reuses the existing private receipt import and application history.

| Provider | Accepted observed page scope | Final employer action |
| --- | --- | --- |
| Lever, global or EU | Same provider region, employer and job; exact posting, `/apply` with bounded child paths, or `/thanks` | Existing separately authorized one-use action, or applicant manually submits |
| Ashby | Same employer and job; exact posting or `/application` with bounded child paths | Applicant manually submits |
| Hosted Greenhouse | Same board and numeric job ID; exact posting or `/confirmation`; official legacy/current host equivalence only | Applicant manually submits |

Trailing slashes are accepted where covered by the original posting grammar.
The observed page's query and fragment are discarded. Cross-job, cross-board,
tenant-wide thank-you pages, lookalike/escaped hosts, non-HTTPS URLs, user
credentials, nondefault ports, escaped or ambiguous paths are rejected.
Greenhouse custom domains and iframe-only flows remain outside this adapter.

These are deliberately bounded supported routes, not a promise that every
employer displays a reference or preserves a usable confirmation URL.
Greenhouse lets employers customize their confirmation message; it also
documents that confirmation emails are configurable rather than universal:
[confirmation page](https://support.greenhouse.io/hc/en-us/articles/115005516483-Edit-application-confirmation-page),
[confirmation email](https://support.greenhouse.io/hc/en-us/articles/115004681926-I-applied-to-a-job-post-but-I-didn-t-receive-confirmation).

## Applicant flow

1. Prepare and review the existing application, then verify its short-lived
   packet on the signed-in SmartPloy tab.
2. Finish and personally submit the employer form when automatic submission
   is unavailable. No submission is caused by receipt inspection.
3. Return to the visible confirmation and choose **Check a Lever, Ashby or
   Greenhouse confirmation**. For a manual application, explicitly confirm
   that you already submitted this exact job.
4. The companion requires the same reviewed documents, a current signed-in
   review, exact job address, visible confirmation text and reference, and
   no active Submit control. It rechecks browser/document state after awaits.
5. Copy the observation into **My applications → Import observed receipt**.
   The original server verifies owner, workspace, revision, document digest,
   observation age and exact provider/job scope.
6. Keep the employer's email. If no usable reference or exact job URL remains,
   use **I applied on employer site** to record a personal report. Never
   automatically repeat an uncertain application.

If the five-minute browser review expires while the applicant completes the
form, verify the same packet again on SmartPloy before returning to the
confirmation. Expired packets need a fresh packet for the unchanged draft.
An existing automatic Lever attempt keeps its original observation-only
reconciliation path and durable no-retry behavior.

## Reuse and new implementation

| Existing component | Reused behavior |
| --- | --- |
| `browser-companion/review-bridge.mjs` | Signed-in review fingerprints, document/contact binding, expiry |
| SP42 `onResumeReceipt` / `onReceipt` | Explicit manual confirmation and minimal private receipt packet |
| SP43 hosted Greenhouse form policy | Official host pair plus exact board/numeric job identity |
| `smartploy/browser_receipt.py` | Original receipt schema, document digest, observation age and status |
| Existing receipt repositories and API | Owner isolation, idempotent storage, conflict handling and draft locking |
| Application Studio | Receipt import, personal report, queue and application-agent integration |
| Existing companion packager | Deterministic 0.5.1 ZIP, checksum, permission allowlist and release attestation |

New original work is limited to exact-job receipt routing, the missing
manual-provider branches, observation-only UI state, stale-result guards,
tests and current user instructions. There is no new runtime dependency,
framework, database table/migration, browser permission or external project.
The reused source avoids rebuilding identity, storage, receipts and agent
lifecycle. No numerical time-saving multiplier is claimed without measurement.

## Authority and evidence

Manual observation never creates or consumes a final-submit claim, calls an
employer API, uploads a document or clicks Submit. In receipt mode the popup
also disables and guards form filling, attachment, questions and reservation.
The existing Lever-only transport and final-click code remain unchanged.

All browser records remain `browser_observed_unverified` with
`independently_verified_by_employer=false`. They do not increment
`actually_submitted`. A browser observation, an applicant's personal report
and a genuine provider acknowledgment remain separate evidence types.

Independent review reproduced two asynchronous UI races before release:
navigation during the final review lookup, and a delayed earlier form scan
overwriting newer receipt mode. The fixes recheck tab identity/URL and bind
pending work to its original packet and sequence. Regression cases exercise
both races through the real popup event handlers.

## Verification

The feature's local validation includes:

- 94 passing receipt tests and one PostgreSQL-only case deferred locally to
  the repository's real PostgreSQL CI. This includes three actual OIDC
  middleware API cases with different users sharing the same email, no
  automated claims, and a fail-on-use employer transport.
- 18 real-popup Node cases covering the supported providers, current review,
  manual confirmation, prior automated attempt recovery, no claim writes,
  malformed URLs, stale export clearing, subframes and the two UI races.
- 20 targeted Chromium cases: 11 new receipt-inspector cases, five existing
  Ashby/Lever receipt cases and four existing Greenhouse form/PDF cases.
- All 172 existing React tests and the production web build pass.
- Ruff and whitespace checks pass. The existing Python static contracts
  now describe the generalized manual observation path and version 0.5.1.

These tests use synthetic local pages and application data. No employer was
contacted and no real application or live provider acknowledgment is claimed.
The PR must also pass the existing full five-job source CI, including real
PostgreSQL and Docker smoke, before expected-head merge. Independent merged
main CI is a separate source check. Neither is native deployment evidence.

## Production audit and remaining work

A fresh read-only audit on 26 October returned HTTP 200 and healthy storage/
worker status from `https://smartploy.komplyint.fi/healthz`. The signed-out
dashboard returns 401 and login redirects directly to ZITADEL. However,
health does **not** expose `release_revision`; the latest source cannot be
identified as running. `obumai_configured` is false.

Delivery source at `obumai/obum-delivery@af49a3662d29d1769b9279e987a0aa0f8446d50e`
still lists `galapoto/smartploy` as disabled. Its admission contract and
SmartPloy's native workflow retain the production HOLD. The public controller
requests returned 403; no authenticated controller or OVH execution connector
is available in this session. This is an access/commissioning blocker,
not a request for another deployment engine or for production credentials
inside ordinary test jobs.

| Status | Remaining item |
| --- | --- |
| Done in this change | Manual confirmation continuity and exact-job attribution |
| Blocked on authenticated delivery access | Controller admission, native exact-SHA qualification and guarded OVH release |
| Not yet verified | Live signed-in application journey, companion installation and source-worker freshness |
| Not yet verified | One genuine, authorized employer/provider acknowledgment |
| Incomplete | Non-Lever automatic final submission; external agent follow-up channels |
| Next source usability issue identified | CV-first job list hides rows beyond its first 80 and can omit a search-selected job outside returned matching limits |

Use the existing `deploy/personal/scripts/deploy.sh` and release-evidence
workflow once the authenticated delivery path is commissioned. Require the
public release revision, running image/companion checks and signed-in
acceptance before describing SP47 as available in production.

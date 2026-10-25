# SP43 — Greenhouse-hosted jobs to reviewed browser form assistance

**Date:** 25 October 2026
**Plan:** SP21 P0-C, employer application handoff, Agentic SmartPloy Gate 1.
**Baseline:** SP42 `main@6c6cc22da594a3ea426bf81f25a655f2044c7ebd`.
**Status:** code/CI only; OVH release needs independent native ObumDelivery evidence.

## Gap closed and why it advances AutoApply

The existing SP20 public Greenhouse Job Board API adapter publishes source-current
explicitly Finnish vacancies and SP33/SP40 AutoApply can prepare consented
private drafts. Before SP43, the signed-in review and local Chrome companion
refused Greenhouse URLs, so the user had to leave SmartPloy and re-enter
every approved contact/CV/ordinary question manually.

SP43 connects **the original read-only Greenhouse API → normalized Finland
job → private CV/job-specific draft → approved packet → same reviewed local
browser form help**. The employer's final submission is the applicant's
action. No general headless application, employer API submission or guarantee
that every Greenhouse form is supported is claimed.

## Exact supported host boundary

- Greenhouse-owned hosted standard post only:
  `https://job-boards.greenhouse.io/{board}/jobs/{numeric-id}`
  or legacy `https://boards.greenhouse.io/{board}/jobs/{numeric-id}`.
- A legacy posting is permitted to redirect to the **other named official
  Greenhouse host** only when the entire board+job numeric ID is identical.
- No custom employer careers domains, embedded iframes, opaque job aliases,
  redirects to unrelated hosts, query/fragment tracking links, or cross-job
  navigation are authorized by this packet. Such links remain manual.
- Even a supported URL only enables first-party, user-approved ordinary
  name/contact/cover-letter fields, user-reviewed ordinary free-text questions,
  and a unique visible CV PDF field under exact hash and form metadata.
  The actual form must be at the top level, have a standard reviewable DOM
  and obey the original 250-field, 12-question limits and dynamic rerender
  stops. Unknown fields, CAPTCHA, legally protected attributes, privacy
  terms, uploads without exact matching digest, and iframe-only forms remain
  applicant-manual.
- The employer webpage may itself transmit on input/change; inform the
  applicant before every user-controlled data transfer.

## Reuse vs scratch

Reused **without a new runtime**:
SP20 `GreenhouseAdapter` and source-current Finnish location filters,
SP33 opt-in private auto-draft queue and per-job agents,
SP15d first-party signed-in review, OIDC owner/revision Postgres locks,
SP41 exact PDF digest and ordinary contact/question mapping, the single
MV3 extension popup, the original final-claim/permission gate and explicit
personal form review. Existing app/worker/Postgres images and source tests
are unchanged.

New original code: strict Greenhouse-hosted URL parser and official-host
alias; provider-isolated **`greenhouse-review-only-v1`** non-bearer job
identity in the existing review-intent table; tiny authorization branches
in the existing Chrome packet/inspect/standalone contact/question/PDF
executors; unit/real adapter/real SQL/synthetic Chromium tests; user
copy and usage documentation. No new dependency, schema migration,
model invocation, account store, browser permission, background content
script or employer credential.

## Safety and independent authority

`browser_handoff._posting_url`,
`employer_automation_rights.employer_job_key`,
`employer_submit_claim_storage._employer_job_key_sha256`,
`PostgresEmployerSubmitClaimRepository.reserve`, the durable
cross-device final action grant and `submitReviewedLeverOnce` remain
**Lever only**. A Greenhouse review marker never becomes submission
authority, and Greenhouse browser receipt export is NOT implemented;
after personally submitting, the user uses **I applied on employer site**
and keeps their employer confirmation. Browser observations and
applicant self-reports never increment verified provider ACK.

## Required acceptance evidence

1. Existing genuine `GreenhouseAdapter` under mocked GET: one Helsinki
   data vacancy, no foreign/prospect-only jobs, no external data forwarding,
   same source-original application URL, reviewed packet (no raw CV).
2. Backend: only exact official hosted URLs accepted, original Lever-only
   final rights reject Greenhouse. The same signed-in owner/revision/
   job/approved-document Postgres locks accept only non-submitting
   review; different user, board, job and final submit claims are denied.
3. Node: exact old/new Greenhouse board host equivalence,
   cross-board, sibling-ID, arbitrary-path, query, hash and iframe reject.
4. Chromium: original serialized form executor fills approved contacts and
   applicant-reviewed ordinary questions on a **mocked modern Greenhouse
   form** when the packet is the legacy Greenhouse URL; PDF original hash
   transfer succeeds under explicit approval; attempts to change legal/
   sensitive fields, different employer, SHA and dynamic rerender block.
   Zero synthetic employer Submit clicks or off-fixture HTTP traffic.
5. Full PR-head CI 5/5, merge only green exact head SHA, then independent
   merged-main CI. The Compose smoke is not production. Native Woodpecker,
   guarded pinned-SHA OVH rollout, two-account signed-in extension QA and
   consenting employer end-to-end experience are additional gates.

## Honest remaining blockers

- Live `https://smartploy.komplyint.fi/healthz` currently reports ready
  PostgreSQL/worker but does **not** expose the `release_revision`
  already implemented in source. This is NOT proof SP43 is deployed.
- Official Greenhouse Job Board API employer submission requires employer-
  controlled API credentials; this implementation does not obtain or use
  them. No scraping/login bypass or inferred permission to submit.
- Unknown / embedded employer forms need manual handoff.
- Before automatically claiming any application succeeded, an actual
  provider-issued acknowledgment and per-employer permission are required.

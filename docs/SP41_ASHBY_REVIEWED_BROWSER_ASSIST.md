# SP41 — First reviewed Ashby application form assistance (not submission)

**Date:** 25 October 2026
**Plan:** SP21 P0-C first real browser handoff; Agentic SmartPloy Gate 1.
**Source baseline:** SP40 `main@a50b39af3f24f348ed6b07932f18243c875043e3`.
**Release posture:** source/CI only; native ObumDelivery exact-SHA, OVH rollout and signed-in physical-extension test remain independent.

## Core gap

SP40 repaired the original AutoApply background-draft admission for approved,
freshly verified Finnish Ashby vacancies. Yet every user-facing browser packet,
signed-in review marker, companion validator and PDF/question executor accepted
Lever only. An Ashby applicant could prepare a reviewed application but
could not progress to browser-assisted form fill without copying everything
manually.

This change reuses the established review-first path **on standard, exact
Ashby-hosted `/application` forms**. Supported actions are explicitly user-
initiated approved contact/cover-letter fill, reviewed ordinary text answers
and reviewed CV PDF attachment. The employer's own page may transmit data
immediately on input/change or file attachment; the applicant must approve
the transfer and inspect every field.

## Reuse first, no unnecessary provider runtime

- Reuse original SP15d authenticated first-party review and signed-in OIDC
  session, exact CV/letter/fields SHA-256 digest, short-lived non-bearer
  Chrome session fingerprint and the existing employer revision/source checks.
- Reuse existing SP15a PostgreSQL owner → workspace → current-job preflight
  with a **strict `assisted_review_only=True` flag**. The ordinary final
  submit/claim preflight keeps its original Lever-only default.
- Reuse the same SP14 `planReviewedQuestions` safety rules, original
  contact-field mapping, `chooseResumeField`, PDF magic+trailer+digest checks,
  isolated-world injection, user approval and no-persistent-PII design.
- Reuse SP40 exact Ashby job-board URL identity and published `/application`
  route rather than a general browser automation service.
- New original code: small domain-separated Ashby REVIEW-ONLY job hash;
  exact provider/form route guards in the original backend/companion; narrow
  branch for the original popup; synthetic Node/Python/Postgres/Chromium
  acceptance for those real executor functions. No new dependency, model,
  account store, employer credential, browser permission, background
  content script or database migration.

## Safety and authority separation

The original `browser_handoff._posting_url`,
`employer_automation_rights.employer_job_key`,
`employer_submit_claim_storage._employer_job_key_sha256`, cross-device
`PostgresEmployerSubmitClaimRepository.reserve`, and
`submitReviewedLeverOnce` remain Lever-only.

Only the review-specific `PostgresEmployerReviewIntentRepository` gains
`ashby-review-only-v1` identity with the exact tenant/job canonical path.
A successful signed-in review returns no bearer grant and cannot reserve
an Ashby employer attempt. Client final claim, final preflight, one-use
final button and receipt export remain unavailable to Ashby. There is no
Ashby employer POST, final submit, background click, remote model call,
automatic retry or provider acknowledgment.

For Ashby, require exact HTTPS hostname `jobs.ashbyhq.com`, exact
`/{tenant}/{job-id}/application` (trailing slash acceptable), no query/
fragment, no off-host or subdomain, exact inspected URL, top-level browser
frame, matching form/visible input metadata, bounded 250 controls, approved
CV SHA-256 and user confirmation before attachment. Unsupported custom
forms, CAPTCHA, privacy, immigration, salary, radio/select/checkbox,
unknown/sensitive fields and unexpected React rerenders remain manual.

The packet may be obtained for an exact Ashby job posting URL or the
`/application` URL. Form execution only occurs on the matching
`/application` route. No cross-employer fallback or generic host allowlist.

## Tests / release proof

- Pure Python: reviewed Ashby packet contains only approved contact, letter,
  CV digest, no raw CV; invalid host/query/path rejected; original Lever-only
  independent employer final-rights identity refuses Ashby.
- Real PostgreSQL: two-account review record and exact current job/revision/
  document checks, Ashby `prepare → verify → cancel`, no final submit
  claim, no cross-account review.
- Pure Node: 15-minute packet for exact Ashby same-job form, rejects
  cross-board/offsite/redirect/cross-job; exact PDF form guard and
  Lever-only final-provider recognition.
- Chromium: actual original form executor fills ordinary name/email and
  user-reviewed answer, original PDF attachment places exact bytes into
  unique form field, changed/foreign employer and sensitive metadata are
  refused, dynamic required field insertion stops further filling;
  synthetic employer submission handler must record **zero submits** and
  no network request may leave the isolated fixture.

Run exact PR-head CI, then merge with expected SHA only if green, and rerun
independent merged-main CI. A synthetic Docker compose smoke is NOT an OVH
deployment. Real logged-in Chrome extension acceptance with an authorized
test-employer remains required before claiming live support.

## Progress

- **Done in source:** exact Ashby reviewed packet, signed-in review ledger,
  standard browser field/question/PDF help, never an Ashby final click.
- **Pending CI:** PR-head suite and merged-main suite.
- **Blocked:** native Woodpecker exact-SHA qualification, guarded OVH rollout,
  signed-in user and synthetic consenting employer live verification.
- **Not done:** real Ashby provider submission API, independently permitted
  final browser submit, full arbitrary ATS agent, employer receipt ACK.

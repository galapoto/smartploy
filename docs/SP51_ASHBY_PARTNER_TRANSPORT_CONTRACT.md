# SP51 — Official Ashby partner transport behind original release gates

**Date:** 26 October 2026 (Finland)  
**Plan:** SP21 P0-C approved ATS submissions; follow-up after SP50 `main@ec09d9e2f97ed577085f6372e766aee12062ac82`  
**Status:** internal SOURCE ONLY — this feature does NOT register an HTTP endpoint, browser permission, background worker, or real employer submission.

## Why Ashby first

Research on 26 October 2026 confirmed that Ashby's official
`jobPosting.info` returns a per-posting application form, the documented
`applicationForm.submit` endpoint returns a `submittedFormInstance.id`
and `formMessages.blocked`, and the independent `application.info`
endpoint can return the actual application ID using that submitted-form
instance ID. The exact return value and blocked check matter: an HTTP
`200` is not sufficient proof that an employer accepted the application.

Official references:

- https://developers.ashbyhq.com/docs/creating-a-custom-careers-page
- https://developers.ashbyhq.com/reference/jobpostinginfo
- https://developers.ashbyhq.com/reference/applicationformsubmit
- https://developers.ashbyhq.com/reference/applicationinfo
- https://developers.ashbyhq.com/reference/authentication

Greenhouse also supports employer-keyed application POST, but warns it
does **not validate the inclusion of all required fields**, making it a
worse first choice until exact form-question binding is independently
reviewed: https://docs.greenhouse.io/job-board.html

## Reused vs original implementation

**Reused:** `smartploy/browser_handoff._assisted_posting_url` exact hosted
Ashby HTTPS origin/job validation; original P0-C policy that an employer
API key comes from an approved business partner and is never sent to the
browser; original deterministic reviewed PDF and applicant fields;
HTTPX for no-redirect client traffic; existing configuration and
readiness contract style from `lever_partner_submit.py`.
All runtime code is original SmartPloy source — no vendor SDK imported,
new dependency installed, or external software runtime required.

**SP51 original build:**

1. `smartploy/ashby_partner_submit.py`: separate, opt-in, exact-job
   `AshbyPartnerRegistry`. Empty config fails closed; the configured job
   slug is NEVER guessed to be an Ashby UUID. Each employer-operated
   posting must map to an explicit official UUID and independently pinned
   form SHA-256. Only server-side credential environment names are
   accepted. Company wildcard/redirect/private credential exposure is
   forbidden.
2. `AshbyPartnerTransport.send_after_external_claim` is a **dormant
   internal transport**, not a public route. It must not be used until a
   separately authenticated, reviewed, employer-authorized, irrevocably
   consumed PostgreSQL claim has been provided by a follow-up integration.
3. Before transferring ANY applicant data, POST to the official Ashby
   `jobPosting.info` read-only endpoint (requires employer `jobsRead`).
   Verify the exact partner UUID, published/listed job, same hosted job
   destination, absence of additional survey forms, independently
   reviewed entire form checksum, and only recognized fields.
   Reject required extra questions, unfamiliar consent/EEOC/demographic
   fields and all changed forms. Never generate implicit answers.
4. Submit one reviewed PDF directly using documented
   `multipart/form-data` on the fixed HTTPS
   `https://api.ashbyhq.com/applicationForm.submit` endpoint
   (employer `candidatesWrite` permission). No presigned third-party
   upload URL, dynamic employer-supplied hostname, log of private fields,
   follow_redirects, speculative retry or fallback browser click.
   Explicitly set `allowSubmissionForUnpublishedJobPosting=false`.
5. Treat the official `submittedFormInstance.id` as a form reference,
   NOT an application ID. Require `success=true`,
   `formMessages.blocked=false`, same independently reviewed form
   definition, and exact returned name/email before further verification.
6. Read-only `application.info` (requires employer `candidatesRead`)
   resolves that form reference to a real `applicationId`. Only this
   combination returns a `AshbyPartnerAcknowledgment`. Missing/read
   denied/ambiguous outcomes require reconciliation and **never
   permit automatic application retransmission**.

**Business prerequisite:** A consenting Ashby employer must provide an
authorized API key with `jobsRead`, `candidatesWrite`, and
`candidatesRead`. Keys and independently reviewed form digest remain
server secrets/config. DO NOT put them in GitHub, PR comments, model
prompts or client/browser storage.

## Tested contract (all offline / synthetic)

`tests/test_ashby_partner_submit.py` uses `httpx.MockTransport` only.
It tests empty/malformed configuration, exact hosted employer job
isolation, secret non-disclosure, valid form and PDF, real multipart
field wiring with **one** POST and a separate official application-ID
lookup, non-listed or unpublished jobs, employer/form/question drift,
presence of surveys, blocked/ambiguous provider responses, and no
retry on a synthetic network timeout.

The full original Python/PostgreSQL + React + extension + Chromium +
Docker CI must remain passing on the exact candidate and merged main.
These simulations are NOT a production employer acknowledgement.

## Remaining critical gates (NOT implemented or claimed)

- Review and extend the existing **Lever-only** employer job identity
  and two-independent-operator rights scope for Ashby. Do not merely
  allow Ashby URLs through the Lever-specific claim path; it would weaken
  existing browser final-click boundaries.
- Integrate a distinct action scope and SQL migration, same-transaction
  current owner/posting/document form checks, fresh applicant final
  consent, one-time sticky original claim, and an Ashby-specific
  authenticated first-party reviewed-submit route. No background
  unsolicited sending or cross-provider blanket permissions.
- Atomically persist exact `formInstanceId` and true Ashby
  `applicationId` in original owner-bound provider receipt and
  `provider_acknowledged` workspace. Do not infer acknowledgment
  from HTTP 200, browser click or successful PDF upload.
- Add owner-scoped React readiness/review/consent, real Postgres
  OIDC two-subject synthetic flow and authorized live consenting-employer
  acceptance. Missing required custom questions, legal declarations,
  company-specific surveys or employer API key remain **Needs review**.
- SmartPloy source is not production: ObumDelivery inventory still has
  `galapoto/smartploy enabled: false`; the running OVH health endpoint
  does not attest a release revision. Native controller admission,
  guarded exact-SHA OVH deployment and signed-in end-user acceptance
  are still blocked.

No new general coding engine, agent platform, ATS crawler, database
table or external runtime dependency was introduced in SP51.

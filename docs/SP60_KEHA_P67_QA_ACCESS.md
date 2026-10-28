# SP60 — Komplyint Oy KEHA P67 QA test access and isolated acceptance

**Date:** 28 October 2026
**Source baseline:** SP59 `65e21fe2346b1a76f7fb103f9289415d346a3787`
**Plan subpart:** SP21 P0-A nationwide Finnish source discovery; SP21 P0-C verified source freshness before CV-first AutoApply.

## Verified external event

On 26 October 2026 KEHA Centre granted Komplyint Oy access to the
**Job Market Finland Job Posting Search API P67 v2 QA environment** and
provided the KIPA subscription key via secure message. This is **NOT**
production approval. The provider explicitly asks for sufficient test
results before issuing a separate production credential.

- Exact approved QA URL: `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings`
- Exact production URL, **NOT yet authorized**: `https://api.ahtp.fi/kipa/p67/v2/jobpostings`
- Contract: HTTPS POST with `KIPA-Subscription-Key` header,
  `onlyStatus` PUBLISHED/ARCHIVED, bounded `modified.from/to`,
  languages `fi,en,sv`, NDJSON response.
- Access can also depend on KEHA's IP allowlist; a 401/403 requires
  credential/allowlist review and never authorizes a less secure URL.

## Reuse before new code

**Reused first-party:** `JobMarketFinlandSettings` exact allowlist,
`JobMarketFinlandAdapter.fetch_window`, existing credential redaction,
NDJSON parsing, source provenance, original attribution and
`external_ai_forwarding_allowed=false`. Existing synthetic
PUBLISHED/ARCHIVED→PostgreSQL retirement tests continue unchanged.
No second crawler or ATS interface; no provider client implementation.

**New missing acceptance glue:**
- `scripts/probe_jobmarket_finland_qa.py`: default offline check
  (`0` HTTP requests). Explicit `--execute` performs precisely two
  P67 QA-only reads for a bounded time window, uses the original adapter,
  outputs only counts/fixed states, and **never connects to PostgreSQL**.
  No job text, applicant records, credentials, upstream raw bodies or
  private errors appear in stdout/stderr. The source remains OFF for
  all normal workers.
- `JobMarketFinlandSettings.from_env()` rejects any QA source
  activation when `SMARTPLOY_ENVIRONMENT=production`, applying to
  both one-shot polling and background worker registration.
  `preflight.sh` independently rejects `JOBMARKET_FINLAND_API_ENABLED`
  in live production unless the environment is `production` and
  the configured endpoint is the exact official production P67 address.
- New mock HTTP unit tests prove PUBLISHED then ARCHIVED, exact URL,
  request body and headers, zero valid results, no data persistence,
  refusal of wrong QA env or host, redacted 403 response, bounded
  window, explicit execute and default no-network mode.

## Operator QA run (not performed by GitHub CI)

1. Do **not** copy the actual key into GitHub, ChatGPT text, email
   drafts, a .env committed to source control, browser javascript, or
   the production `deploy/personal/env`.
2. Because the credential was visible in screenshots, consider it
   **exposed** and ask KEHA to replace it before team-wide or
   production acceptance. Store a fresh QA credential in a protected
   secret manager or a mode-0600 private file on a separate, trusted
   **QA-only** machine/checkout. The credential is a secret even though
   the test host address is public.
3. Keep `JOBMARKET_FINLAND_API_ENABLED=false` and set
   `JOBMARKET_FINLAND_ENVIRONMENT=test` for the isolated test runner.
   Export `JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY` into only the
   short-lived shell environment. Never supply the key as a CLI argument
   or commit it into an example.
4. With source containing SP60, run
   `python scripts/probe_jobmarket_finland_qa.py` first. This verifies
   only configuration/credential presence and performs **zero** network
   requests. The receipt says `live_qa_verified=false`.
5. Then on the isolated QA checkout, run
   `python scripts/probe_jobmarket_finland_qa.py --execute --minutes 30`.
   It sends only two bounded read-only HTTPS POST searches to KEHA QA,
   with zero database writes or employer actions. Report fixed
   `qa_reachable`, `published_query_passed`,
   `archived_query_passed`, and aggregate counts only.
   A successful empty interval is valid: it does **not** mean live
   current national jobs have been discovered.
6. If the script says `QA_AUTHORIZATION_OR_IP_ACCESS_DENIED`, check
   the secret and contact KEHA about the **QA tester's egress IP**.
   Never paste credentials, raw HTTP headers or job bodies into
   GitHub issues/CI logs. The script deliberately does not auto-retry
   rate limits.
7. Request a separately issued **production** P67 credential from
   KEHA only after the test result is satisfactory. The production
   adapter must not be enabled until this and the normal release
   provenance/owner approval gates succeed.

## Acceptance status and privacy boundary

**Source test PASS** means the synthetic adapter/probe and production
separation passed CI. **Real KEHA QA access PASS** requires an operator
to show the `qa_reachable` receipt from the actual QA endpoint
without the credential. No real authenticated QA call has been
performed by the GitHub source workflow.

This API is **retrieval only**; it cannot send applications. KEHA terms
require original source attribution, prompt removal of expired items,
restrictions on forwarding to third parties, and permission before using
the dataset to market a service. SmartPloy retains these restrictions.
Public launch and production data ingestion are still HOLD.

**Next operational evidence:** timestamped QA red/green result and
separately approved production credentials. Current live SmartPloy
source version remains unverified without OVH release revision,
native ObumDelivery acceptance and authenticated CV-to-draft proof.

## Authoritative documentation

- https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html
- https://tyomarkkinatori.fi/jobpostingProvider/swagger/api-docs/P67-tmt-provider-haku-V2
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings/terms-of-use-for-job-market-finlands-job-posting-apis

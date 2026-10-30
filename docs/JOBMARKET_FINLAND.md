# Job Market Finland P67 integration

## Purpose

Use KEHA Centre's official Job Market Finland job-posting retrieval interface v2 as Smartploy's
national job source.

## Activation

The interface is not anonymous. The organisation must activate the interface with KEHA Centre, accept
the terms, test against the QA environment and receive credentials. Smartploy does not automate this
process and ships the adapter disabled.

Environment variables are documented in .env.example.

## Official endpoints

- Test: https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings
- Production: https://api.ahtp.fi/kipa/p67/v2/jobpostings

Smartploy accepts only the exact HTTPS endpoint corresponding to the selected environment. Requests use
POST and KIPA-Subscription-Key. The key and any additional KEHA-supplied headers are runtime secrets and
are never persisted in job observations or returned to the web UI.

## Incremental lifecycle

Each poll uses a modified interval with overlap and performs two calls:

1. onlyStatus=PUBLISHED
2. onlyStatus=ARCHIVED

PUBLISHED results are normal Smartploy observations. ARCHIVED results are source lifecycle signals, not
new jobs. Smartploy retires the matching source external ID only when it has previously observed that
ID. An empty incremental response is not evidence that older jobs are closed.

## Source terms

Smartploy preserves the required original source label:

Source: Job Market Finland's customer information system

Archived Job Market Finland payloads are redacted from Smartploy source observations. If no other
current source supports that canonical vacancy, the canonical job is closed and its retrievable posting
content is redacted. If another independent source remains current, the canonical record is rebuilt
from that source.

The published retrieval terms also restrict forwarding retrieved postings to third parties. Therefore
Job Market Finland candidates have external_ai_forwarding_allowed=false. Smartploy scoring still works,
but ObumAI reasoning/application-draft preparation is blocked for those candidates until an explicitly
permitted processing mode exists.

## Operator command

~~~bash
python scripts/poll_jobmarket_finland.py
~~~

The command requires PostgreSQL so external-ID lifecycle state survives process restarts.

## References

- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings/retrieval-interface-description-and-instructions
- https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings/terms-of-use-for-job-market-finlands-job-posting-apis

## SP60 — KEHA QA test user grant (28 October 2026)

KEHA Centre granted **Komplyint Oy** a **QA-only** KIPA subscription on
26 October 2026. This grant does **not** authorize the production endpoint.
The official P67 v2 OpenAPI schema confirms `POST`, a `modified` interval,
`onlyStatus=PUBLISHED/ARCHIVED`, `postingLanguageIn`, and NDJSON.

**Keep the QA key out of Git, ChatGPT transcripts, browser logs and the
production `deploy/personal/env`.** Because the key was shown in shared
screenshots, request a replacement key from KEHA before production-grade
or team-shared testing.

The standalone safe test is `scripts/probe_jobmarket_finland_qa.py`. It
reuses `JobMarketFinlandAdapter` rather than creating a second P67 client.
With no arguments it performs **zero network calls** and reports only
whether a key is present. With `--execute` it uses only the exact
`https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` endpoint, makes two
bounded POST search calls (PUBLISHED and ARCHIVED) for the last 30 minutes
and reports safe aggregate counts. Zero results is a valid QA response.

The QA test reads `JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY` from a
private shell environment (not a command-line argument). Keep
`JOBMARKET_FINLAND_API_ENABLED=false` in that test environment; the
standalone QA probe explicitly refuses the enabled production/worker path.
It uses **no database**, user account, model or application submission.
It does not save returned job titles, source bodies, credentials or CVs.
If QA requires the calling IP to be allowlisted, confirm the exact
test-host outbound IP privately with KEHA rather than lowering TLS checks.

**Do not flip Job Market Finland on in the live SmartPloy worker.**
`JobMarketFinlandSettings.from_env` now refuses QA credentials when
`SMARTPLOY_ENVIRONMENT=production` and the production preflight
also rejects enabled QA configurations. A later production rollout requires
a separately issued **production** key, exact official production endpoint,
operator approval, and the existing image/source/receipt acceptance gates.

Public display remains subject to original-source attribution, rapid
removal of closed vacancies, restrictions on transfer to third parties,
and no promotion/marketing based on the retrieved data without KEHA's
permission. The earlier `external_ai_forwarding_allowed=false` flag
remains unchanged.

**QA evidence to request without leaking secrets:** exact UTC test time,
`qa_reachable` or a fixed error category, PUBLISHED/ARCHIVED query
success and counts, no job storage or external AI actions. These are
still not evidence of production source availability.

Official references:
- https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings/terms-of-use-for-job-market-finlands-job-posting-apis

## SP76 — production key grant and read-only acceptance (30 October 2026)

**Update to SP60:** On 30 October 2026, KEHA issued **separate production**
P67 job-retrieval credentials to Komplyint Oy through a time-limited secure
message. The previously stated **QA-only** status remains historically accurate
for October 26–29, but is **superseded as an authorization blocker** by this
production grant. The production key is **not** stored in GitHub or this chat.
No authenticated *production* P67 POST, posting import or OVH rollout has yet
been independently observed.

The next step is the existing production adapter's **database-free**
`scripts/probe_jobmarket_finland_production.py`, using the official
`https://api.ahtp.fi/kipa/p67/v2/jobpostings` address and the actual
new key loaded privately on OVH. By default the script is offline and
reads no network. `--execute --minutes 30` deliberately makes exactly
two count-only POST searches and never starts workers or persists jobs.
Source ingestion remains **disabled** until the real probe and independent
trusted OVH release gates pass. Details, the 120-minute-first-window caveat,
terms and operator acceptance: [SP76 production activation](SP76_KEHA_P67_PRODUCTION_ACCESS.md).

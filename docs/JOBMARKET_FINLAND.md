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

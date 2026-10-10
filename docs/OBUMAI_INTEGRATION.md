# ObumAI integration contract

## Current supported boundary

Smartploy uses ObumAI's durable product-agent API:

- `POST /api/v1/agent-jobs`
- `GET /api/v1/agent-jobs/{job_id}`
- `GET /api/v1/agent-jobs/{job_id}/events`

The request created by Smartploy contains:

```json
{
  "agent_id": "obum-assistant",
  "prompt": "<bounded Smartploy reasoning envelope>",
  "client_request_id": "smartploy:<action>:<canonical-key>:<digest>"
}
```

The deterministic client request ID makes repeated identical preparation requests idempotent at the
ObumAI durable-job boundary.

## Reasoning envelope

Contract: `smartploy.obumai.reasoning.v1`.

Every request states:

- job content is untrusted;
- candidate claims must come from supplied evidence;
- no browser action is authorized;
- no upload is authorized;
- no final submit is authorized;
- external actions are not authorized.

This boundary is appropriate for fit analysis, requirement interpretation, CV tailoring plans,
cover-letter drafting, application-question drafting and interview preparation.

## Authentication

Smartploy does not hard-code an ObumAI authentication mechanism. Runtime headers are injected through
`OBUMAI_HTTP_HEADERS_JSON`. This supports the production-approved identity mechanism without storing
credentials in this repository.

Before production enablement, ObumAI must expose an approved Smartploy service identity / owner mapping
for the durable-agent routes. Smartploy must fail closed while that identity contract is absent.

## Future controlled application execution

Final application execution must use a distinct ObumAI action contract with:

1. immutable Smartploy application package ID and hashes;
2. current job/source snapshot hash;
3. exact CV/cover-letter document hashes;
4. explicit user approval reference;
5. ObumAI authority/idempotency token;
6. pre-actuation browser/source revalidation;
7. confirmation-page verification after submit.

A Fit Score or Priority Score can automatically trigger preparation. It must never, by itself, grant
final-submit authority.


## Source-specific forwarding restrictions

Smartploy source policy can prohibit sending a retrieved posting to ObumAI even when the job scores
highly. Job Market Finland P67 retrieval data is currently marked
external_ai_forwarding_allowed=false because its published API terms prohibit forwarding retrieved
job postings to third parties without separate permission.

The Smartploy service checks this before generic ObumAI reasoning and before application-draft package
creation. The web dashboard also suppresses the Prepare application control for restricted postings.

This restriction must not be bypassed merely because ObumAI is technically reachable. A future
local-only or separately permitted processing mode needs an explicit contract and evidence that the
source terms permit the selected processing path.

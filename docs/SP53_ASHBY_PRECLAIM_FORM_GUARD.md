# SP53 — Reject changed Ashby forms before burning an applicant's one-use attempt

**Date:** 27 October 2026 (Finland)  
**Baseline:** merged SP52 main at \`b6a54b324f53e132a188aa225f487dd75b0dec2c\`  
**Plan subpart:** SP21 P0-C exact owner-approved partner employer submission; SP46 real CV-to-employer end-to-end contract; SP50 no-retry failure triage.  
**Status:** candidate source change. An exact-head and merged-main CI run, native ObumDelivery receipt and approved OVH acceptance are independent gates; do not claim live deployment.

## Previous failure path (SP52)

SP52's authenticated Ashby route checks the owner, current PDF/documents, one-job review, independent employer permission and fresh final approval. It then *commits a sticky PostgreSQL attempt* and only afterwards calls the Ashby read-only \`jobPosting.info\` endpoint. If the employer has changed the required form, removed the job, added a survey, or the reviewed letter no longer satisfies the form, the provider POST never happens, yet the one-use attempt has been consumed. This safe-but-unrecoverable user experience is avoidable.

## Core change

1. **Reuse** the original \`_exact_url\`, \`_approved_form\`, \`_form_sha\`, authenticated API, \`make_browser_packet\`, \`render_document\`, exact employer-rights ledger, final approval and persistent claim. Do not add another client, queue, database or submission engine.
2. Extract the exact existing input validation, official read-only employer form request, and reviewed field/letter construction into shared private helpers in \`smartploy/ashby_partner_submit.py\`. The original \`send_after_external_claim\` still calls them.
3. Add \`AshbyPartnerTransport.preflight_before_claim\`. After **all existing user rights, review, origin and document checks**, but before final approval/claim, it checks only the approved official employer posting and form digest; no name, email, PDF, covering letter or form answers are transferred. If the form changed or reviewed fields cannot satisfy it, the route returns a clear **409** while the applicant's claim remains unreserved. It cannot submit.
4. The original final-send operation repeats exactly the same official form check **after the claim is committed**, preventing trust in a stale preflight (TOCTOU). On later form drift, keep the existing sticky claim, require reconciliation and never silently send a second application.
5. The source review includes standalone \`httpx.MockTransport\` preflight privacy/invalid-input tests and real PostgreSQL + distinct OIDC user API tests for early form drift, valid path, synthetic provider ACK/503 and race drift. No outside employer requests or credentials.

## Reuse-first evidence

- First-party source: \`smartploy/ashby_partner_submit.py\` SP51, \`smartploy/api.py\` SP52, existing \`employer_final_action_gate.py\` and \`employer_submit_claim_storage.py\` unchanged.
- First-party synthetic Postgres/OIDC fixture and real HTTP route tests: \`tests/test_employer_submit_claims_postgres.py\` SP52.
- First-party provider-mock fixture: \`tests/test_ashby_partner_submit.py\` SP51.
- **New** only: a read-only preclaim method, factoring existing checks into shared helpers, an insertion at the existing authorized API boundary, and regression tests. All provider requests use current HTTPX; no third-party source copied or runtime dependency added.
- This prevents invalid-form attempts without weakening same-employer single-use identity. Time saved is **not measured**.

## Acceptance / non-claims

- On a changed form, no \`applicationForm.submit\`, no applicant-data transfer and no durable claim.
- On valid form, before the one actual provider POST the job form is checked twice; after verified provider acknowledgment, save the true provider application UUID as in SP52.
- If the form changes between preflight and final send, no provider POST; the sticky claim remains for manual reconciliation. The code does not automatically retry.
- The original Lever, manually reviewed Greenhouse/browser, source polling, agent and account-isolation behavior must remain unchanged.
- **This source patch does not activate employer rights or native ObumDelivery.** No actual employer receipt, applicant-submitted application, production rollout or background/unattended final-send permission is claimed.

## Independent release gates

1. Exact PR-head GitHub backend/PostgreSQL, React, browser/Chromium, Docker and receipt checks, followed by separate merged-main CI.
2. Authorized operator enrolls \`galapoto/smartploy\` in native ObumDelivery, runs pinned SHA positive and negative tests, records real worker/checkout evidence (platform issue \`obumai/obum-delivery#32\`).
3. Backup-first protected OVH deployment of the approved exact main SHA, image/source checks, release revision and rollback proof.
4. Real signed-in two-account CV-first/live source QA; explicit consenting-employer rights and real Ashby form review for one permitted job; individually authorized submission and actual employer acknowledgment before labeling AutoApply live.

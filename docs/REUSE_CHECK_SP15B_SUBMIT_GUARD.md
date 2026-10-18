# REUSE-CHECK - SP15b server attempt visibility and disabled unsafe final click

18 October 2026. DRAFT SOURCE ONLY. No permission to deploy or submit.

## Examined and reused before rewriting

- Existing SmartPloy SP15a PR #160 at a839b50438c1080e33b9b565fa3fadc1a36f3b3e: PostgreSQL one-shot claim, cross-source Lever job identity, owner/erasure locks, durable no-retry state. No second ledger built.
- Existing OIDC middleware, tenant_context, identity bindings and same-origin write protections: reused verbatim. No second authentication service.
- Existing SmartPloy browser packet, application workspace/receipt storage, CV PDF attachment, one-browser-profile Web Locks helper, Node/Chromium tests: reused. No browser framework, background extension runner or broad host permissions.
- Existing ApplicationStudio private read account-switch checks: new claim-state read shares the verified pre/post fetch boundary.
- Existing source inventory/reuse audit in draft project plan PR #150; no new third-party source, dependencies or copied code.

## Actual defect in source

The existing Chrome popup still clicked the employer Submit button under a Chrome-profile-only Web Lock without consuming the durable account-scoped server claim. A second device could therefore submit independently. The SP15a ledger alone cannot truthfully claim live cross-device exactly-one-click enforcement.

## Minimal safe change

1. Remove the active extension final-click function and handler. Keep approved form field filling, independently approved PDF attachment, local reviewed questions and inspection of historical local attempt receipts. Existing one-browser-profile lock helper remains reusable for a future authenticated protocol.
2. Permanently disable the popup Submit control in this draft at every checkbox, preflight, reset and event path. Users can still manually submit on employer site.
3. Add a read-only authenticated OIDC-cookie-backed employer-attempt status endpoint. Owner + workspace are resolved server side; any missing PostgreSQL or unverified account fails closed. Cross-origin/extension reads fail; no claim ID, CV, URL, email, session token or unverified submission metric is returned.
4. Recheck server claims at handoff readiness and browser packet issuance; an earlier attempt or database outage refuses fresh data packets for authenticated users.
5. Reuse Application Studio authenticated account-switch protection and display prior/uncertain claim state; disable fresh packet copy after a reservation. Add real Postgres/identity and synthetic frontend/browser contract tests.

## Explicitly unfinished

No final-action issuer or one-time browser redemption endpoint exists here, no new submission engine, no employer request, no site-permission attestation. Next step requires verified employer rights, one-use origin-scoped grant consumed just before a final click, safe client-to-companion delivery without copying account bearer/session tokens, two-device browser race tests, crash ambiguity reconciliation, erasure retention policy, actual ObumDelivery exact-SHA Woodpecker test and deliberate failing probe, and approved OVH deployment.

RELEASE HOLD: a server marker is not an employer receipt, and human-submitted applications remain self-reported until independently corroborated.

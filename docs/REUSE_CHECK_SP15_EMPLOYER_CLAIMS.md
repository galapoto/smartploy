# REUSE-CHECK — SP15a durable employer claim

Status: draft-review-only, 18 October 2026. No production deployment, no automatic employer submit.

## Existing source examined before new work

- SmartPloy obumai_dispatch_storage.py and migrations/017: reuse the atomic PostgreSQL INSERT/ON CONFLICT one-shot pattern and permanent uncertain state; do NOT reuse that AI-draft ledger to count actual applications.
- application_workspace_storage.py, browser_handoff.py, identity.py, account_erasure.py: reuse owner-bound workspace/revision, HTTPS Lever job verification, stable user/profile ID and quarantine lock order.
- browser_receipt_storage.py, applications CRM and first-party Chrome companion attempt-lock.mjs: check prior attempts while retaining per-browser Web Lock; do not create another browser engine.
- Previously examined internal and external candidates in docs/REUSE_FIRST_AUDIT_2026-10-18.md (draft plan PR #150). No third-party source or new dependencies copied.

## New minimal gap

smartploy/employer_submit_claim_storage.py plus migrations/019_employer_submit_claims.sql: separate durable unique account/profile/canonical-job claim AND a second uniqueness guard on normalized Lever organisation/job identity, even across source keys, /apply variants, host regions and tracking query strings. Claims survive changed CV revision and deleted/recreated workspace; no automatic expiry or retries. New account-erasure inventory entry. PostgreSQL source-of-truth checks account activity, quarantine, saved document, revision, application URL, current posting, receipts and legacy submitted CRM before atomic claim. No full CV, email, token or raw employer URL in the ledger.

The required explicit-user-approval and employer-rights flags are internal caller preconditions, NOT independently verified proof. No route is registered or permission surfaced to a browser. A row means only an unverified attempt was reserved, not that an employer received an application.

## Blocking next checks

Authenticated and CSRF-resistant end-user final-action endpoint; trusted employer/source terms; MV3 secure one-shot token binding (never place app bearer token in employer page or clipboard); user-owned browser preflight before actual click; two-device safety, account erasure retention/purge policy, verified receipt; actual ObumDelivery CI and independent release gate. Do not treat GitHub CI as OVH deployment or completion of SP15.

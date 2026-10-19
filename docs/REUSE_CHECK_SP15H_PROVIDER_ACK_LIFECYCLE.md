# SP15h: real provider acknowledgment must advance original application status

## Defect in already-built real core workflow

SP15f/SP15g can transmit an approved full CV and cover letter through an
employer-authorized official Lever Postings API and persist the returned
applicationId in smartploy_partner_application_receipts. HOWEVER the
original smartploy_application_workspaces row remained status=draft even
after a real provider ACK. This let the app display "Editable draft · not
submitted" and offered manual "I applied" / Save changes even after
an independently documented external application. The app's job-search
and document lifecycle would no longer represent the core function.

## Reuse-first, before writing any new code

- Reused (and adapted in place) original SmartPloy application workspace
  model and to_dict authority projection. Original blob:
  smartploy/application_workspace.py 501f3d385401dfd5915a3338332bff76448e8001.
  Reused original status=draft/edit/download/revision semantics, and
  preserved distinct self_reported_applied for user claims. No new
  application lifecycle table.
- Reused (and adapted in place) original owner-scoped SQL workspace
  repository and locked-row/optimistic revision controls. Blob:
  smartploy/application_workspace_storage.py
  019642541ab0f4441188709f2ebb6475b46a9991.
  Reused established Postgres connection, profile ownership, list/get,
  edit/report and deletion instead of adding a parallel CRM/status store.
- Reused existing SP15a immutable original employer attempt storage
  smartploy/employer_submit_claim_storage.py original blob
  a980c50913ae14fd7f14f70af2fb167baf62abd4.
  Its reserved_unverified or uncertain claim locks documents and manual
  status reporting until the result is reconciled. The revision + row
  check is intentionally performed AFTER the application-workspace
  FOR UPDATE row lock, in a second SQL statement, preventing stale
  READ COMMITTED results when a provider POST concurrently reserves.
- Reused SP15f original PostgresPartnerApplicationReceipts.record
  and Lever applicationId parser in smartploy/lever_partner_submit.py
  blob 823cb8e420081322f50b21c9094a54fff0be000d.
  The exact already-issued claim, provider ID and owner are reverified.
  The EXISTING provider receipt INSERT and EXISTING workspace UPDATE
  now commit in ONE transaction. No duplicative receipt/claim DB.
- Reused existing Application Studio component source blob
  06527ded000635a2809c218573b4ffa7654ce49a and
  web/src/types.ts blob 0d1ac72f18bcc50018cce365b67d331f4c421580.
  Existing signed-in account verification and review->submit button,
  saved list/detail, and private provider receipt are preserved.
  No new front-end framework, authentication or browser engine.

## Small missing functionality newly written (not copied)

- Migration 023 extends ONLY the original workspace.status CHECK
  constraint to include a third provenance-respecting enum value:
  provider_acknowledged. Idempotent constraint rebuild for existing
  migration runner, no new owner tables or PII.
- Shared original repository lock helper now checks the SP15a claim in
  a second statement after FOR UPDATE and blocks both document edits
  and false manual self-report on an attempted job. Existing users'
  self-reported status remains idempotent.
- Provider ACK receipt DB transaction now updates existing workspace
  to provider_acknowledged, preserving exact document revision, text
  and self_reported_* fields. If user intentionally deleted their
  workspace during the request, the exact provider ID still persists
  against the original claim for reconciliation.
- Existing Application Studio renders exact distinct state as
  "Sent · Lever acknowledged" in list/header/footer and an owner-only
  provider-ID detail section even after reload. It no longer shows the
  fake "SmartPloy has not sent this application" message, or editable
  draft or manual applied controls on an acknowledged application.
- Adapted current synthetic real Postgres/FastAPI/mock-Lever suite to
  verify receipt status in the repository and signed-in GET/list,
  revision preservation, no self-report marker, editing/re-report
  denied after provider success and after uncertain 429. Reused
  existing unit model tests and React component tests to distinguish
  provider acknowledgments from manual self-reports. No browser
  extension, new external dependency or live employer request.

## Ground truth and release gate

The full source SHA and exact five-job CI evidence must be posted to
SmartPloy acceptance issue #158, delivery ledger #88, native
ObumDelivery issue #32 and docs/PROJECT_PLAN.md after successful
verification. SP15g baseline is draft PR #166, SHA
d0e04035211fc381d7b77b3ea5b19c79b3e7c0e3, CI
https://github.com/galapoto/smartploy/actions/runs/39304284642
(689 Python/PostgreSQL, 95 React, 32 Chromium, 36 Node, Compose).

This is a SOURCE-only employer-confirmation lifecycle fix until the
project proves authenticated website/OVH main deployment, independent
employer partner rights & private API key and real provider applicationId,
native ObumDelivery exact-head green and negative RED probe. Never
call a test MockTransport application a real submission or claim a
hiring outcome merely because Lever returns applicationId.

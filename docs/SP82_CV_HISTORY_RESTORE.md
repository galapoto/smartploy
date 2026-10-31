# SP82 — Exact, owner-safe CV version restoration

Date: 2026-10-31. Redesign working-paper issue #243, CV & Documents recovery workstream.
**Stacked base:** SP80 `feature/sp80-structured-cv-editor-20261031` (which itself requires SP79, PR #244).
No production rollout, real employer action or account-level approvals are part of this change.

## User workflow

In **My CV & Documents → Create & edit your CV → Previous CV versions**, each archived revision has
**Download previous version** and the new **Restore version** control. Explicit confirmation explains
that active CV bytes will be replaced and the current saved version will remain in private history.
Unsaved text changes are specifically called out. The full original extracted text appears in the
editor immediately after the restoration, with the original media type and filename preserved.
A user can subsequently edit, save or export the restored master CV through the original SP79/80 UI.

## Reused and new source

- **Reused:** the original `smartploy_cv_files` active CV, `smartploy_cv_history` bounded version
  archive, per-profile PostgreSQL advisory write lock, same origin account-bound React mutation gate,
  exact CV SHA-256, OIDC binding and original CV-to-job-matching consumers.
- **New:** `restore_archived(profile_id, digest, expected_sha256)` for both in-memory and PostgreSQL
  repositories; a private, confirmed `POST /api/v1/profile/cv/history/{digest}/restore`; typed
  React client, explicit editor button, focused accessibility styles and regression tests.
- **No new** migration, model, external dependency, CV parser, file format, AI service, ATS transfer,
  employer permissions, browser capability, secret or hosted service.
- **REA:** NOT_APPLICABLE; authorized first-party source and version data are available directly.
  No third-party application recovered/copied; time savings not measured.

## Invariants / security

1. Restore requires explicit confirmation and a full exact digest of the currently active CV.
   Competing updates return **409**; no last-write-wins overwrite or automatic retry.
2. The chosen archive is looked up by exact digest **and** verified owner profile. A missing
   historic file returns **404**, including another user's historical digest.
3. Under the same per-profile write lock, the previous active document is archived, and
   the exact archived original bytes, media type, filename and extracted text are installed.
   The restored version is removed from archived rows, avoiding duplicates in history.
   When history is already full, the restore target is read before bounded archive pruning.
4. The immutable historic content checksum is verified against the selected SHA before mutation.
   No extraction/classification/reconstruction/translation occurs during restoration.
5. The HTTP write uses OIDC owner binding, expected user-ID and same-origin checks;
   personal response contents are `Cache-Control: private, no-store`.
6. No profile fact is approved, draft automatically prepared, CV or letter delivered to a
   third party, employer attempt reserved, browser click authorized or hiring event claimed.
   Existing application workspaces are not rewritten by a master-CV restore.

## Test plan

- Memory repository: complete-byte round-trip, stale revision, no cross-owner access,
  retained previous active revision, bounded history and safe deletion.
- PostgreSQL integration: 12-version archive edge case, same lock/CAS semantics,
  old original DOCX bytes, isolated profiles and integrity guard.
- FastAPI: confirmation, extra-payload rejection, stale revision, missing version, no
  employer actions/profile approval, current CV download restored to exact bytes.
- OIDC/PG: two distinct subjects with identical email, wrong-origin denial and
  successful first-owner-only restore.
- React: confirm/decline, exact old/new SHA, unsaved-draft protection, error state,
  no false save and immediate preview.
- Required CI: exact-head Python/Postgres, web, Chromium browser and isolated Docker stack;
  independent review and post-merge main acceptance before deployment.

## Release truth

This is an open source pull-request workstream. Only the source CI result on its
precise head and subsequent independent review can qualify it for merging. SP79 and
SP80 must land in order; after integration, SP78/SP81 changes must be reconciled
with the overlapping API/web files. Native ObumDelivery, pinned OVH release proof,
signed-in end-user acceptance and real employer provider acknowledgments are
**not** implied by this feature.

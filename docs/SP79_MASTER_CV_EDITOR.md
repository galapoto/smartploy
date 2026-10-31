# SP79 — Standalone master CV editor; private version recovery

Date: 2026-10-31. Plan: redesign issue #243, workstream A. Baseline:
\`main@0fc03d8b0236074d1fb6ab7606b0e94f8764ac7c\`.

## Functional change

- An applicant may create a CV from a blank document OR edit the **complete**
  extracted text from a previously uploaded PDF or DOCX, not only the earlier
  6,000-character preview. The editor offers named CV sections and a live,
  accessible preview. It does not automatically infer or approve experience.
- Explicit Save persists a **real DOCX** as the active CV, with an exact
  \`expected_sha256\` concurrency check. A stale tab gets HTTP 409 and never
  silently overwrites a newer version. A no-document candidate may create
  their first CV using an empty expected digest.
- Existing \`smartploy_cv_files\` active-CV storage is reused: CV-first job
  matches, manual workspace preparation, and opted-in draft agents already
  read it. The edited CV is therefore active in all existing paths.
- A transactionally archived copy of the **previous original** and subsequent
  saved versions can be downloaded privately. The archive is bounded to the
  twelve most recent distinct file revisions per profile. A CV deletion
  removes the current document and all archived versions.
- The master CV can be exported to A4 PDF or DOCX, using the existing
  \`application_workspace.render_document\` implementation. No external AI,
  employer site, training data or remote service receives document text.

## Requirements and proofs

- GET /api/v1/profile/cv/editor: entire owner-private text, exact active SHA,
  bounded revision history; private/no-store.
- PUT /api/v1/profile/cv/editor: explicit confirmation, bounded 20–30,000
  characters and exact SHA, verified same-origin account user binding in OIDC
  mode; never a job submission or profile fact approval.
- GET /api/v1/profile/cv/editor/download/pdf|docx: actual exported bytes;
  GET /api/v1/profile/cv/history/{digest}: exact archived original/version,
  owner-only; all downloads are no-store, attachment, and nosniff.
- Memory and PostgreSQL repositories use a compatible contract; PG upload
  and editor replacement serialize under a per-profile advisory transaction
  lock, with the previous file archived before replacement. The archive
  supports deleting personal CV history.
- Migration 028: smartploy_cv_history. Add it to owner-scoped erasure
  inventory and the known-owner table list.
- Regression cases include blank creation, original-document recovery,
  stale SHA, concurrent saves, no text truncation, strict payload schema,
  same-email OIDC subject isolation and no external submission.
- The editor is **not yet a fully structured field-by-field CV model**;
  section insertion plus text editing is the first functioning, reversible
  master-document slice. Structured sections, ordering and per-job variants
  remain tracked separately in issue #243.

## REA / reuse decision

REA_NOT_APPLICABLE for this work: complete first-party source and
first-party fixtures are available; no authorized opaque binary or
third-party app is necessary to recover behavior. Existing CV parser,
storage, CV-first matching, workspace/AutoDraft consumers and PDF/DOCX
renderers are reused; minimal new version archive, save/export API,
editor UI and tests were authored. REA was not run and no savings are
measured. No third-party code, software packages, fonts or assets were
copied. The original first-party source remains under its existing license.

## Release separation

This is a branch and PR deliverable. A green GitHub run is not proof of
Woodpecker qualification, independent review, protected main, pinned
OVH deployment, authenticated live applicant acceptance or a genuine
employer acknowledgment. No employer automated submission was enabled.

## First-use navigation

The initial chooser now presents an explicit **Create CV from scratch** action alongside upload. This opens the new master editor without a prior CV or any employer submission; ordinary job browsing remains available.

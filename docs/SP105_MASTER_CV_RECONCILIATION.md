# SP105: Current master CV → deliberate job-draft reconciliation

**Date:** 2026-11-01. **Starting SHA:** fcc048c7f4b5c498863143567c7306df1d782ada on already-source-green SP104 PR #271. This is a separate stacked PR, not a production deployment. The stack is SP101–103 #270 → SP104 #271 → SP105.

## Gap / user journey

A job-specific ApplicationWorkspace stores an immutable `source_cv_sha256` at creation time, but the active owner master CV can subsequently change. Prior UI left saved, carefully edited job CVs intact (correctly), without telling applicants the source version differs or offering a safe way to compare and update their job-specific CV. This makes the Assisted review and Automatic preparation workflow less trustworthy.

SP105 implements an **explicit, owner-private Compare → Choose → Review → Save** route inside the *existing* Application Studio:

- Parent passes the currently loaded master CV summary. If both SHA-256 digests are present, the UI reports an unchanged or outdated source with accurate wording. Missing digests are **unknown**, never represented as "current".
- The applicant deliberately clicks Compare to retrieve the complete private master CV using the existing `getCVEditor()` API, with owner/session verification *before and after*, exact current SHA check and all read-only/non-approval attestations validated. No external/AI/employer operation occurs.
- The reusable `DocumentComparison` preview displays complete job-specific CV and master CV side-by-side without persisting changes.
- The applicant can explicitly replace **only** the unsaved job-specific CV text after an extra confirmation. The full cover letter remains as written. This action is editor-local until the applicant clicks existing Save changes, which increments the server revision and requires new final review.
- A late response is discarded when the master SHA, selected job, session, or component changes. Server-side submission, employer permissions and one-use attempt checks remain independent.
- Existing, intentionally tailored older CV drafts may still be reviewed and used. Master CV mismatch is **a warning, not a fake authorization or universal submission block**. Once a job CV is updated, its source provenance SHA continues to record original creation; editing the job CV does not rewrite historical source metadata.

## REA-FIRST-001 / reuse

`REA_NOT_APPLICABLE`: the missing behavior is first-party React composition over already authorized, readable, owner-private `getCVEditor`, `ApplicationStudio.runPrivateAction`, `DocumentComparison`, `editApplicationWorkspace`, and original SHA lineage from `smartploy/application_workspace.py`. No external executable, proprietary app, web recording or binary is involved; REA tool revision / permission target: N/A. No source copied from nonowned projects, no dependencies added. Reused existing security/editing proof; savings=unknown.

## Validation / outstanding

Run exact-SHA frontend tests, full Python API/real PostgreSQL contract tests, synthetic Chromium browser tests, Compose smoke and exact-checkout review receipt. Add positive copy-and-save flow, stale SHA, in-flight draft switching, account-switch rejection, no-save/no-employer-call tests. Keep source branch review-only pending predecessor PRs, independent review, ObumDelivery gates where required, real two-account acceptance, approved immutable production release and frontend/backend revision parity. No claim of live employer submission.

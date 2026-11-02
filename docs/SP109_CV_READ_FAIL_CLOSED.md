# SP109 — Fail-closed CV availability and safe retry

**Base:** integrated SP101–SP108 review candidate `034cc9e0d6a9cd1b9b9cde6723df0175405ced80`.
**Target:** the existing release candidate branch, not production or `main`.

## Problem and result

An intermittent owner-private `GET /api/v1/profile/cv` failure previously became the same frontend state as a confirmed `{present:false}` CV. An applicant could be prompted to upload/create a new CV even though the existing document had not been checked. This is particularly confusing in the required CV-first Manual / Assisted / Automatic entry.

SP109 distinguishes a verified missing CV from an **unavailable CV check**. The unavailable state explains that the original file may still exist, blocks application-mode selection and CV upload/replacement/deletion, hides the master editor, and offers an explicit retry. General vacancy browsing remains available. A successful session-verified retry restores normal UI based only on the actual `getCV` result. The private CV is never cached in local storage. No employer submission, partner permission, autonomous action or existing workspace revision is changed.

The profile page has the same unavailable-state guard, and even manually triggered hidden file-input change events do not call the upload API during an unreliable CV check. Network read failures are not misreported as document erasure.

## Verification and release safety

Synthetic React regressions cover failed CV read, disabled Manual/Assisted/Auto choices, no false upload/create prompts, inaccessible CV mutation path, screen-reader error association, retry, and recovery of the existing CV. Exact-head CI is required before review and deployment. Existing separate approval, production identity isolation, privacy, backed-up immutable release, Woodpecker/ObumDelivery and two-user acceptance gates remain mandatory. This PR does not merge or deploy the release candidate.

## REA-FIRST-001

**REA_NOT_APPLICABLE** to already-owned readable first-party React API, loader, account-gating and Vitest code. No third-party executable, competitor behavior or asset is required. Reused and adapted: `App.tsx::load`, `StartChoices.tsx`, `getCV`, `load(true)`, private mutation fences, existing error/ARIA styles and tests. New code: the CV-read-state branch and its negative/recovery tests. No runtime dependency. Engineering-time baseline and savings unknown.

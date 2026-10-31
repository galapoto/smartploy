# SP78 - Redesign implementation: finished cover-letter prose and safe CV intake

## Plan subpart and baseline

- Product paper: 31 October 2026 working paper, sections 7, 10, 11, 13, 17 and 27.
- Baseline: main at 0fc03d8b0236074d1fb6ab7606b0e94f8764ac7c.
- First vertical slice of the revised redesign: finish a real document from confirmed job-matched facts while retaining existing owner/revision/approval boundaries.
- Branch: feature/sp78-finished-evidence-cover-letters-20261031.

## Actual behavior in this slice

1. **Explicit user-triggered letter proposal:** reuse the existing signed-in, owner-scoped and revision-checked POST /api/v1/application-workspaces/{id}/letter-proposal, with its source-current / fingerprint and original browser-receipt checks.
2. **Complete prose:** the deterministic composer now returns natural paragraphs in Finnish or English. No coaching instructions, bracketed placeholders or evidence-bullet lists appear in the proposed letter body.
3. **Evidence separation:** the response separately returns complete, missing_information, evidence_fact_ids and review_notes. The response is still unsaved and requires owner review and explicit Save; the API executes zero employer actions.
4. **Safe fallback:** when no relevant approved evidence or a unique approved name exists, complete is false and the exact missing information is returned outside the letter. The generated document never invents qualifications or personal motivation.
5. **CV intake:** a text CV over the same 30,000-character workspace limit now fails explicitly rather than silently truncating the last content (potentially a negation or dated qualification). Existing local-only PDF/DOCX import is retained.

## Reuse inventory and REA decision

- **Reused unmodified:** first-party candidate scorer matched_evidence_ids, approved profile fact IDs, tenant-bound workspace repository, editor save/revision UX, current-job fingerprint checks, same-origin action gate, browser receipt/one-use employer claims, and PDF/DOCX export.
- **Adapted:** existing letter-proposal response and its editable React panel, and CV import's final validation.
- **New:** small deterministic complete-letter module, negative tests and documentation.
- **REA_NOT_APPLICABLE:** all affected first-party SmartPloy sources and contracts are available. The authorized behavior gap is directly observable; an external opaque binary/recorded API is not involved. Canonical REA project: morluto/rea, MIT, last reviewed for this task via its public README. REA was not executed; no code or runtime recovery or saved time is claimed.
- **License:** no new third-party code, fonts or dependencies copied; reuse is from this first-party repository.
- **Measured time saved:** unknown.

## Safety boundary and deliberate limitation

The initial new_workspace template still contains explicit review markers. This is intentional for this first additive rollout because existing browser/provider readiness uses those markers to block unreviewed initial packages. Changing initial generation to ready prose **must** be accompanied by a persisted explicit-review state and a corresponding transactional employer-send preflight update, rather than silently bypassing a safety gate. The on-demand complete letter is inserted as unsaved edits and cannot enter an employer attempt until the user explicitly saves and completes the original independent approval path.

There is no master-CV structured editor, new employer route, batch-submit authority, or production deployment in this slice. Those belong to subsequent tracked implementation phases. This document does not claim that Automatic currently sends everywhere.

## Acceptance and release evidence required

- Pure composer: bilingual, relevant approved facts, missing information outside prose, hostile posting, no invented achievements, no truncated negations.
- Existing API: two-subject same-email OIDC isolation, stale revision/account switch/source drift, no employer actions, no persistence until Save.
- Existing browser final action tests and frontend editor tests must remain green.
- CV DOCX import: an extracted CV over 30,000 characters fails visibly rather than silently losing content.
- Exact PR-head 5 GitHub checks, independent review, post-merge main checks, ObumDelivery/Woodpecker qualification, pinned OVH deployment, and signed-in acceptance are **separate** steps. No claim of deployment or live employer submission is made by a source commit.

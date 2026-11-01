# SP95 — Review every loaded supported AutoApply draft without hidden candidates

**Baseline:** deployed production and main `cb20d7b04730e711887a463858531bacb4069355` (SP94), 1 November 2026.

## User-visible defect

The original `AuthorizedAutoApplyBatch` deliberately limits a single employer-rights
check to 12 saved candidate jobs to bound API calls. It always takes the first 12
drafts. When an applicant has 13 or more saved supported Lever/Ashby drafts,
later candidates cannot be inspected or selected for a reviewed AutoApply
batch, even when the user's account has permission to access them.

## Implementation and safety

- Reuse the current saved, owner-scoped `ApplicationWorkspace[]`, original
  `providerForUrl`, `getLeverPartnerReadiness`, `getAshbyPartnerReadiness`,
  independent rights/review checks, `verifyAccount`, and final one-shot
  `submitAuthorizedAutoApplyBatch`. No new API, worker, provider transport,
  permissions, CV storage or dependency.
- Show the number of **loaded** supported ATS draft candidates and a clear
  `Drafts 1–12 of N` page range with accessible Previous / Next controls.
- Preserve the existing **12 employer-readiness checks per deliberate page**.
  Browsing pages makes no partner API requests and never sends to employers;
  the applicant must explicitly press the original check button on each page.
- Page changes clear the previous exact-job rights snapshot, checkbox picks,
  review approval and data-transfer approval. Disable navigation during a
  running eligibility read or one-shot send. Each eligible batch retains the
  original three-job limit, revalidation, signed-in subject checks, employer
  rights and sticky no-retry claims.
- Reset to page one and revoke all page approvals when account identity,
  workspace revision/status or posting URL changes. Never persist eligibility,
  private documents or consent in browser storage.
- The page range covers **loaded workspaces only**; it is not a claim that
  every older application is loaded. Ineligible hosts remain Assisted / Manual,
  and a draft is not an employer submission.

## Reuse and REA decision

**Existing first-party code reused:** `web/src/AuthorizedAutoApplyBatch.tsx`,
`web/src/ApplicationStudio.tsx`, `web/src/api.ts`,
`smartploy/api.py` partner eligibility and original one-shot sender. New
code is only browser page state, candidate slicing, accessible navigation and
a regression test in the existing Vitest suite. No third-party code copied.

**REA_NOT_APPLICABLE:** the exact authorized source, data contracts and
behavior are readable in the existing repository. There is no authorized
opaque application, binary or API to reconstruct for this narrowly scoped
change. REA tool revision/evidence: not used; permission to inspect
third-party sources is not assumed. Engineering savings: unknown (no
comparable measurement).

## Acceptance gates

- Existing Vitest cases must continue to prove applicant approval, employer
  rights, exact document-hash checks, and account verification.
- New regression: 14 loaded candidates, exactly 12 rights requests on first
  page, later two accessible only after explicit navigation/check, and no
  inherited approval or outbound employer application.
- TypeScript + production web build, full Python/PostgreSQL suite,
  Playwright Chromium, isolated OIDC Compose and exact-checkout CI remain
  mandatory before merge.
- Merge does **not** deploy the page controls. Live OVH requires its own
  approved exact merge SHA, backup/migration/provenance/health and online
  release evidence, then authenticated applicant visual acceptance.

## Progress

- **DONE in source:** bounded page navigation and regression coverage.
- **IN PROGRESS:** exact-head CI / independent review.
- **NOT STARTED:** OVH deployment and signed-in two-account acceptance.
- **BLOCKED externally:** any real employer send without independently
  authorized employer integration, reviewed documents and applicant final approval.

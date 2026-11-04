# SmartPloy RC — SP101 to SP107 consolidated review and release checklist

**Prepared:** 2026-11-02. **Existing main baseline (verified before this PR):** `804747bd9f01f999f9e806dcf96459bb215bb8f1`.  
**Pre-integration source head:** `b2f94ed1489d0d5dab8eefb9d71b1c393fd9f72a` (source-green SP107).  
**Integrated PR head and resulting main SHA:** **read from GitHub at decision time**, never copy an obsolete hash.  
**Review status at creation:** independent approvals outstanding, no production deploy. This plan is **not** approval.

## Scope — one deliberately combined changeset

The five source-tested changes are linearly stacked on `main` (verified compare: **ahead 28 commits, behind 0** before the additional integration test and this document). They are not five unrelated cherry-picks and have no known divergent base. Integrating the exact tested linear ancestry in one separately reviewed PR avoids applying the same code five times or losing a follow-up in an intermediate deployment.

| Component | Prior review PR | Source-green head | User-visible or privacy behavior |
| --- | --- | --- | --- |
| SP101–SP103 | [#270](https://github.com/galapoto/smartploy/pull/270) | `f7a3f4098c40593d405681f71134dafdc683b303` | CV writes fence off stale matching and preparation; previous selected jobs cannot survive a CV replacement |
| SP104 | [#271](https://github.com/galapoto/smartploy/pull/271) | `fcc048c7f4b5c498863143567c7306df1d782ada` | Unsaved CV and cover-letter text protected before sidebar, refresh and browser navigation |
| SP105 | [#272](https://github.com/galapoto/smartploy/pull/272) | `431de3cccdf539ce5470518c513ecaddb0295732` | Compare updated owner master CV and job draft; explicit copy, undo and revisioned private save; historical provenance retained |
| SP106 | [#273](https://github.com/galapoto/smartploy/pull/273) | `575b827e1511161c8c9f4857baca759e775895c1` | Save one complete CV + letter ZIP with true PDF and DOCX files; no employer action |
| SP107 | [#274](https://github.com/galapoto/smartploy/pull/274) | `b2f94ed1489d0d5dab8eefb9d71b1c393fd9f72a` | Owner-scoped, exactly revisioned inline PDF previews of saved CV/letter; stale and cross-account requests refuse |

All five features are available in **this integrated PR's source**, not automatically in production. Preserve existing sidebar, panorama, dark/light mode, and CV-first Manual / Assisted / Automatic chooser. Design-only draft PR #269 is explicitly **out of scope**.

## New RC cross-account acceptance evidence

A single additional FastAPI integration test in `tests/test_authenticated_account_switch.py` exercises the real **OIDC production-mode tenant routing** with two synthetic, individually authenticated users who share the same email but have different issuer subjects. Each has a different private CV/letter, including an intentionally identical opaque workspace ID, using the actual first-party repository and document rendering endpoints.

- Both users receive their own actual **PDF text** and complete **ZIP/DOCX text**, never the other's text, even for an identical workspace ID.
- Owner-only cases return **404** to the other account for both endpoints.
- Stale PDF revision returns **409**; an unauthenticated request returns **401**; data remains private/no-store and **actually_submitted** remains zero.
- No live user accounts, real CVs, external provider or employer submission appear in this test.

The RC must pass the original complete Python + PostgreSQL synthetic AutoApply contract, React tests/build, Chromium/Playwright tests, Compose smoke and exact-checkout review receipt at **its own final exact SHA**. PR-only green checks are review evidence, **not** post-merge main evidence.

## Real PostgreSQL identity and binary-document isolation (release hardening)

The additional `tests/test_rc_postgres_document_isolation.py` runs against the CI's actual migrated **PostgreSQL 17** service (guarded by `SMARTPLOY_TEST_DATABASE_URL`), not the in-memory workspace simulation. It constructs two separate OIDC principals with the **same email** and distinct subjects, resolves them using `PostgresIdentityRepository`, creates actual `PostgresSessionRepository` cookies and persists distinct private workspaces through `PostgresWorkspaceRepository`. The authenticated FastAPI app itself uses the PostgreSQL DSN.

- Each account can view **its own actual rendered CV and cover-letter PDFs**, read its standalone DOCX, and download a five-entry ZIP containing the correctly isolated PDF+DOCX documents. All formats are parsed, so mere HTTP 200 cannot pass the test.
- Both signed-in accounts receive **404** for the other owner's workspace URL, across inline PDF and ZIP routes; stale exact PDF revision is **409**; anonymous requests are **401**. All authenticated binary responses are private/no-store, and `actually_submitted=0`.
- An intentional attempt to insert the *other* account's opaque workspace ID is **rejected by PostgreSQL with a unique constraint**. This differs from the memory-fixture collision used by the earlier source test: `migrations/011_application_workspaces.sql` has `workspace_id TEXT PRIMARY KEY`. The production test therefore never claims two physically identical keys can coexist in the real SQL table.
- The synthetic test uses uniquely generated test subject/workspace identifiers and only the **isolated test database**. Cleanup deletes only its own workspace and identity rows. No real external OIDC request, employer transfer, private production key or customer data is required.

This is stronger source verification, **not** evidence of a real OVH login or production deployment. The GitHub CI job must pass at the current *revised* RC commit; the earlier head `bf216178...` no longer qualifies after this hardening change.

## SP108 — revision-bound CV, cover-letter and ZIP exports

The new complete package originally accepted the current workspace ID but could export a newer revision after a second device saved a change. **SP108** requires expected_revision on the new ZIP endpoint and returns 409 for an owned stale revision or 422 for a missing/invalid revision. All four individual saved CV/letter PDF/DOCX download links in the UI now also pin the applicant-reviewed revision; the existing per-document API remains backward compatible if an older client omits that parameter. All five links are disabled and unfocusable during unsaved edits or saves, or when download authority is missing.

Tests cover the revision-aware URL builder, real PDF/DOCX/ZIP responses, stale/missing/invalid version refusal, in-memory and PostgreSQL two-account OIDC scope checks, and actual browser stale ZIP-link rejection after saving. No employer request or external permission is granted. Reuse-first decision: REA_NOT_APPLICABLE for first-party existing SP107 revision helper, ZIP/PDF/DOCX renderer, database access and React editor. Savings unknown.

## Release gates — do not skip

- [ ] Independent code/privacy reviewer examines **cumulative diff against `main`**, including server response headers, account scopes, owner/DOCX/PDF/ZIP identity checks, unsaved editor protection, and employer rights controls.
- [ ] Explicit owner/Director GO for merge/release is recorded in the canonical approval channel. The author/agent does not self-approve, infer approval from green CI or silently advance any protected branch.
- [ ] Confirm `main` baseline did not move; if it moved, reconcile diffs and rerun exact integration tests. No force push or blind merge.
- [ ] **After merge**, confirm push-to-`main` CI is green at the exact resulting 40-character immutable SHA. Require `test`, `web`, `browser` and `deploy-stack`; the review-only receipt does not qualify as a release approval.
- [ ] Collect native ObumDelivery/Woodpecker exact-SHA and negative/permission evidence where the deployment process requires it. No synthetic pass is substituted for its independent approval.
- [ ] Authorized operator performs backup, image identity/health/OIDC checks and pinned-SHA release with `deploy/personal/scripts/deploy.sh`; no unreviewed moving-ref checkout. Validate web/backend/worker revision parity and rollback safety.
- [ ] Run actual signed-in user acceptance in **two independent user sessions**: CV upload/edit → choose Manual, Assisted, Automatic → current matched jobs → full job-specific CV and complete cover letter editor → save/reopen → ZIP/DOCX/PDF preview → account isolation.
- [ ] Check disabled previews/ZIP while unsaved, stale version 409, missing owner 404, and preserved review intent on navigation. Do not upload or publish test CVs or private response bodies as release evidence.
- [ ] Verify source freshness and KEHA job count separately from UI readiness; verify explicit applicant final action and employer-specific rights for every real transfer. A prepared draft, ZIP, browser observation, synthetic AutoApply test or UI "Applied" marker **does not prove an employer received an application**.
- [ ] Record a nonsecret release receipt in [tracker #88](https://github.com/galapoto/smartploy/issues/88) and [go-live issue #57](https://github.com/galapoto/smartploy/issues/57): SHA, deployment time, backup evidence/checksum, verification gates, source count, UI acceptance, precise remaining limitations. Never include OIDC cookies, CV text, partner tokens or production keys.

## Release/go-no-go summary

**DONE at creation:** feature source for SP101–SP107 exists and their prior component-PR exact-SHA CI passed; the cumulative branch is linear from the stated baseline.  
**IN PROGRESS:** the real-memory and real-PostgreSQL OIDC two-account document tests and the consolidated **PR-to-main** exact-head CI.  
**BLOCKED:** independent approval, native release CI evidence where designated, post-merge main CI, operator production deployment and signed-in two-account acceptance.  
**NOT STARTED:** any actual employer submission under this RC. No automatic ATS rights granted.

## REA-FIRST-001 reuse decision

`REA_NOT_APPLICABLE` for this *integration-only* slice: no opaque upstream binary, competitor application, API recording or licensed external asset is a candidate for reconstructing the already-owned tested SmartPloy history. The work reuses **100% of the existing first-party SP101–SP107 implementation**, FastAPI tenant/context and owner-scoped workspace repository, standard PDF/ZIP/DOCX renderers, `MemoryIdentityRepository`, `MemorySessionRepository`, and synthetic authentication test setup from `tests/test_authenticated_account_switch.py`. New code is only the combined real-identity cross-account regression and this review/release manifest; no runtime package added. Source/permission: owned repository baseline above; REA executable target/tool version: N/A. Engineering time versus comparable measured baseline unknown; **savings=unknown**.

## Integration alternatives

This RC offers **one cumulative review and merge path**. The five component PRs remain individually reviewable as detailed evidence; do **not** merge this RC **and** subsequently re-apply all five feature PRs to `main` without comparing histories. After an independently approved RC merge, close redundant component PRs as superseded with an explicit link, preserving their review discussions and CI history. If independent reviewers instead choose staged merges, keep this RC unmerged and rerun post-merge CI at every resultant main SHA.

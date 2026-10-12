# SmartPloy SP-116 integration evidence — non-merge acceptance branch

**DO NOT MERGE THIS BRANCH INTO MAIN.** It is a disposable CI-only
integration snapshot of independently reviewed/review-pending feature heads.
Source pull requests remain the authoritative merge units; changes made here
must be ported back to their source PRs before any production integration.

## Exact feature inputs

- Search preference mutation privacy: PR #112 at `394ac40aa40a5433149657e85b9a0c7ab781986d`
- Private CV/fact/application action privacy: PR #115 at `c8a0905570e680d92590d9fdc74994d08fc9b699`
- Private user bookmarks backend and migration: PR #117 at `6ceb9b29e1914ebc5c335737fe1b0f5bf14e8028`
- Account-private saved jobs UI: PR #118 at `17e82ac9c5d4b92e5b2302f6ed704510e37e7a2f`
- Operator-only shared ATS source/ingestion API: PR #119 at `2b73d2b44a227ba488b5a28ccd025e54ca0651a6`

## Composition

Starting from PR #118's head (containing #112 and #115), this branch
overlays the private-job repository, SQL migration, test module and private
API routes from PR #117, plus the operator allowlist, service-only Docker
environment, test module and shared source API guard from PR #119.
The `smartploy/api.py` composition is not an independent feature.
Only the source PRs may be merged after external review and refreshed exact
main CI. CI of this branch is a **pre-merge compatibility check**, not review
approval and not a replacement for the merged-main release gates.

Expected invariant: a user-added job is private and never affects global ATS
job counts or listing matching, while the operator-only endpoints that
*can* alter the shared catalog reject an ordinary authenticated user.
No real applicant data, Cloudflare configuration, employer submissions,
production DB or worker feeds are changed.

## Acceptance

- [ ] Python/PostgreSQL including private jobs, same-email owner isolation,
  Cloudflare and OIDC operator admission/denial
- [ ] React tests and build
- [ ] Synthetic Chromium first-use and private bookmarks scenarios
- [ ] Docker fixture migrations, image checks and backup/restore recovery
- [ ] Independent reviewer approval **of each source PR**, then exact-main
  merge checks and real owner-authenticated A1–A7 acceptance

Tracking: #88, #91, #116. Production SHA remains independently verified by
the operator; GitHub CI does not infer that an OVH release happened.

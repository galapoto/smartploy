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
- Disabled-account request gate and OIDC session revocation: PR #121 at `ba04e214ea1a3931eadc39157a7cafec9a53884a`
- Public health endpoint privacy redaction with unchanged release invariants: PR #122 at `6623f7308f3f9b926063b4733678fceefeef5e4c`
- OIDC cookie exact-origin write protection (stacked on #121): PR #123 at `7f8d32ec8539b4a0a849d4ca881a8e62e8335ea2`
- Confirmation-only GET logout and same-origin POST sign-out (stacked on #123): PR #125 at `2f00bbe5d2f73426a58ed1de6c9492dbceb78c48`

## Composition

Starting from PR #118's head (containing #112 and #115), this branch
overlays the private-job repository, SQL migration, test module and private
API routes from PR #117, plus the operator allowlist, service-only Docker
environment, test module and shared source API guard from PR #119.
It then overlays the verified request identity/status middleware and the
OIDC-disabled-account regression module from PR #121, with the API binding
changes applied to the existing integrated private-job/source API handlers.
It also overlays only PR #122's public-health implementation, web health
response schema, redaction tests and documentation; the existing authenticated
worker and private profile routes remain untouched.
PR #123 adds the exact-origin OIDC session mutation guard and synthetic
CSRF tests. The prior OIDC operator admission regression in
`tests/test_operator_access.py` is adapted here to send the legitimate
same-origin browser headers; port that assertion update into #119 or a
reviewed integrated main change before merging #123.
PR #125 replaces only the sign-out routes in this composed API, adds the
logout tests and linked Settings UX, and updates prior OIDC/logout assertions.
GET logout and GET logged-out pages are inert; only a same-origin POST may
revoke the browser session. This entire composition remains CI-only.
The `smartploy/api.py` composition is not an independent feature.
PRs #121, #122, #123 and #125 are also independently review-gated. Only the source PRs may be merged after external review and refreshed exact
main CI. CI of this branch is a **pre-merge compatibility check**, not review
approval and not a replacement for the merged-main release gates.

Expected invariant: a user-added job is private and never affects global ATS
job counts or listing matching, while the operator-only endpoints that
*can* alter the shared catalog reject an ordinary authenticated user.
No real applicant data, Cloudflare configuration, employer submissions,
production DB or worker feeds are changed.

## Acceptance

- [ ] Python/PostgreSQL including private jobs, same-email owner isolation,
  Cloudflare and OIDC operator admission/denial,
  disabled-account revocation, OIDC session reassignment denial,
  and anti-CSRF exact-origin cookie mutation checks,
  cross-origin logout GET/POST and server revocation outage handling
- [ ] React tests and build
- [ ] Synthetic Chromium first-use and private bookmarks scenarios
- [ ] Docker fixture migrations, image checks and backup/restore recovery
- [ ] Independent reviewer approval **of each source PR**, then exact-main
  merge checks and real owner-authenticated A1–A7 acceptance

Tracking: #88, #91, #116. Production SHA remains independently verified by
the operator; GitHub CI does not infer that an OVH release happened.

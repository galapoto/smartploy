# SmartPloy verified delivery fast lane (SP-11)

This workflow shortens feedback and review handoff **without** skipping privacy, browser, database, backup or rollback tests. It does not authorize any unattended production action.

## Measured baseline

GitHub Actions run [38524758751](https://github.com/galapoto/smartploy/actions/runs/38524758751), 14 October 2026, validated the then-current stacked SP-10 source candidate.

| Existing job | Observed runner duration |
| --- | ---: |
| Web / React | 23 seconds |
| Python/PostgreSQL | 58 seconds |
| Synthetic Chromium browser | 66 seconds |
| Docker image, migrations, four-service health, backup, restore | 77 seconds |

These jobs run in parallel. The Docker end-to-end rehearsal is the wall-clock constraint and **must remain mandatory**. Single-run timing is noisy: compare several successful runs under similar runner load before claiming a demonstrated speedup.

## Improvements

1. **Cancel superseded pull-request runs only.** Two runs for the same PR no longer consume separate runner slots after a new commit arrives. Push-to-`main` and manual workflow runs are never canceled by this rule. Do not replace the complete last-commit CI run with an earlier success.
2. **Cache npm download tarballs, not installed dependencies.** Both React and Chromium runners restore `setup-node`'s npm cache keyed to the committed `web/package-lock.json`. The original pinned npm 10.9.2 and `npm ci` still execute; integrity hashes, negative manifest/lock drift check and production Docker clean install remain unchanged. An empty/stale cache is not permission to skip an install.
3. **Overlap independent Docker setup.** Start the isolated PostgreSQL fixture while building the API/web images, then `wait` for **both**. Build failures, failed database readiness, migrations, API/worker/web health, image provenance, forbidden-access control, real backup and restore all remain hard failures. No production Compose configuration changes.
4. **Publish a review-only receipt after every mandatory job passes.** The dependent `review-receipt` job records the *actual tested checkout commit/tree*, any separate PR head SHA, the exact GitHub Actions run/attempt, required job results, and an SHA-256 checksum. It is read-only, carries no private CV/account/source secrets, has a 30-day retention, and never claims human approval or OVH release readiness. For PR events the tested checkout may be GitHub's synthetic merge SHA, not the PR branch tip. Inspect both before treating the source as approved.

Run the receipt generator locally only for testing/diagnostics; the ordinary Actions workflow creates the definitive CI-linked artifact on successful runs. Unit tests reject altered source SHA, missing jobs, failed jobs, incomplete event metadata, and claims that a PR head is the same as a synthetic merge checkout.

## Shortest *safe* route to production

Reviews and deployment prerequisites can be **worked on in parallel**, but their completion gates cannot be bypassed:

- **Security reviewer:** review the current **integrated canonical draft [#137](https://github.com/galapoto/smartploy/pull/137)** against the original scope and nested drafts (#129, #133–#136). Do not treat reviews of subordinate or superseded proposals as approval of the current unified source. Follow the [main branch protection runbook](MAIN_BRANCH_GUARD.md) and record the independent audit and current head SHA. This fast-lane is separate CI-only source; do not treat a passing automated receipt as an independent human review. Verify account/tenant isolation, CSRF/OIDC, private saved jobs, operator-only ATS writes, and negative tests before any approval.
- **Identity operator:** separately commission Obum Identity per [Projects #17](https://github.com/galapoto/Projects/issues/17), preserving existing Cloudflare Access until first-party discovery, callbacks, issuer/PKCE and recovery are proven. This is an external critical-path dependency, **not** solved by CI changes.
- **Authorized integrator:** only after review or an explicitly documented owner exception, integrate the exact reviewed source in the approved order, run fresh push-to-`main` complete CI, record the immutable new `main` SHA and compare the Git tree to the review receipt. Do not merge CI-only experiment harness PRs.
- **OVH operator:** separately approve a pinned-SHA, backup-first guarded deployment. Verify protected origin, images, storage, ATS continuity and rollback. CI's local Docker fixture is never evidence that OVH was deployed.
- **Two-account tester:** carry out live authenticated A1–A7 checks in [#91](https://github.com/galapoto/smartploy/issues/91), including logo, general/personalized job search, settings, two separate identities, mobile UX and original employer links. Synthetic tests cannot close this gate.

A successful CI receipt means **automated CI succeeded on a specific checkout**, nothing more. The review, acceptance, source authorization, human application approvals, production identity cutover and deployment states must be recorded separately in [tracker #88](https://github.com/galapoto/smartploy/issues/88).

## Speed/quality measurement

Compare `web`, `browser`, `test`, and `deploy-stack` duration and first failure detection latency against the baseline above; track the number of superseded PR runs canceled. Fewer repeated installs or canceled obsolete runs are useful, but do not promise a faster end-to-end delivery until several fresh exact-head runs and owner-controlled release steps demonstrate it.

**Out of scope:** live Cloudflare or OIDC changes, Docker image/version changes, private ATS polls, user account writes, CV data processing, production deployment, and employer application submission.

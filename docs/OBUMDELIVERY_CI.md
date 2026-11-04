# SmartPloy -> ObumDelivery: scoped, review-only product qualification

ObumDelivery owns a Woodpecker 3.19 CI controller and isolated KVM
worker. SmartPloy retains ownership of its product source/tests.

This file is a source-level enrollment proposal. A checked-in workflow
does NOT prove the running CI controller has enabled the repository,
execute a pipeline, deploy a product, or authorize Cloudflare/DNS/AI changes.

## Admission prerequisites

1. Platform operator independently confirms isolated worker host/VM,
   its separate Docker socket, private controller channel, and both a
   successful and a deliberately failing native ObumDelivery pipeline.
2. The running WOODPECKER_REPO_OWNERS must include owner galapoto;
   WOODPECKER_ORGS remains obumai for sign-in eligibility.
   Repo ownership admission does not grant deployment permission.
3. GitHub OAuth app grants repository access; the authorized Woodpecker
   admin activates exactly galapoto/smartploy in ci.obumai.com. The
   platform source inventory must remain disabled until verified. Operator
   must explicitly enable **Allow pull requests**, keep forked PR execution
   behind an independent approval, verify the runner is KVM-isolated and all
   PR secret/event policies deny credentials and privileged trust flags.
   Source YAML cannot activate repository webhooks or project settings.
4. For an independently reviewed emergency release, run the existing SmartPloy workflow manually on the exact approved
   review branch, supplying nonsecret Woodpecker pipeline variable
   `OBUMDELIVERY_EXPECTED_SHA` equal to the **full 40-character reviewed
   candidate commit**. Woodpecker 3.19 manual-run API selects a branch,
   not a commit SHA: it cannot itself guarantee an immutable checkout.
   `scripts/obumdelivery_ci_gate.py` refuses a missing, malformed or stale
   expected SHA before executing native product tests. Independently
   compare the returned pipeline's `commit`, checked-out Git HEAD and
   recorded tree with the reviewed candidate, and refuse promotion if
   any value differs. Do not create a no-op branch push to force tests.
   Verify native Python/Postgres + bilingual synthetic quality gate,
   React build/Vitest, synthetic Chromium/Playwright and companion checks.
   For routine feature PRs targeting main, FEATURE-FIRST-001 adds the same
   **source-only** checks as a dedicated `pull_request` event path. The
   entrypoint rejects non-main targets, invalid PR number, and trusted
   runner network/volume/security privileges. CI_COMMIT_SHA must match
   checked-out git HEAD. A PR checkout may be a synthetic merge commit:
   independently relate its source and parents to current PR head before
   claiming acceptance. PR green remains `CI_QUALIFIED`, not release GO.
5. Check the no-overwrite stage receipts and final JSON HOLD policy.
   The deliberate negative test with CI_NEGATIVE_PROBE=1 must turn red.
   Unset after the experiment. An accepted source SHA does NOT authorize
   deployment even if every product test is green.

## Test contract

The Woodpecker file is .woodpecker/smartploy.yaml. It accepts explicit
manual builds, push-to-main and `pull_request` targeting main **only after
native project webhook/PR admission is enabled and separately verified**.
An older SP15j push filter is retained for backwards compatibility;
unrelated branch pushes remain excluded.
Build runner selector is isolated-build. PostgreSQL is a temporary fixture
with a literal synthetic password inside the isolated CI network.
Playwright image v1.55.1 matches the locked Node dependencies; tests
launch a local fake API and localhost browser. No real applicant CV,
model prompt, employer submission or production database is accessed.

scripts/obumdelivery_ci_gate.py validates CI_REPO and exact CI_COMMIT_SHA
against git checkout, plus its Git tree. On manual events it additionally
requires `OBUMDELIVERY_EXPECTED_SHA` and records `expected_review_sha`
in each stage receipt. For pull_request it additionally requires exact
main branch metadata, a numeric PR identifier and all three untrusted
runner capability flags false. Push-to-main source tests continue unchanged;
other CI events fail closed. Two sequential stages must leave matching redacted
receipts; final aggregate denies release even when product tests pass.
All receipts are in ignored .ci-out/obumdelivery.
Do not upload unreviewed workspace files, credentials or data dumps.

## Important separation of test and release duties

The isolated CI worker does NOT execute SmartPloy's production Docker
Compose smoke/backup/restore; the existing GitHub Actions deploy-stack
test independently covers an isolated production-like fixture.
Do not misrepresent that as an ObumDelivery pipeline stage.

Trusted production rollout requires a separate operator with deployment
authority. Required preconditions include independent security/privacy
review, explicit source terms, real two-account QA, protected/reviewed
merge into main, immutable merged-main SHA checks, full private backup,
rollback plan, safe host resource checks, access/identity continuity,
guarded deploy script and post-release image/health/source checks.

Never mount the production host Docker socket into ObumDelivery's VM,
grant production SSH/DNS secrets to CI source, or deploy a draft directly.
Keep unattended ObumAI preparation off, preserve Cloudflare Access until
OIDC acceptance, and never submit a real employer application in CI.

## Status as inspected on 4 November 2026

- SP115–SP122 application candidate [PR #289](https://github.com/galapoto/smartploy/pull/289)
  passed its five GitHub Actions checks at head
  `5ce35e1562225c24cd664fc229c0d1f5cf8e27d4`.
  It remains a separate, unmerged production candidate.
- This source change **only** enables safe `pull_request` event admission in
  the original Woodpecker workflow and adds a fail-closed native metadata gate.
- ObumDelivery project enrollment/PR events and real native test runs:
  **NOT YET VERIFIED** by this source change. Require a real positive
  native run and a deliberate negative control linked to exact SHA.
- Independent review, protected main qualification and OVH production
  deployment: **NOT EXECUTED** by this change.
- FEATURE-FIRST-001 requires immediate qualified per-feature release,
  not automatic bypass of CI, role/privacy approval or recovery.

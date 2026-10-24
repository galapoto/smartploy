# SmartPloy release candidate and continuous progress contract

Source of truth for development milestones: [SmartPloy master tracker #88](https://github.com/galapoto/smartploy/issues/88).
Use this runbook in combination with \`docs/OVH_COMPOSE_DEPLOYMENT.md\`, not as a replacement for its guardrails.

## Release evidence is commit-specific

A source branch changing is **not** evidence of a failed service deployment.
A previously issued exact-SHA operator command stopped on 2026-10-11
because another approved PR advanced \`origin/main\` from
\`d5f82f3f89aba0262d01846b2d388642ec723b43\` to
\`738b4c119b610b5376a951519aac0204e92e6cec\`. The early
\`test origin/main == expected SHA\` protected against accidental drift,
but made an already reviewed immutable commit undeployable once another
agent merged an unrelated commit.

**Never silently switch** an operator's intended release to a newer moving
branch tip; **never deploy** an unreviewed commit just because it is latest.

The GitHub \`Smartploy CI\` workflow now runs on:
- pull requests (pre-merge checks);
- pushes to \`main\` (exact resulting merged commit);
- explicit manual workflow dispatch.

Release decision must reference the exact immutable commit SHA and the
**successful push-to-main CI run for that SHA** with four green jobs:
\`test\`, \`web\`, \`browser\`, \`deploy-stack\`.

Older PR-only results do **not** prove combined post-merge code passed.
A merge to \`main\` is not an OVH production deployment.

## Safe pinned release on obum-core-01

**Owner/operator**, after inspecting that commit's exact push-to-main CI
results and approving the release, replaces \`<REVIEWED_TESTED_SHA>\` below:

~~~bash
set -Eeuo pipefail
REPO=/srv/obum/stacks/smartploy
SHA=<REVIEWED_TESTED_SHA>

cd "$REPO"

# Do not silently overwrite locally edited tracked code.
test -z "$(sudo git status --porcelain --untracked-files=no)" || {
  echo "STOP: tracked files are modified; reconcile before release" >&2
  exit 1
}

sudo git fetch --no-tags origin main
sudo git cat-file -e "$SHA^{commit}"

# A vetted commit remains deployable after subsequent main merges,
# provided it is genuinely in main's history. This is not permission
# to skip reviewing newly merged security-critical fixes.
sudo git merge-base --is-ancestor "$SHA" refs/remotes/origin/main || {
  echo "STOP: candidate is not an ancestor of remote main" >&2
  exit 1
}

# First upgrade: explicit clean checkout makes the new SP30 source gate
# available; subsequent deploys recheck SHA, clean tree and ancestry.
sudo git checkout --detach "$SHA"
test "$(sudo git rev-parse HEAD)" = "$SHA"
sudo env SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc \
  SMARTPLOY_RELEASE_APPROVED_SHA="$SHA" \
  bash deploy/personal/scripts/deploy.sh "$SHA"
test "$(sudo git rev-parse HEAD)" = "$SHA"

sudo bash deploy/personal/scripts/assert-healthy-stack.sh
sudo bash deploy/personal/scripts/assert-running-images.sh "$SHA"
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online

sudo docker exec smartploy-api-1 \
  python scripts/check_application_runtime.py --require-local-ai
sudo docker exec smartploy-worker-1 \
  python scripts/check_ats_readiness.py
~~~

The command uses a **reviewed SHA**, not \`main\`; therefore another
developer's merge does not silently change the release contents and does
not invalidate the pin. SP30 itself rejects mutable refs, short hashes, dirty tracked source and
commits outside remote main, but native Woodpecker CI and actual owner
approval remain independent gates, not automatically attested by Git.

The production scripts still own backups, migrations, image checks,
protection checks and evidence. Do not expose the API, PostgreSQL or
Ollama ports to the public internet.

## Post-deploy evidence

Record in tracker #88 and go-live issue #57, **without secrets or CVs**:

- UTC/Finnish timestamp and **running** release SHA (not only checked-out HEAD);
- exact successful push-to-main CI run for that SHA;
- backup metadata and non-sensitive release-evidence pathname/hash;
- all four container health / running image provenance and DNS/TLS/edge
  Access status;
- currently observed Finnish active job count, source count, local Ollama
  readiness, and ObumAI agent-job integration readiness **separately**;
- human browser acceptance (logo, first-use, general/personalized Settings,
  account isolation) or explicit *not yet checked*;
- real browser companion/employer submission evidence or explicit
  *not performed/not independently verified*.

Cloudflare Access is the current authorized private access boundary.
Do not switch to Obum Identity until \`#64\` and its dependent identity
provider gates are verified.

## Progress report cadence

At each user-requested SmartPloy development continuation, report:
- checkboxes actually completed, with PR/SHA/test evidence;
- current in-progress item, owned blockers and exact next action;
- source \`main\` vs actually running production commit;
- note that no background deployment, future work, or employer applications
  are promised without the required separate scheduling/action approval.

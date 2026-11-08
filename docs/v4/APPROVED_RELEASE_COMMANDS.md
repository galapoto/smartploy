# SmartPloy — approved server release commands
**Operator-only. Last reviewed against** `deploy/personal/scripts/deploy.sh`, `check-approved-source.sh` and `release-evidence.sh` on `main=37382b54ac9257298e2d32bcd1a2733b87705f60` (2026-11-08).

**GitHub source commit is NOT a server deployment.** GitHub PRs must undergo required independent review, security/CI approval and approved merge. The server fetches only trusted `origin/main`, and deployment accepts only the exact approved immutable full SHA already contained in main. The existing deploy script backs up PostgreSQL before migration, rebuilds/recreates app containers, checks exact image/web/companion release and OIDC/identity policy, and keeps rollback evidence. **Do not use a PR head, blindly deploy latest main, edit production source, force checkout dirty files, disable checks, or guess approval flags.**

## Read-only diagnosis

From a trusted SSH workstation:

```sh
ssh ubuntu@obum-core-01
# On server:
sudo -i
cd /srv/obum/stacks/smartploy
git status --short
git fetch --no-tags origin main
git rev-parse HEAD
git rev-parse origin/main
cat /srv/obum/data/smartploy/deploy-state/deployed-auth-profile
curl --fail --silent --show-error https://smartploy.komplyint.fi/release.json
curl --fail --silent --show-error https://smartploy.komplyint.fi/healthz
```

If the location, user, SSH identity, auth profile or file permissions differ, stop and use the approved operator configuration; do not guess credentials. The state directory contains private deployment information: inspect only the identity profile, do not print the full env, tokens or backup.

## Authorized exact-SHA release

**Only after** an independent review/merge and explicit human production release GO:

```bash
# Run in the already authenticated privileged server shell, not a local laptop.
set -Eeuo pipefail
cd /srv/obum/stacks/smartploy
APPROVED_SHA='REPLACE_WITH_THE_REVIEWED_MERGED_FULL_40_HEX_COMMIT'
[[ "$APPROVED_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "STOP: exact approved 40-character SHA required"; exit 2;
}
test -z "$(git status --porcelain --untracked-files=no)" || {
  echo "STOP: tracked files are dirty"; exit 2;
}
git fetch --no-tags origin main
git cat-file -e "$APPROVED_SHA^{commit}"
git merge-base --is-ancestor "$APPROVED_SHA" origin/main || {
  echo "STOP: commit not merged to origin/main"; exit 2;
}
# Preserve whichever auth policy is already deployed; no identity-mode switch.
MODE="$(cat /srv/obum/data/smartploy/deploy-state/deployed-auth-profile)"
[[ "$MODE" == "oidc" || "$MODE" == "cloudflare" ]] || {
  echo "STOP: production identity profile unknown"; exit 2;
}
# This environment value is NOT itself release approval. Obtain separate GO.
if [[ "$MODE" == "oidc" ]]; then
  SMARTPLOY_PRODUCTION_IDENTITY_MODE="$MODE" \
  SMARTPLOY_RELEASE_APPROVED_SHA="$APPROVED_SHA" \
    bash deploy/personal/scripts/deploy.sh "$APPROVED_SHA"
else
  SMARTPLOY_PRODUCTION_IDENTITY_MODE="$MODE" \
    bash deploy/personal/scripts/deploy.sh "$APPROVED_SHA"
fi
SMARTPLOY_PRODUCTION_IDENTITY_MODE="$MODE" \
  bash deploy/personal/scripts/release-evidence.sh --online
curl --fail --silent --show-error https://smartploy.komplyint.fi/release.json
curl --fail --silent --show-error https://smartploy.komplyint.fi/healthz
```

**Not finished after shell exit.** Verify actual signed-in Home → CV → mode → exact job → browser/form → save/review on the public hostname and supported device/browser. Compare exact approved SHA fingerprints, collect redacted evidence, review all negative tests, retain rollback SHA and update [the acceptance checklist](LIVE_USER_OUTCOME_CHECKLIST.md). If the release or signed-in acceptance fails, label `BLOCKED`/rollback and do **not** tick any affected target. A production operator must use the repo's approved recovery procedure; never improvise restore or bypass tenant/identity policy.

For CI-QUALIFIED PRs without required review or production access, **do not run the release block**. Request an independent reviewer and the authorized OVH operator. Do not ask candidates to share passwords, SSH keys or any production env content in chat.

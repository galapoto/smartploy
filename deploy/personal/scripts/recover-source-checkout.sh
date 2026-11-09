#!/usr/bin/env bash
# Recover a separate reviewed Git checkout when the live SmartPloy stack is a
# source snapshot without .git. This NEVER stops Docker or deploys anything.
set -Eeuo pipefail

SNAPSHOT=/srv/obum/stacks/smartploy
RECOVERY=/srv/obum/stacks/smartploy-source
REMOTE=https://github.com/galapoto/smartploy.git

fail() { printf 'SmartPloy source recovery: %s\n' "$1" >&2; exit 1; }
if [[ $# -ne 1 || ! "${1:-}" =~ ^[0-9a-f]{40}$ ]]; then
  fail 'provide one approved immutable 40-character Git commit SHA'
fi
SHA="$1"
[[ -d "$SNAPSHOT" && ! -L "$SNAPSHOT" ]] || fail 'existing stack is absent or symlinked'
if git -C "$SNAPSHOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail 'existing stack is already a Git checkout; use its native release process'
fi
ENV="$SNAPSHOT/deploy/personal/env"
[[ -f "$ENV" && ! -L "$ENV" ]] || fail 'original private env absent/symlinked; do not generate new database credentials'
MODE="$(stat -c '%a' "$ENV")"
[[ "$MODE" =~ ^[0-7]{3,4}$ ]] || fail 'unable to verify private env permissions'
(( (8#$MODE & 077) == 0 )) || fail 'original private env is readable by group or other users'

# An existing checkout is never reset, deleted, overwritten, or silently rebased.
if [[ -e "$RECOVERY" || -L "$RECOVERY" ]]; then
  [[ -d "$RECOVERY/.git" || -f "$RECOVERY/.git" ]] || fail 'recovery path exists but is not a Git checkout'
  [[ "$(git -C "$RECOVERY" remote get-url origin)" == "$REMOTE" ]] || fail 'recovery remote is not the expected first-party repository'
  [[ "$(git -C "$RECOVERY" rev-parse HEAD)" == "$SHA" ]] || fail 'existing recovery checkout is a different revision; inspect manually'
  [[ -f "$RECOVERY/deploy/personal/env" && ! -L "$RECOVERY/deploy/personal/env" ]] || fail 'existing checkout has no safe private env'
  cmp -s "$ENV" "$RECOVERY/deploy/personal/env" || fail 'private env differs; reconcile manually'
  printf 'recovery=existing_checkout_verified\nsource_sha=%s\nproduction_unchanged=true\n' "$SHA"
  exit 0
fi

PARENT="$(dirname "$RECOVERY")"
[[ -d "$PARENT" && ! -L "$PARENT" ]] || fail 'recovery parent directory is absent or symlinked'
for cmd in git mktemp install cmp stat; do command -v "$cmd" >/dev/null 2>&1 || fail "missing command: $cmd"; done
umask 077
TEMP="$(mktemp -d "$PARENT/.smartploy-source-recovery.XXXXXXXX")"
trap 'rm -rf -- "$TEMP"' EXIT
GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout --single-branch --branch main "$REMOTE" "$TEMP/source" \
  || fail 'GitHub clone failed; running production is untouched'
git -C "$TEMP/source" cat-file -e "${SHA}^{commit}" 2>/dev/null \
  || fail 'approved SHA absent from first-party main history'
git -C "$TEMP/source" merge-base --is-ancestor "$SHA" refs/remotes/origin/main \
  || fail 'approved SHA is not an ancestor of first-party main'
git -C "$TEMP/source" checkout --quiet --detach "$SHA"
[[ "$(git -C "$TEMP/source" rev-parse HEAD)" == "$SHA" ]] || fail 'source revision mismatch'
[[ -f "$TEMP/source/deploy/personal/scripts/deploy.sh" ]] || fail 'reviewed release script missing'
install -m 600 "$ENV" "$TEMP/source/deploy/personal/env"
cmp -s "$ENV" "$TEMP/source/deploy/personal/env" || fail 'private env copy verification failed'
[[ ! -e "$RECOVERY" && ! -L "$RECOVERY" ]] || fail 'recovery path appeared concurrently; refusing to overwrite'
mv -T -- "$TEMP/source" "$RECOVERY"
[[ "$(git -C "$RECOVERY" rev-parse HEAD)" == "$SHA" ]] || fail 'staged revision mismatch'
printf 'recovery=new_checkout_ready\nsource_sha=%s\nprivate_env=copied_mode_600\nproduction_unchanged=true\n' "$SHA"
printf 'next=run_existing_exact_sha_deploy_after_release_approval\n'
#!/usr/bin/env bash
# FEATURE-FIRST-001: root-executed SmartPloy production promotion *after*
# successful exact-main GitHub CI, independent native Woodpecker proof and
# independently approved low-risk/explicit high-risk release classification.
#
# This script is sent via SSH stdin by the protected GitHub environment job.
# It deliberately cannot create its own native CI/Director approval receipts.
# The existing guarded deploy.sh retains backup, migration, provenance,
# locking and rollback checks. No source/PR branch can deploy itself.
set -Eeuo pipefail
umask 077

SHA="${1:-}"
if [[ "$#" -ne 1 || ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FEATURE_FIRST_DENIED: immutable reviewed 40-hex SHA required" >&2
  exit 41
fi

REPO="/srv/obum/stacks/smartploy"
DEPLOY_SCRIPT="${REPO}/deploy/personal/scripts/deploy.sh"
ENV_FILE="${REPO}/deploy/personal/env"
[[ -f "$ENV_FILE" && -f "$DEPLOY_SCRIPT" ]] || {
  echo "FEATURE_FIRST_DENIED: production host is not commissioned" >&2
  exit 41
}

STATE_DIR="$(sed -n 's/^SMARTPLOY_DEPLOY_STATE_DIR=//p' "$ENV_FILE" | tail -n 1)"
STATE_DIR="${STATE_DIR:-/srv/obum/data/smartploy/deploy-state}"
case "$STATE_DIR" in
  /srv/obum/data/smartploy/deploy-state|/srv/obum/data/smartploy/deploy-state/*) ;;
  *) echo "FEATURE_FIRST_DENIED: untrusted deploy-state directory" >&2; exit 41 ;;
esac
[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || {
  echo "FEATURE_FIRST_DENIED: private deploy-state directory missing" >&2
  exit 41
}

# Files below must be written by the separately commissioned **native CI
# and release risk/approval owners**. This script cannot synthesize them.
# Native CI must attest the immutable SHA and the independent policy gate
# must classify that SHA as auto-eligible low-risk OR explicitly approved.
receipt_matches() {
  local file="${STATE_DIR}/$1"
  [[ -f "$file" && ! -L "$file" ]] || return 1
  [[ "$(stat -c '%U' "$file")" == "root" ]] || return 1
  # root-owned and not writable by group/other
  local mode
  mode="$(stat -c '%a' "$file")"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || return 1
  if (( (8#$mode & 022) != 0 )); then return 1; fi
  local recorded
  recorded="$(tr -d '[:space:]' < "$file")"
  [[ "$recorded" == "$SHA" ]]
}

# Native CI could complete slightly after GitHub; wait a bounded interval
# so each feature can ship on the same merge without manual reruns.
qualified=false
for _ in $(seq 1 60); do
  if receipt_matches "native-ci-qualified-sha"; then
    qualified=true
    break
  fi
  sleep 10
done
[[ "$qualified" == "true" ]] || {
  echo "FEATURE_FIRST_DENIED: exact-SHA native Woodpecker PASS missing" >&2
  exit 41
}
if receipt_matches "feature-first-auto-eligible-sha"; then
  echo "FEATURE_FIRST_APPROVAL=reviewed_low_risk"
elif receipt_matches "feature-first-approved-sha"; then
  echo "FEATURE_FIRST_APPROVAL=explicit_high_risk"
else
  echo "FEATURE_FIRST_DENIED: independent release-approval receipt missing" >&2
  exit 41
fi

cd "$REPO"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
  echo "FEATURE_FIRST_DENIED: tracked production checkout is dirty" >&2
  exit 41
}
git fetch --no-tags origin main
git cat-file -e "$SHA^{commit}"
git merge-base --is-ancestor "$SHA" origin/main || {
  echo "FEATURE_FIRST_DENIED: candidate not contained in reviewed origin/main" >&2
  exit 41
}

if [[ -f "${STATE_DIR}/deployed-sha" ]]; then
  PREVIOUS="$(tr -d '[:space:]' < "${STATE_DIR}/deployed-sha")"
  if [[ "$PREVIOUS" =~ ^[0-9a-f]{40}$ && "$PREVIOUS" != "$SHA" ]]; then
    git merge-base --is-ancestor "$PREVIOUS" "$SHA" || {
      echo "FEATURE_FIRST_DENIED: not an authorized forward-only deployment" >&2
      exit 41
    }
  fi
fi

if [[ "${PREVIOUS:-}" == "$SHA" ]]; then
  echo "FEATURE_FIRST_SAME_SHA: verifying existing immutable release"
else
  # The original host script creates a database backup before migrations,
  # verifies exact checked-out source/images and requires OIDC live parity.
  env SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc \
      SMARTPLOY_RELEASE_APPROVED_SHA="$SHA" \
      bash "$DEPLOY_SCRIPT" "$SHA"
fi

env SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc \
    bash "${REPO}/deploy/personal/scripts/release-evidence.sh" --online
[[ "$(tr -d '[:space:]' < "${STATE_DIR}/deployed-sha")" == "$SHA" ]] || {
  echo "FEATURE_FIRST_DENIED: running release SHA not recorded" >&2
  exit 42
}
echo "FEATURE_FIRST_RELEASED_SHA=$SHA"
echo "FEATURE_FIRST_STATE=RELEASED_PENDING_SIGNED_IN_UX"
echo "FEATURE_FIRST_NOT_SHIPPED_UNTIL_USER_VERIFIED=true"

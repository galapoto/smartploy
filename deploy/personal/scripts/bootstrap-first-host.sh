#!/usr/bin/env bash
# Provision only the private SmartPloy environment for an initial installation.
# No Docker containers, ingress, identity policies, or neighboring products are modified.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SOURCE="${REPO_ROOT}/deploy/personal/env.example"
TARGET="${REPO_ROOT}/deploy/personal/env"
BACKUP_DIR="/srv/obum/backups/smartploy"
STATE_DIR="/srv/obum/data/smartploy/deploy-state"

fail() {
  printf 'SmartPloy bootstrap: %s\n' "$1" >&2
  exit 1
}

[[ -f "$SOURCE" ]] || fail "missing version-controlled env.example"
[[ -f "${REPO_ROOT}/deploy/personal/docker-compose.yml" ]] || fail "missing Compose manifest"
[[ -d "${REPO_ROOT}/.git" || -f "${REPO_ROOT}/.git" ]] || fail "expected a cloned Git repository"

if [[ -L "$TARGET" ]]; then
  fail "production env must never be a symlink"
fi
if [[ -e "$TARGET" ]]; then
  printf 'private_env=already_exists_untouched\n'
  exit 0
fi

command -v docker >/dev/null || fail "Docker is unavailable"
docker info >/dev/null 2>&1 || fail "Docker daemon is not accessible; run with authorized Docker permissions"

# Never mint a fresh database password over an existing persistent volume or recovery point.
if docker volume inspect smartploy-postgres >/dev/null 2>&1; then
  fail "SmartPloy PostgreSQL volume already exists; recover the original private env instead"
fi
if [[ -e "${STATE_DIR}/deployed-sha" ]]; then
  fail "prior deployment marker exists; recover the original private env instead"
fi
if [[ -d "$BACKUP_DIR" ]] && find "$BACKUP_DIR" -maxdepth 1 -type f -name 'smartploy-*.dump' -print -quit | grep -q .; then
  fail "SmartPloy database backups already exist; recover the original private env instead"
fi

umask 077
python3 - "$SOURCE" "$TARGET" <<'PY'
import os
import secrets
import sys
from pathlib import Path

source, target = map(Path, sys.argv[1:])
text = source.read_text(encoding="utf-8")
changes = {
    "POSTGRES_PASSWORD=replace-with-url-safe-random-password":
        "POSTGRES_PASSWORD=" + secrets.token_urlsafe(40),
    # Machine credentials must be approved before requesting any AI work.
    "OBUMAI_BASE_URL=https://app.obumai.com": "OBUMAI_BASE_URL=",
}
for old, new in changes.items():
    if text.count(old) != 1:
        raise SystemExit("SmartPloy bootstrap: unexpected version-controlled env template")
    text = text.replace(old, new)

flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
fd = os.open(target, flags, 0o600)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
except BaseException:
    target.unlink(missing_ok=True)
    raise
PY

printf 'private_env=created_mode_600\n'
printf 'postgres_password=generated_not_displayed\n'
printf 'obumai_agent_integration=disabled_pending_machine_auth\n'
printf 'cloudflare_access_identity=manual_configuration_required\n'
printf 'next=edit_private_env_then_run_preflight\n'

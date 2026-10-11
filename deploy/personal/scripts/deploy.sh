#!/usr/bin/env bash
set -euo pipefail

TARGET_REF="${1:-main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="${COMPOSE_DIR}/runtime.production.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy env.example to env and add production values." >&2
  exit 1
fi

read_env_value() {
  local name="$1"
  sed -n "s/^${name}=//p" "${ENV_FILE}" | tail -n 1
}

STATE_DIR="$(read_env_value SMARTPLOY_DEPLOY_STATE_DIR)"
STATE_DIR="${STATE_DIR:-/srv/obum/data/smartploy/deploy-state}"
WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
WEB_PORT="${WEB_PORT:-8091}"

if [[ ! "${WEB_PORT}" =~ ^[0-9]+$ ]] || (( WEB_PORT < 1024 || WEB_PORT > 65535 )); then
  echo "SMARTPLOY_WEB_HOST_PORT must be an integer between 1024 and 65535." >&2
  exit 1
fi

mkdir -p "${STATE_DIR}"
chmod 700 "${STATE_DIR}"
umask 077
exec 9>"${STATE_DIR}/production-operation.lock"
if ! flock -n 9; then
  echo "Another SmartPloy production operation already owns the deployment lease." >&2
  exit 1
fi

cleanup() {
  rm -f "${HEALTH_FILE:-}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"
git fetch --prune origin
if git show-ref --verify --quiet "refs/remotes/origin/${TARGET_REF}"; then
  RESOLVED_REF="origin/${TARGET_REF}"
else
  RESOLVED_REF="${TARGET_REF}"
fi

git checkout --detach --force "${RESOLVED_REF}"
DEPLOY_SHA="$(git rev-parse HEAD)"
export SMARTPLOY_IMAGE_TAG="${DEPLOY_SHA:0:12}"

bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}"

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  --env-file "${POLICY_FILE}"
  -f "${COMPOSE_DIR}/docker-compose.yml"
)

"${COMPOSE[@]}" config >/dev/null
"${COMPOSE[@]}" build --pull api web
"${COMPOSE[@]}" up -d --wait postgres

# Always create a bounded pre-deploy database recovery point before migrations.
SMARTPLOY_OPERATION_LOCK_HELD=1 bash "${SCRIPT_DIR}/backup.sh"

# Schema mutation is an explicit one-shot step before application/worker startup.
"${COMPOSE[@]}" run --rm --no-deps api python scripts/migrate.py

# This is a versioned release, not a regular "up": old containers must never
# be treated as successful deployment of a newly built Git revision.
# Recreate only application services, never the existing PostgreSQL volume.
"${COMPOSE[@]}" up -d --wait --wait-timeout 120 --no-deps --force-recreate api
"${COMPOSE[@]}" up -d --no-deps --force-recreate worker web

HEALTH_FILE="$(mktemp)"
HEALTH_OK=false
for _ in $(seq 1 45); do
  if curl --fail --silent --show-error     -H 'Host: smartploy.obumai.com'     "http://127.0.0.1:${WEB_PORT}/healthz" > "${HEALTH_FILE}"; then
    if python3 - "${HEALTH_FILE}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    health = json.load(handle)

assert health["ok"] is True
assert health["service"] == "smartploy"
assert health["public_origin"] == "https://smartploy.obumai.com"
assert health["storage"]["ready"] is True
assert health["access"]["enabled"] is True
assert health["access"]["environment"] == "production"
assert health["access"]["owner_restricted"] is True
assert health["external_actions_authorized"] is False
PY
    then
      HEALTH_OK=true
      break
    fi
  fi
  sleep 2
done

if [[ "${HEALTH_OK}" != true ]]; then
  cat "${HEALTH_FILE}" >&2 || true
  "${COMPOSE[@]}" ps >&2
  echo "SmartPloy production health verification failed." >&2
  exit 1
fi

RUNNING="$("${COMPOSE[@]}" ps --status running --services)"
for required in postgres api worker web; do
  if ! grep -qx "${required}" <<<"${RUNNING}"; then
    "${COMPOSE[@]}" ps >&2
    echo "Required SmartPloy service is not running: ${required}" >&2
    exit 1
  fi
done

# A running service is not necessarily healthy. Never record a deployment SHA
# while the worker is failing its own Docker healthcheck.
bash "${SCRIPT_DIR}/assert-healthy-stack.sh"
bash "${SCRIPT_DIR}/assert-running-images.sh" "${DEPLOY_SHA}"

if [[ -f "${STATE_DIR}/deployed-sha" ]]; then
  PREVIOUS="$(tr -d '[:space:]' < "${STATE_DIR}/deployed-sha")"
  if [[ "${PREVIOUS}" =~ ^[0-9a-f]{40}$ && "${PREVIOUS}" != "${DEPLOY_SHA}" ]]; then
    printf '%s
' "${PREVIOUS}" > "${STATE_DIR}/previous-deployed-sha"
  fi
fi

printf '%s
' "${DEPLOY_SHA}" > "${STATE_DIR}/deployed-sha"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "${STATE_DIR}/deployed-at"
"${COMPOSE[@]}" ps
echo "SmartPloy deployed successfully at ${DEPLOY_SHA}."

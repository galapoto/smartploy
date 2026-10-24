#!/usr/bin/env bash
set -euo pipefail

TARGET_REF="${1:-}"
if [[ "$#" -ne 1 || ! "$TARGET_REF" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SmartPloy deploy: an approved immutable 40-character Git SHA is required; main/branch are not release targets" >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
IDENTITY_PROFILE="${SMARTPLOY_PRODUCTION_IDENTITY_MODE:-cloudflare}"

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
# Reuse the dedicated source gate before any checkout or Docker mutation:
# require clean tracked files and the exact reviewed SHA in origin/main.
bash "${SCRIPT_DIR}/check-approved-source.sh" "${TARGET_REF}" >/dev/null
git checkout --detach "${TARGET_REF}"
DEPLOY_SHA="$(git rev-parse HEAD)"
if [[ "${DEPLOY_SHA}" != "${TARGET_REF}" ]]; then
  echo "SmartPloy deploy: checked-out commit differs from approved exact SHA" >&2
  exit 3
fi
export SMARTPLOY_IMAGE_TAG="${DEPLOY_SHA:0:12}"

bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}"
# Reuse the immutable, validated identity policy as the ONLY allowed Host,
# for both legacy rollback and the Komplyint first-party OIDC release.
PRODUCTION_ORIGIN="$(sed -n 's/^SMARTPLOY_PUBLIC_ORIGIN=//p' "${POLICY_FILE}")"
PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"
# Before deploying, verify selected-host DNS/TLS and exact issuer PKCE
# metadata. Do NOT require the new web shell to be served before it exists.
# After deploying, the original live-acceptance.sh rejects Cloudflare
# Access challenges, unsafe login redirects and inaccessible private APIs
# before recording a successful release SHA.
if [[ "${IDENTITY_PROFILE}" == "oidc" ]]; then
  [[ "${SMARTPLOY_RELEASE_APPROVED_SHA:-}" == "${DEPLOY_SHA}" ]] || {
    echo "OIDC rollout requires a separately approved EXACT release commit SHA" >&2
    exit 1
  }
  bash "${SCRIPT_DIR}/preflight.sh" --online >/dev/null
else
  bash "${SCRIPT_DIR}/preflight.sh" >/dev/null
fi

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

# Explicitly opted-in SmartPloy model reads are allowed only on a dedicated
# INTERNAL Docker network shared with ObumAI's Ollama. Never expose 11434,
# join ObumAI's database network or turn on model access in CI by default.
LOCAL_AI_ENABLED="$(read_env_value SMARTPLOY_LOCAL_AI_ENABLED)"
if [[ "$LOCAL_AI_ENABLED" == "true" ]]; then
  LOCAL_AI_URL="$(read_env_value SMARTPLOY_LOCAL_AI_BASE_URL)"
  if [[ "$LOCAL_AI_URL" != "http://ollama:11434" ]]; then
    echo "SmartPloy local AI must use the approved model-only bridge endpoint." >&2
    exit 1
  fi
  export SMARTPLOY_BRIDGE_MODEL="$(read_env_value SMARTPLOY_LOCAL_AI_MODEL)"
  SMARTPLOY_BRIDGE_MODEL="${SMARTPLOY_BRIDGE_MODEL:-qwen3:4b}"
  export SMARTPLOY_BRIDGE_MODEL
  bash "${SCRIPT_DIR}/bridge-local-ollama.sh" --connect
fi

"${COMPOSE[@]}" up -d --no-deps --force-recreate worker web

HEALTH_FILE="$(mktemp)"
HEALTH_OK=false
for _ in $(seq 1 45); do
  if curl --fail --silent --show-error     -H "Host: ${PRODUCTION_HOST}"     "http://127.0.0.1:${WEB_PORT}/healthz" > "${HEALTH_FILE}"; then
    if python3 - "${HEALTH_FILE}" "${IDENTITY_PROFILE}" "${PRODUCTION_ORIGIN}" "${DEPLOY_SHA:0:12}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    health = json.load(handle)

assert health["ok"] is True
assert health["service"] == "smartploy"
assert health["public_origin"] == sys.argv[3]
assert health.get("release_revision") == sys.argv[4], (
    "Deployed API revision differs from the exact approved Git SHA"
)
assert health["storage"]["ready"] is True
assert health["access"]["environment"] == "production"
if sys.argv[2] == "oidc":
    assert health["access"]["enabled"] is False
else:
    assert sys.argv[2] == "cloudflare"
    assert health["access"]["enabled"] is True
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

# OIDC release must prove the ACTUAL public login -> trusted issuer, public
# static shell, and signed-out private API before recording the release SHA.
# The original Cloudflare profile remains subject to its existing probes.
if [[ "${IDENTITY_PROFILE}" == "oidc" ]]; then
  bash "${SCRIPT_DIR}/live-acceptance.sh" >/dev/null
fi

if [[ -f "${STATE_DIR}/deployed-sha" ]]; then
  PREVIOUS="$(tr -d '[:space:]' < "${STATE_DIR}/deployed-sha")"
  if [[ "${PREVIOUS}" =~ ^[0-9a-f]{40}$ && "${PREVIOUS}" != "${DEPLOY_SHA}" ]]; then
    printf '%s
' "${PREVIOUS}" > "${STATE_DIR}/previous-deployed-sha"
  fi
fi

printf '%s
' "${DEPLOY_SHA}" > "${STATE_DIR}/deployed-sha"
printf '%s\n' "${IDENTITY_PROFILE}" > "${STATE_DIR}/deployed-auth-profile"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "${STATE_DIR}/deployed-at"
"${COMPOSE[@]}" ps
echo "SmartPloy deployed successfully at ${DEPLOY_SHA}."

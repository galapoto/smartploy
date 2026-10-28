#!/usr/bin/env bash
set -euo pipefail

ONLINE=false
if [[ "${1:-}" == "--online" ]]; then
  ONLINE=true
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: release-evidence.sh [--online]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
IDENTITY_PROFILE="${SMARTPLOY_PRODUCTION_IDENTITY_MODE:-cloudflare}"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

fail() {
  echo "SmartPloy release evidence: $1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

read_env_value() {
  local name="$1"
  sed -n "s/^${name}=//p" "${ENV_FILE}" | tail -n 1
}

for command_name in awk basename chmod curl date find flock git mktemp mv python3 realpath sed sha256sum sort stat tail tr; do
  require_command "${command_name}"
done

[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] \
  || fail "deploy/personal/env must exist as a regular non-symlink file"
bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null
PRODUCTION_ORIGIN="$(sed -n 's/^SMARTPLOY_PUBLIC_ORIGIN=//p' "${POLICY_FILE}")"
PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"

STATE_DIR="$(read_env_value SMARTPLOY_DEPLOY_STATE_DIR)"
STATE_DIR="${STATE_DIR:-/srv/obum/data/smartploy/deploy-state}"
BACKUP_DIR="$(read_env_value SMARTPLOY_BACKUP_DIR)"
BACKUP_DIR="${BACKUP_DIR:-/srv/obum/backups/smartploy}"
WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
WEB_PORT="${WEB_PORT:-8091}"

if [[ -f "${STATE_DIR}/deployed-auth-profile" ]]; then
  DEPLOYED_IDENTITY_PROFILE="$(tr -d '[:space:]' < "${STATE_DIR}/deployed-auth-profile")"
  if [[ "${DEPLOYED_IDENTITY_PROFILE}" != "${IDENTITY_PROFILE}" ]]; then
    echo "Deployed identity profile differs from selected rollback/release profile" >&2
    exit 1
  fi
fi
[[ "${STATE_DIR}" == /* ]] || fail "SMARTPLOY_DEPLOY_STATE_DIR must be absolute"
[[ "${BACKUP_DIR}" == /* ]] || fail "SMARTPLOY_BACKUP_DIR must be absolute"
[[ "${WEB_PORT}" =~ ^[0-9]+$ ]] || fail "SMARTPLOY_WEB_HOST_PORT must be numeric"

[[ -d "${STATE_DIR}" ]] || fail "deployment state directory does not exist"
STATE_MODE="$(stat -c '%a' "${STATE_DIR}")"
[[ "${STATE_MODE}" =~ ^[0-7]{3,4}$ ]] || fail "unable to determine deployment state permissions"
if (( (8#${STATE_MODE} & 077) != 0 )); then
  fail "deployment state directory must not be group/world accessible"
fi
umask 077

exec 9>"${STATE_DIR}/production-operation.lock"
if ! flock -n 9; then
  fail "another SmartPloy production operation owns the operation lock"
fi

CURRENT_CODE_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
[[ "${CURRENT_CODE_SHA}" =~ ^[0-9a-f]{40}$ ]] \
  || fail "current repository SHA is invalid"

[[ -f "${STATE_DIR}/deployed-sha" && ! -L "${STATE_DIR}/deployed-sha" ]] \
  || fail "deployed-sha state is missing"
DEPLOYED_SHA="$(tr -d '[:space:]' < "${STATE_DIR}/deployed-sha")"
[[ "${DEPLOYED_SHA}" =~ ^[0-9a-f]{40}$ ]] \
  || fail "deployed-sha state is invalid"
[[ "${DEPLOYED_SHA}" == "${CURRENT_CODE_SHA}" ]] \
  || fail "current code SHA does not match deployed-sha"

DEPLOYED_AT="unknown"
if [[ -f "${STATE_DIR}/deployed-at" && ! -L "${STATE_DIR}/deployed-at" ]]; then
  CANDIDATE_DEPLOYED_AT="$(tr -d '\r\n' < "${STATE_DIR}/deployed-at")"
  if [[ "${CANDIDATE_DEPLOYED_AT}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
    DEPLOYED_AT="${CANDIDATE_DEPLOYED_AT}"
  fi
fi

# Run existing read-only production gates without echoing their output into the evidence command.
if ! bash "${SCRIPT_DIR}/preflight.sh" >/dev/null; then
  fail "production preflight failed"
fi
if ! bash "${SCRIPT_DIR}/smoke-env-boundaries.sh" >/dev/null; then
  fail "runtime environment-boundary smoke failed"
fi
if ! bash "${SCRIPT_DIR}/assert-healthy-stack.sh" >/dev/null; then
  fail "one or more SmartPloy services are not healthy"
fi
# Release evidence must certify running image identity, not merely healthy older images.
if ! bash "${SCRIPT_DIR}/assert-running-images.sh" "${DEPLOYED_SHA}" >/dev/null; then
  fail "running container image IDs do not match deployed Git revision"
fi
# SP45: independently check the exact public ZIP against current source.
# This is an anonymous local Caddy read, not a browser or employer action.
if ! COMPANION_FIELDS="$(bash "${SCRIPT_DIR}/assert-companion-release.sh" "${PRODUCTION_HOST}" "${WEB_PORT}")"; then
  fail "running companion download/sha differs from approved source"
fi
[[ "${COMPANION_FIELDS}" == *"companion_release_verified=true"* ]] \
  || fail "companion release proof is incomplete"
# A generic healthy worker/database is NOT proof that Agent Zero was
# registered or actually ran. Require an independent task-level receipt.
# Values are fixed booleans/status labels only: no applicant/job/secret data.
if ! AGENT_ZERO_REPORT="$(bash "${SCRIPT_DIR}/assert-agent-zero-worker.sh")"; then
  fail "Agent Zero worker runtime gate failed"
fi
AGENT_ZERO_FIELDS="$(printf '%s\n' "${AGENT_ZERO_REPORT}" | sed -n '/^agent_zero_/p')"
[[ "$(printf '%s\n' "${AGENT_ZERO_FIELDS}" | grep -c '^agent_zero_mode=')" -eq 1 ]] \
  || fail "Agent Zero task status missing from release proof"

TMP_DIR="$(mktemp -d)"
EVIDENCE_TMP=""
cleanup() {
  rm -rf "${TMP_DIR}"
  if [[ -n "${EVIDENCE_TMP}" ]]; then
    rm -f "${EVIDENCE_TMP}"
  fi
}
trap cleanup EXIT
chmod 700 "${TMP_DIR}"

HEALTH_FILE="${TMP_DIR}/health.json"
if ! curl --fail --silent --show-error --max-time 10 \
  -H "Host: ${PRODUCTION_HOST}" \
  "http://127.0.0.1:${WEB_PORT}/healthz" > "${HEALTH_FILE}"; then
  fail "local SmartPloy health request failed"
fi

if ! PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
  origin-health "${HEALTH_FILE}" "${IDENTITY_PROFILE}" >/dev/null; then
  fail "local SmartPloy health contract failed"
fi

HEALTH_FIELDS="$(python3 - "${HEALTH_FILE}" "${DEPLOYED_SHA:0:12}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    health = json.load(handle)

# Public health alone is not a signed release receipt, but it must agree
# with the already-checked Git checkout and Docker image identity.
assert health.get("release_revision") == sys.argv[2], (
    "Public health revision differs from the deployed source"
)
print("release_revision=" + health["release_revision"])
worker = health.get("worker") or {}
access = health.get("access") or {}

def boolean(value):
    return "true" if value is True else "false"

print("storage_ready=" + boolean((health.get("storage") or {}).get("ready")))
print("worker_ready=" + boolean(worker.get("ready")))
print("worker_task_count=" + str(int(worker.get("count") or 0)))
print("access_enabled=" + boolean(access.get("enabled")))
print("access_environment=" + str(access.get("environment") or "unknown"))
print("access_owner_restricted=" + boolean(access.get("owner_restricted")))
print("external_actions_authorized=" + boolean(health.get("external_actions_authorized")))
PY
)"

POLICY_SHA256="$(sha256sum "${POLICY_FILE}" | awk '{print $1}')"
COMPOSE_SHA256="$(sha256sum "${COMPOSE_FILE}" | awk '{print $1}')"

LATEST_BACKUP_FILE="none"
LATEST_BACKUP_SHA256="none"
LATEST_BACKUP_METADATA_VALID="false"

if [[ -d "${BACKUP_DIR}" ]]; then
  LATEST_BACKUP="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'smartploy-*.dump' -printf '%T@ %p\n' \
    | sort -nr | awk 'NR == 1 {print $2}')"
  if [[ -n "${LATEST_BACKUP}" ]]; then
    BACKUP_ROOT="$(realpath "${BACKUP_DIR}")"
    BACKUP_FILE="$(realpath "${LATEST_BACKUP}")"
    case "${BACKUP_FILE}" in
      "${BACKUP_ROOT}"/smartploy-*.dump) ;;
      *) fail "latest backup is outside configured backup directory" ;;
    esac

    [[ ! -L "${LATEST_BACKUP}" ]] || fail "latest backup must not be a symlink"
    CHECKSUM_FILE="${BACKUP_FILE}.sha256"
    META_FILE="${BACKUP_FILE}.meta"
    [[ -f "${CHECKSUM_FILE}" && ! -L "${CHECKSUM_FILE}" ]] \
      || fail "latest backup checksum sidecar is missing"
    [[ -f "${META_FILE}" && ! -L "${META_FILE}" ]] \
      || fail "latest backup metadata sidecar is missing"

    (
      cd "${BACKUP_ROOT}"
      sha256sum -c "$(basename "${CHECKSUM_FILE}")" >/dev/null
    ) || fail "latest backup checksum validation failed"

    BACKUP_SHA="$(awk 'NR == 1 {print $1}' "${CHECKSUM_FILE}")"
    [[ "${BACKUP_SHA}" =~ ^[0-9a-f]{64}$ ]] || fail "latest backup checksum is invalid"

    META_FORMAT="$(sed -n 's/^format=//p' "${META_FILE}" | tail -n 1)"
    META_DUMP="$(sed -n 's/^dump_file=//p' "${META_FILE}" | tail -n 1)"
    META_SHA="$(sed -n 's/^dump_sha256=//p' "${META_FILE}" | tail -n 1)"
    META_SOURCE="$(sed -n 's/^source_deployed_sha=//p' "${META_FILE}" | tail -n 1)"

    [[ "${META_FORMAT}" == "smartploy-db-backup-v1" ]] \
      || fail "latest backup metadata format is invalid"
    [[ "${META_DUMP}" == "$(basename "${BACKUP_FILE}")" ]] \
      || fail "latest backup metadata filename does not match"
    [[ "${META_SHA}" == "${BACKUP_SHA}" ]] \
      || fail "latest backup metadata checksum does not match"
    if [[ "${META_SOURCE}" != "unknown" && ! "${META_SOURCE}" =~ ^[0-9a-f]{40}$ ]]; then
      fail "latest backup source SHA is invalid"
    fi

    LATEST_BACKUP_FILE="$(basename "${BACKUP_FILE}")"
    LATEST_BACKUP_SHA256="${BACKUP_SHA}"
    LATEST_BACKUP_METADATA_VALID="true"
  fi
fi

LIVE_ACCEPTANCE="skipped"
LIVE_ORIGIN_HEALTH="skipped"
LIVE_DNS="skipped"
LIVE_TLS="skipped"
LIVE_CLOUDFLARE_EDGE="skipped"
LIVE_ACCESS_ROOT="skipped"
LIVE_ACCESS_API="skipped"
LIVE_OIDC_LOGIN="skipped"
LIVE_PUBLIC_REVISION_MATCH="skipped"
LIVE_PUBLIC_RELEASE_REVISION="skipped"

if "${ONLINE}"; then
  LIVE_FILE="${TMP_DIR}/live.txt"
  if ! bash "${SCRIPT_DIR}/live-acceptance.sh" > "${LIVE_FILE}"; then
    fail "live production acceptance failed"
  fi

  live_value() {
    local name="$1"
    sed -n "s/^${name}=//p" "${LIVE_FILE}" | tail -n 1
  }

  [[ "$(live_value live_acceptance)" == "pass" ]] || fail "live acceptance result is incomplete"
  LIVE_ACCEPTANCE="passed"
  LIVE_ORIGIN_HEALTH="$(live_value origin_health)"
  LIVE_DNS="$(live_value dns)"
  LIVE_TLS="$(live_value tls)"
  LIVE_CLOUDFLARE_EDGE="$(live_value cloudflare_edge)"
  LIVE_ACCESS_ROOT="$(live_value access_root)"
  LIVE_ACCESS_API="$(live_value access_api)"
  LIVE_OIDC_LOGIN="$(live_value oidc_login)"
  LIVE_PUBLIC_REVISION_MATCH="$(live_value public_revision_matches_origin)"
  LIVE_PUBLIC_RELEASE_REVISION="$(live_value public_release_revision)"
  if [[ "${IDENTITY_PROFILE}" == "oidc" ]]; then
    [[ "${LIVE_OIDC_LOGIN}" == "redirect_to_trusted_oidc" ]] \
      || fail "Live ZITADEL login redirect proof is missing"
    [[ "${LIVE_PUBLIC_REVISION_MATCH}" == "true" ]] \
      || fail "public HTTPS release parity is not verified"
    [[ "${LIVE_PUBLIC_RELEASE_REVISION}" == "${DEPLOYED_SHA:0:12}" ]] \
      || fail "public HTTPS revision differs from approved deployed SHA"
  else
    [[ "${LIVE_PUBLIC_REVISION_MATCH}" == "skipped_legacy_access" ]] \
      || fail "legacy Access release parity classification is invalid"
    [[ "${LIVE_PUBLIC_RELEASE_REVISION}" == "skipped" ]] \
      || fail "legacy Access must not assert an unauthenticated release revision"
  fi
fi

GENERATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
STAMP="$(date -u +'%Y%m%dT%H%M%SZ')-$$"
FINAL="${STATE_DIR}/release-evidence-${STAMP}.txt"
EVIDENCE_TMP="$(mktemp "${STATE_DIR}/.release-evidence-${STAMP}.XXXXXX")"

cat > "${EVIDENCE_TMP}" <<EOF
format=smartploy-release-evidence-v1
generated_at=${GENERATED_AT}
current_code_sha=${CURRENT_CODE_SHA}
deployed_sha=${DEPLOYED_SHA}
deployed_sha_matches_code=true
deployed_at=${DEPLOYED_AT}
runtime_policy_sha256=${POLICY_SHA256}
compose_file_sha256=${COMPOSE_SHA256}
${HEALTH_FIELDS}
${AGENT_ZERO_FIELDS}
${COMPANION_FIELDS}
latest_backup_file=${LATEST_BACKUP_FILE}
latest_backup_sha256=${LATEST_BACKUP_SHA256}
latest_backup_metadata_valid=${LATEST_BACKUP_METADATA_VALID}
preflight_passed=true
env_boundary_smoke_passed=true
stack_healthy=true
running_release_images_verified=true
live_acceptance=${LIVE_ACCEPTANCE}
live_origin_health=${LIVE_ORIGIN_HEALTH}
live_dns=${LIVE_DNS}
live_tls=${LIVE_TLS}
live_cloudflare_edge=${LIVE_CLOUDFLARE_EDGE}
live_access_root=${LIVE_ACCESS_ROOT}
live_access_api=${LIVE_ACCESS_API}
live_oidc_login=${LIVE_OIDC_LOGIN}
live_public_revision_matches_origin=${LIVE_PUBLIC_REVISION_MATCH}
live_public_release_revision=${LIVE_PUBLIC_RELEASE_REVISION}
identity_profile=${IDENTITY_PROFILE}
EOF

chmod 600 "${EVIDENCE_TMP}"
mv "${EVIDENCE_TMP}" "${FINAL}"
EVIDENCE_TMP=""

(
  cd "${STATE_DIR}"
  sha256sum "$(basename "${FINAL}")" > "$(basename "${FINAL}").sha256"
)
chmod 600 "${FINAL}.sha256"

echo "SmartPloy release evidence: PASS"
echo "Evidence artifact: ${FINAL}"

#!/usr/bin/env bash
set -euo pipefail

REQUESTED_BACKUP="${1:-}"
if [[ -z "${REQUESTED_BACKUP}" ]]; then
  echo "Usage: restore.sh /absolute/path/to/smartploy-*.dump" >&2
  exit 1
fi

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

BACKUP_DIR="$(read_env_value SMARTPLOY_BACKUP_DIR)"
BACKUP_DIR="${BACKUP_DIR:-/srv/obum/backups/smartploy}"
STATE_DIR="$(read_env_value SMARTPLOY_DEPLOY_STATE_DIR)"
STATE_DIR="${STATE_DIR:-/srv/obum/data/smartploy/deploy-state}"
WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
WEB_PORT="${WEB_PORT:-8091}"

if [[ ! "${WEB_PORT}" =~ ^[0-9]+$ ]] || (( WEB_PORT < 1024 || WEB_PORT > 65535 )); then
  echo "SMARTPLOY_WEB_HOST_PORT must be an integer between 1024 and 65535." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}" "${STATE_DIR}"
chmod 700 "${BACKUP_DIR}" "${STATE_DIR}"
umask 077

exec 9>"${STATE_DIR}/production-operation.lock"
if ! flock -n 9; then
  echo "Another SmartPloy production operation owns the operation lock." >&2
  exit 1
fi

BACKUP_ROOT="$(realpath "${BACKUP_DIR}")"
if [[ -L "${REQUESTED_BACKUP}" || ! -f "${REQUESTED_BACKUP}" ]]; then
  echo "Restore target must be a regular SmartPloy backup file." >&2
  exit 1
fi
BACKUP_FILE="$(realpath "${REQUESTED_BACKUP}")"
case "${BACKUP_FILE}" in
  "${BACKUP_ROOT}"/smartploy-*.dump) ;;
  *)
    echo "Restore target must be inside the configured SmartPloy backup directory." >&2
    exit 1
    ;;
esac

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ ! -f "${CHECKSUM_FILE}" || -L "${CHECKSUM_FILE}" ]]; then
  echo "Restore target is missing its trusted SHA256 sidecar." >&2
  exit 1
fi
(
  cd "${BACKUP_ROOT}"
  sha256sum -c "$(basename "${CHECKSUM_FILE}")"
)
BACKUP_SHA256="$(awk 'NR == 1 {print $1}' "${CHECKSUM_FILE}")"
if [[ ! "${BACKUP_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Restore checksum is invalid." >&2
  exit 1
fi

SOURCE_DEPLOYED_SHA="unknown"
META_FILE="${BACKUP_FILE}.meta"
if [[ -f "${META_FILE}" && ! -L "${META_FILE}" ]]; then
  META_FORMAT="$(sed -n 's/^format=//p' "${META_FILE}" | tail -n 1)"
  META_DUMP="$(sed -n 's/^dump_file=//p' "${META_FILE}" | tail -n 1)"
  META_SHA="$(sed -n 's/^dump_sha256=//p' "${META_FILE}" | tail -n 1)"
  META_SOURCE="$(sed -n 's/^source_deployed_sha=//p' "${META_FILE}" | tail -n 1)"
  if [[ "${META_FORMAT}" != "smartploy-db-backup-v1"     || "${META_DUMP}" != "$(basename "${BACKUP_FILE}")"     || "${META_SHA}" != "${BACKUP_SHA256}" ]]; then
    echo "Backup metadata does not match the restore artifact." >&2
    exit 1
  fi
  if [[ "${META_SOURCE}" == "unknown" || "${META_SOURCE}" =~ ^[0-9a-f]{40}$ ]]; then
    SOURCE_DEPLOYED_SHA="${META_SOURCE}"
  else
    echo "Backup metadata contains an invalid source deployed SHA." >&2
    exit 1
  fi
fi

bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}"

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  --env-file "${POLICY_FILE}"
  -f "${COMPOSE_DIR}/docker-compose.yml"
)
"${COMPOSE[@]}" config >/dev/null
"${COMPOSE[@]}" up -d --wait postgres

SAFETY_OUTPUT="$(SMARTPLOY_OPERATION_LOCK_HELD=1 SMARTPLOY_BACKUP_SKIP_RETENTION=1 bash "${SCRIPT_DIR}/backup.sh")"
SAFETY_BACKUP="${SAFETY_OUTPUT#Backup created: }"
if [[ "${SAFETY_BACKUP}" == "${SAFETY_OUTPUT}" || ! -s "${SAFETY_BACKUP}" ]]; then
  echo "Current-state safety backup was not created; restore is forbidden." >&2
  exit 1
fi

# Re-verify the requested artifact after the safety backup and before mutation.
(
  cd "${BACKUP_ROOT}"
  sha256sum -c "$(basename "${CHECKSUM_FILE}")"
)

"${COMPOSE[@]}" stop api worker web >/dev/null

"${COMPOSE[@]}" exec -T postgres sh -c   'exec pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"'   < "${BACKUP_FILE}"

cd "${REPO_ROOT}"
"${COMPOSE[@]}" run --rm --no-deps api python scripts/migrate.py
"${COMPOSE[@]}" up -d api worker web

HEALTH_FILE="$(mktemp)"
cleanup() {
  rm -f "${HEALTH_FILE}"
}
trap cleanup EXIT

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
  echo "SmartPloy restore health verification failed. Safety backup: ${SAFETY_BACKUP}" >&2
  exit 1
fi

RUNNING="$("${COMPOSE[@]}" ps --status running --services)"
for required in postgres api worker web; do
  if ! grep -qx "${required}" <<<"${RUNNING}"; then
    "${COMPOSE[@]}" ps >&2
    echo "Required service is not running after restore: ${required}" >&2
    exit 1
  fi
done

bash "${SCRIPT_DIR}/assert-healthy-stack.sh"

RESTORED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
EVIDENCE="${STATE_DIR}/restore-$(date -u +'%Y%m%dT%H%M%SZ')-$$.txt"
CURRENT_CODE_SHA="unknown"
if git -C "${REPO_ROOT}" rev-parse HEAD >/dev/null 2>&1; then
  CANDIDATE_CODE_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  if [[ "${CANDIDATE_CODE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
    CURRENT_CODE_SHA="${CANDIDATE_CODE_SHA}"
  fi
fi

cat > "${EVIDENCE}" <<EOF
format=smartploy-db-restore-v1
restored_at=${RESTORED_AT}
backup_file=$(basename "${BACKUP_FILE}")
backup_sha256=${BACKUP_SHA256}
backup_source_deployed_sha=${SOURCE_DEPLOYED_SHA}
safety_backup_file=$(basename "${SAFETY_BACKUP}")
current_code_sha=${CURRENT_CODE_SHA}
health_verified=true
EOF
chmod 600 "${EVIDENCE}"

echo "SmartPloy restore completed from ${BACKUP_FILE}."
echo "Safety backup: ${SAFETY_BACKUP}"
echo "Restore evidence: ${EVIDENCE}"

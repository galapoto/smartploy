#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
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
KEEP="$(read_env_value SMARTPLOY_BACKUP_KEEP)"
KEEP="${KEEP:-7}"

if [[ ! "${KEEP}" =~ ^[0-9]+$ ]] || (( KEEP < 1 || KEEP > 100 )); then
  echo "SMARTPLOY_BACKUP_KEEP must be an integer between 1 and 100." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
umask 077

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  --env-file "${POLICY_FILE}"
  -f "${COMPOSE_DIR}/docker-compose.yml"
)

"${COMPOSE[@]}" up -d postgres >/dev/null

STAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
FINAL="${BACKUP_DIR}/smartploy-${STAMP}.dump"
TMP="$(mktemp "${BACKUP_DIR}/.smartploy-${STAMP}.XXXXXX")"
cleanup() {
  rm -f "${TMP}"
}
trap cleanup EXIT

"${COMPOSE[@]}" exec -T postgres   sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${TMP}"

if [[ ! -s "${TMP}" ]]; then
  echo "SmartPloy database backup is empty; refusing to publish it." >&2
  exit 1
fi

mv "${TMP}" "${FINAL}"
chmod 600 "${FINAL}"
(
  cd "${BACKUP_DIR}"
  sha256sum "$(basename "${FINAL}")" > "$(basename "${FINAL}").sha256"
)
chmod 600 "${FINAL}.sha256"

mapfile -t BACKUPS < <(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'smartploy-*.dump' -printf '%T@ %p
' | sort -nr | awk '{print $2}')
if (( ${#BACKUPS[@]} > KEEP )); then
  for old in "${BACKUPS[@]:KEEP}"; do
    rm -f -- "${old}" "${old}.sha256"
  done
fi

echo "Backup created: ${FINAL}"

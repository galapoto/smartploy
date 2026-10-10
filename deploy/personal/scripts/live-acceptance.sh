#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"

PRODUCTION_HOST="smartploy.obumai.com"
PRODUCTION_ORIGIN="https://smartploy.obumai.com"

fail() {
  echo "SmartPloy live acceptance: $1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

read_env_value() {
  local name="$1"
  sed -n "s/^${name}=//p" "${ENV_FILE}" | tail -n 1
}

for command_name in curl getent python mktemp sed tail; do
  require_command "${command_name}"
done

[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] \
  || fail "deploy/personal/env must exist as a regular file"

WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
WEB_PORT="${WEB_PORT:-8091}"
[[ "${WEB_PORT}" =~ ^[0-9]+$ ]] \
  || fail "SMARTPLOY_WEB_HOST_PORT must be numeric"
if (( WEB_PORT < 1024 || WEB_PORT > 65535 )); then
  fail "SMARTPLOY_WEB_HOST_PORT must be between 1024 and 65535"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT
chmod 700 "${TMP_DIR}"
umask 077

HEALTH_FILE="${TMP_DIR}/origin-health.json"
if ! curl --fail --silent --show-error --max-time 10 \
  -H "Host: ${PRODUCTION_HOST}" \
  "http://127.0.0.1:${WEB_PORT}/healthz" \
  > "${HEALTH_FILE}"; then
  fail "local production gateway health check failed"
fi

if ! PYTHONPATH="${REPO_ROOT}" python -m smartploy.live_acceptance \
  origin-health "${HEALTH_FILE}" >/dev/null; then
  fail "local production origin health contract failed"
fi
echo "origin_health=pass"

if ! getent ahosts "${PRODUCTION_HOST}" >/dev/null 2>&1; then
  fail "production DNS does not resolve"
fi
echo "dns=pass"

probe_public() {
  local url="$1"
  local output="$2"

  # Do not follow redirects. Write only the selected non-credential response fields.
  curl --silent --show-error --max-time 15 --output /dev/null \
    --write-out '%{http_code}\n%header{cf-ray}\n%header{server}\n%header{location}\n' \
    "${url}" > "${output}"
}

ROOT_PROBE="${TMP_DIR}/root.probe"
if ! probe_public "${PRODUCTION_ORIGIN}/" "${ROOT_PROBE}"; then
  fail "public HTTPS/TLS probe failed"
fi
ROOT_CLASS="$(PYTHONPATH="${REPO_ROOT}" python -m smartploy.live_acceptance \
  public-probe "${ROOT_PROBE}")" \
  || fail "public root protection validation failed"

echo "tls=pass"
echo "cloudflare_edge=pass"
echo "access_root=${ROOT_CLASS}"

API_PROBE="${TMP_DIR}/api.probe"
if ! probe_public "${PRODUCTION_ORIGIN}/api/v1/dashboard" "${API_PROBE}"; then
  fail "public protected API probe failed"
fi
API_CLASS="$(PYTHONPATH="${REPO_ROOT}" python -m smartploy.live_acceptance \
  public-probe "${API_PROBE}")" \
  || fail "public API protection validation failed"

echo "access_api=${API_CLASS}"
echo "live_acceptance=pass"

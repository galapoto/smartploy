#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
PROFILE="${SMARTPLOY_PRODUCTION_IDENTITY_MODE:-cloudflare}"

# Origin and host come ONLY from the immutable, exact allowlisted policy
# after validate-runtime-policy.sh succeeds. Never trust external redirect
# headers or a caller-provided host for post-deploy acceptance.

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

for command_name in curl getent python3 mktemp sed tail; do
  require_command "${command_name}"
done

[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] \
  || fail "deploy/personal/env must exist as a regular file"

WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
WEB_PORT="${WEB_PORT:-8091}"
OIDC_ISSUER="$(read_env_value SMARTPLOY_OIDC_ISSUER)"
bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null
PRODUCTION_ORIGIN="$(sed -n 's/^SMARTPLOY_PUBLIC_ORIGIN=//p' "${POLICY_FILE}")"
PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"
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

if ! PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
  origin-health "${HEALTH_FILE}" "${PROFILE}" >/dev/null; then
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
# The public response classification must not require Cloudflare headers in
# OIDC mode: Komplyint can route by direct trusted TLS to its OVH Caddy host.
# Show numeric status only; never print redirect URLs, cookies or OAuth state.
echo "public_root_http=$(sed -n '1p' "${ROOT_PROBE}")"
if [[ "${PROFILE}" == "oidc" ]]; then
  ROOT_CLASS="$(PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
    oidc-root "${ROOT_PROBE}" "${OIDC_ISSUER}")" \
    || fail "first-party OIDC public root validation failed"
else
  ROOT_CLASS="$(PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
    public-probe "${ROOT_PROBE}")" \
    || fail "legacy Access public root validation failed"
fi

echo "tls=pass"
if [[ "${PROFILE}" == "oidc" ]]; then
  # Ingress topology is informative, not an authentication decision. Curl
  # already verified the exact public HTTPS hostname and server certificate.
  ROOT_CF_RAY="$(sed -n '2p' "${ROOT_PROBE}")"
  ROOT_SERVER="$(sed -n '3p' "${ROOT_PROBE}")"
  if [[ -n "${ROOT_CF_RAY}" || "${ROOT_SERVER,,}" == "cloudflare" ]]; then
    echo "public_ingress=cloudflare_edge"
  else
    echo "public_ingress=direct_https_or_other_proxy"
  fi
else
  echo "cloudflare_edge=pass"
fi
echo "access_root=${ROOT_CLASS}"

API_PROBE="${TMP_DIR}/api.probe"
if ! probe_public "${PRODUCTION_ORIGIN}/api/v1/dashboard" "${API_PROBE}"; then
  fail "public protected API probe failed"
fi
echo "public_api_http=$(sed -n '1p' "${API_PROBE}")"
if [[ "${PROFILE}" == "oidc" ]]; then
  API_CLASS="$(PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
    oidc-api "${API_PROBE}" "${OIDC_ISSUER}")" \
    || fail "first-party OIDC API protection validation failed"
  LOGIN_PROBE="${TMP_DIR}/login.probe"
  if ! probe_public "${PRODUCTION_ORIGIN}/auth/login" "${LOGIN_PROBE}"; then
    fail "OIDC login initiation probe failed"
  fi
  echo "public_login_http=$(sed -n '1p' "${LOGIN_PROBE}")"
  LOGIN_CLASS="$(PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
    oidc-login "${LOGIN_PROBE}" "${OIDC_ISSUER}")" \
    || fail "OIDC issuer redirect verification failed"
  echo "oidc_login=${LOGIN_CLASS}"
else
  API_CLASS="$(PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
    public-probe "${API_PROBE}")" \
    || fail "legacy Access public API protection validation failed"
fi

echo "access_api=${API_CLASS}"
echo "identity_profile=${PROFILE}"
echo "live_acceptance=pass"

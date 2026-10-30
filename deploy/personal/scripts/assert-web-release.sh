#!/usr/bin/env bash
# SP74: read-only proof that the checked-out API and served Caddy static web
# carry the same exact release SHA. A passing result is NOT permission to deploy.
set -Eeuo pipefail
umask 077

EXPECTED_SHA="${1:-}"
PUBLIC_MODE="${2:-}"
if [[ "$#" -lt 1 || "$#" -gt 2 || ! "${EXPECTED_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SmartPloy web parity: provide the reviewed full 40-character Git SHA" >&2
  exit 2
fi
if [[ -n "${PUBLIC_MODE}" && "${PUBLIC_MODE}" != "--public" ]]; then
  echo "SmartPloy web parity: unsupported option" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${COMPOSE_DIR}/../.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
IDENTITY_PROFILE="${SMARTPLOY_PRODUCTION_IDENTITY_MODE:-cloudflare}"
EXPECTED_REVISION="${EXPECTED_SHA:0:12}"

fail() {
  echo "SmartPloy web parity: $1" >&2
  exit 1
}
for command_name in curl mktemp python3 sed tail; do
  command -v "${command_name}" >/dev/null 2>&1 \
    || fail "required command unavailable: ${command_name}"
done
[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] \
  || fail "private production env must be a regular file"
bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null
PRODUCTION_ORIGIN="$(sed -n 's/^SMARTPLOY_PUBLIC_ORIGIN=//p' "${POLICY_FILE}")"
PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"
WEB_PORT="$(sed -n 's/^SMARTPLOY_WEB_HOST_PORT=//p' "${ENV_FILE}" | tail -n 1)"
WEB_PORT="${WEB_PORT:-8091}"
[[ "${WEB_PORT}" =~ ^[0-9]+$ ]] \
  || fail "web port must be numeric"
if (( WEB_PORT < 1024 || WEB_PORT > 65535 )); then
  fail "web port outside accepted range"
fi
if [[ "${PUBLIC_MODE}" == "--public" && "${IDENTITY_PROFILE}" != "oidc" ]]; then
  fail "public manifest parity is only available on the first-party OIDC origin"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "${TMP_DIR}"' EXIT
chmod 700 "${TMP_DIR}"

curl --fail --silent --show-error --max-time 12 --max-filesize 4096 \
  -H "Host: ${PRODUCTION_HOST}" \
  "http://127.0.0.1:${WEB_PORT}/healthz" > "${TMP_DIR}/origin-health.json" \
  || fail "local API health unavailable"
curl --fail --silent --show-error --max-time 12 --max-filesize 4096 \
  -D "${TMP_DIR}/origin-web.headers" \
  -H "Host: ${PRODUCTION_HOST}" \
  "http://127.0.0.1:${WEB_PORT}/release.json" > "${TMP_DIR}/origin-web.json" \
  || fail "local web release manifest unavailable"

MANIFEST_ARGS=( "${TMP_DIR}/origin-health.json" "${TMP_DIR}/origin-web.json"
  "${EXPECTED_REVISION}" "${IDENTITY_PROFILE}" )
if [[ "${PUBLIC_MODE}" == "--public" ]]; then
  # Only the exact validated immutable production origin may be requested.
  # No redirects, credentials, request body, applicant material or cookies.
  curl --fail --silent --show-error --max-time 15 --max-filesize 4096 \
    -D "${TMP_DIR}/public-web.headers" \
    "${PRODUCTION_ORIGIN}/release.json" > "${TMP_DIR}/public-web.json" \
    || fail "public HTTPS web manifest unavailable"
  MANIFEST_ARGS+=( "${TMP_DIR}/public-web.json" )
fi

# Unlike an arbitrary index.html, this manifest must not be cached at origin
# or at the public edge. Verify only the response header *names and policies*.
python3 - "${TMP_DIR}/origin-web.headers" \
  "${TMP_DIR}/public-web.headers" "${PUBLIC_MODE}" <<'PY'
from pathlib import Path
import sys

def verify_no_store(path: Path):
    raw = path.read_bytes()
    if len(raw) > 8192:
        raise SystemExit("web release manifest header limit exceeded")
    values = []
    for line in raw.decode("latin1").splitlines():
        if line.casefold().startswith("cache-control:"):
            values.extend(token.strip().casefold() for token in line.split(":", 1)[1].split(","))
    if "no-store" not in values:
        raise SystemExit("web release manifest is missing a no-store cache directive")

verify_no_store(Path(sys.argv[1]))
if sys.argv[3] == "--public":
    verify_no_store(Path(sys.argv[2]))
PY

if ! REVISION="$(PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance \
    web-release-parity "${MANIFEST_ARGS[@]}")"; then
  fail "API/frontend exact release revision does not match"
fi
[[ "${REVISION}" == "${EXPECTED_REVISION}" ]] \
  || fail "validated web revision is not the approved release"
printf 'web_release_revision=%s\n' "${REVISION}"
printf 'web_release_origin_parity=true\n'
if [[ "${PUBLIC_MODE}" == "--public" ]]; then
  printf 'web_release_public_parity=true\n'
else
  printf 'web_release_public_parity=not_checked\n'
fi

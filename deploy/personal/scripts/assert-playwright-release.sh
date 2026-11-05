#!/usr/bin/env bash
# SP110: fail-closed, read-only proof that Caddy is serving EXACT reviewed
# local assistant bytes from this approved source checkout, not stale/missing SPA HTML.
# This script does not access applicants, DB, sessions, or employer websites.
set -Eeuo pipefail
umask 077

if [[ "$#" -ne 2 || ! "${1:-}" =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ ||
      ! "${2:-}" =~ ^[0-9]{4,5}$ ]] ; then
  echo "Usage: assert-playwright-release.sh <validated-public-host> <local-web-port>" >&2
  exit 2
fi

PUBLIC_HOST="$1"
WEB_PORT="$2"
if (( 10#${WEB_PORT} < 1024 || 10#${WEB_PORT} > 65535 )); then
  echo "Invalid SmartPloy local web port." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "${TMP_DIR}"' EXIT

require() { command -v "$1" >/dev/null 2>&1 || {
  echo "Missing release verification command: $1" >&2
  exit 1
}; }
for command_name in curl python3 cmp sha256sum grep wc; do require "$command_name"; done

SOURCE_BUILT="${TMP_DIR}/source-playwright-reviewed.zip"
DOWNLOADED="${TMP_DIR}/smartploy-playwright-assistant.zip"
SIDE_CAR="${DOWNLOADED}.sha256"
HEADER_FILE="${TMP_DIR}/playwright-headers"

# Deterministic stdlib packager already validates imported modules, manifest
# permissions and the source allowlist. Build into a *temporary* directory;
# never contaminate a production source tree/public asset.
python3 -B "${REPO_ROOT}/web/scripts/package_playwright_assistant.py" \
  --output "${SOURCE_BUILT}" >/dev/null

BASE="http://127.0.0.1:${WEB_PORT}"
curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  --max-redirs 0 --header "Host: ${PUBLIC_HOST}" \
  --dump-header "${HEADER_FILE}" --output "${DOWNLOADED}" \
  "${BASE}/smartploy-playwright-assistant.zip"
curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  --max-redirs 0 --header "Host: ${PUBLIC_HOST}" \
  --output "${SIDE_CAR}" \
  "${BASE}/smartploy-playwright-assistant.zip.sha256"

# Reject HTML SPA fallbacks, stale Caddy images, stale web bundles, altered
# download links, arbitrary sidecar paths or unaudited local assistant permissions.
if ! grep -Eiq '^cache-control:.*no-store([[:space:]]|$)' "${HEADER_FILE}"; then
  echo "SmartPloy Playwright release: download is not marked no-store" >&2
  exit 1
fi
if [[ "$(wc -l < "${SIDE_CAR}" | tr -d '[:space:]')" != "1" ]] ||
   ! grep -Eq '^[a-f0-9]{64}  smartploy-playwright-assistant\.zip$' "${SIDE_CAR}"; then
  echo "SmartPloy Playwright release: invalid SHA256 sidecar" >&2
  exit 1
fi
(cd "${TMP_DIR}" && sha256sum -c smartploy-playwright-assistant.zip.sha256 >/dev/null)
if ! cmp -s "${SOURCE_BUILT}" "${DOWNLOADED}"; then
  echo "SmartPloy Playwright release: served ZIP differs from exact reviewed source" >&2
  exit 1
fi

DIGEST="$(sha256sum "${DOWNLOADED}" | cut -d ' ' -f 1)"
echo "playwright_release_verified=true"
echo "playwright_zip_sha256=${DIGEST}"

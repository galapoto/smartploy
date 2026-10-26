#!/usr/bin/env bash
# SP45: fail-closed, read-only proof that Caddy is serving EXACT reviewed
# extension bytes from this approved source checkout, not stale/missing SPA HTML.
# This script does not access applicants, DB, sessions, or employer websites.
set -Eeuo pipefail
umask 077

if [[ "$#" -ne 2 || ! "${1:-}" =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ ||
      ! "${2:-}" =~ ^[0-9]{4,5}$ ]] ; then
  echo "Usage: assert-companion-release.sh <validated-public-host> <local-web-port>" >&2
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

SOURCE_BUILT="${TMP_DIR}/source-reviewed.zip"
DOWNLOADED="${TMP_DIR}/smartploy-apply-companion.zip"
SIDE_CAR="${DOWNLOADED}.sha256"
HEADER_FILE="${TMP_DIR}/companion-headers"

# Deterministic stdlib packager already validates imported modules, manifest
# permissions and the source allowlist. Build into a *temporary* directory;
# never contaminate a production source tree/public asset.
python3 -B "${REPO_ROOT}/web/scripts/package_companion.py" \
  --output "${SOURCE_BUILT}" >/dev/null

BASE="http://127.0.0.1:${WEB_PORT}"
curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  --max-redirs 0 --header "Host: ${PUBLIC_HOST}" \
  --dump-header "${HEADER_FILE}" --output "${DOWNLOADED}" \
  "${BASE}/smartploy-apply-companion.zip"
curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  --max-redirs 0 --header "Host: ${PUBLIC_HOST}" \
  --output "${SIDE_CAR}" \
  "${BASE}/smartploy-apply-companion.zip.sha256"

# Reject HTML SPA fallbacks, stale Caddy images, stale web bundles, altered
# download links, arbitrary sidecar paths or unaudited extension permissions.
if ! grep -Eiq '^cache-control:.*no-store([[:space:]]|$)' "${HEADER_FILE}"; then
  echo "SmartPloy companion release: download is not marked no-store" >&2
  exit 1
fi
if [[ "$(wc -l < "${SIDE_CAR}" | tr -d '[:space:]')" != "1" ]] ||
   ! grep -Eq '^[a-f0-9]{64}  smartploy-apply-companion\.zip$' "${SIDE_CAR}"; then
  echo "SmartPloy companion release: invalid SHA256 sidecar" >&2
  exit 1
fi
(cd "${TMP_DIR}" && sha256sum -c smartploy-apply-companion.zip.sha256 >/dev/null)
if ! cmp -s "${SOURCE_BUILT}" "${DOWNLOADED}"; then
  echo "SmartPloy companion release: served ZIP differs from exact reviewed source" >&2
  exit 1
fi

DIGEST="$(sha256sum "${DOWNLOADED}" | cut -d ' ' -f 1)"
echo "companion_release_verified=true"
echo "companion_zip_sha256=${DIGEST}"

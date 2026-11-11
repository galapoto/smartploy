#!/usr/bin/env bash
# Read-only attestation: actual Caddy image serves the EXACT source-reviewed
# local Playwright helper, including pinned ObumAI provenance, not SPA fallback.
# ADAPTED from first-party assert-companion-release.sh (SP45).
set -Eeuo pipefail
umask 077
if [[ "$#" -ne 2 || ! "$1" =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ ||
      ! "$2" =~ ^[0-9]{4,5}$ ]]; then
  echo "Usage: assert-playwright-release.sh <validated-public-host> <local-web-port>" >&2
  exit 2
fi
PUBLIC_HOST="$1"
WEB_PORT="$2"
if (( 10#$WEB_PORT < 1024 || 10#$WEB_PORT > 65535 )); then
  echo "Invalid SmartPloy local web port." >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
for cmd in python3 curl cmp sha256sum grep wc; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing Playwright release verifier: $cmd" >&2; exit 1;
  }
done
python3 -B "$REPO_ROOT/web/scripts/package_playwright_assistant.py" \
  --output "$TMP/source-reviewed.zip" >/dev/null
BASE="http://127.0.0.1:$WEB_PORT"
curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  --max-redirs 0 --header "Host: $PUBLIC_HOST" \
  --dump-header "$TMP/headers" --output "$TMP/smartploy-playwright-assistant.zip" \
  "$BASE/smartploy-playwright-assistant.zip"
curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  --max-redirs 0 --header "Host: $PUBLIC_HOST" \
  --output "$TMP/smartploy-playwright-assistant.zip.sha256" \
  "$BASE/smartploy-playwright-assistant.zip.sha256"
grep -Eiq '^cache-control:.*no-store([[:space:]]|$)' "$TMP/headers" || {
  echo "SmartPloy Playwright release: missing no-store header" >&2; exit 1;
}
[[ "$(wc -l < "$TMP/smartploy-playwright-assistant.zip.sha256" | tr -d '[:space:]')" == "1" ]] || {
  echo "SmartPloy Playwright release: invalid checksum line count" >&2; exit 1;
}
grep -Eq '^[a-f0-9]{64}  smartploy-playwright-assistant\.zip$' \
  "$TMP/smartploy-playwright-assistant.zip.sha256" || {
  echo "SmartPloy Playwright release: invalid checksum format" >&2; exit 1;
}
(cd "$TMP" && sha256sum -c smartploy-playwright-assistant.zip.sha256 >/dev/null)
cmp -s "$TMP/source-reviewed.zip" "$TMP/smartploy-playwright-assistant.zip" || {
  echo "SmartPloy Playwright release: stale or changed packaged helper" >&2; exit 1;
}
printf 'playwright_helper_release_verified=true\nplaywright_helper_zip_sha256=%s\n' \
  "$(sha256sum "$TMP/smartploy-playwright-assistant.zip" | cut -d ' ' -f 1)"

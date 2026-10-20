#!/usr/bin/env bash
set -euo pipefail

POLICY_FILE="${1:-}"
if [[ -z "${POLICY_FILE}" || ! -f "${POLICY_FILE}" ]]; then
  echo "Usage: validate-runtime-policy.sh <runtime.production.env|runtime.oidc.production.env>" >&2
  exit 1
fi

case "$(basename "${POLICY_FILE}")" in
  runtime.production.env)
    EXPECTED_AUTH_MODE=cloudflare
    EXPECTED_ACCESS_ENABLED=true
    ;;
  runtime.oidc.production.env)
    EXPECTED_AUTH_MODE=oidc
    EXPECTED_ACCESS_ENABLED=false
    ;;
  *) echo "SmartPloy runtime policy must be one of the two committed identity profiles" >&2; exit 1 ;;
esac
EXPECTED="$(cat <<EOF
SMARTPLOY_ENVIRONMENT=production
SMARTPLOY_HOST=0.0.0.0
SMARTPLOY_PORT=8090
SMARTPLOY_PUBLIC_ORIGIN=https://smartploy.obumai.com
SMARTPLOY_ALLOWED_HOSTS=smartploy.obumai.com
SMARTPLOY_AUTH_MODE=${EXPECTED_AUTH_MODE}
SMARTPLOY_ACCESS_ENABLED=${EXPECTED_ACCESS_ENABLED}
EOF
)"

ACTUAL="$(
  sed -e 's/[[:space:]]*$//' "${POLICY_FILE}"     | grep -v '^[[:space:]]*#'     | grep -v '^[[:space:]]*$'
)"

if [[ "${ACTUAL}" != "${EXPECTED}" ]]; then
  echo "Committed SmartPloy production policy does not match the approved allowlist." >&2
  exit 1
fi

echo "SmartPloy production policy: validated (${EXPECTED_AUTH_MODE})"

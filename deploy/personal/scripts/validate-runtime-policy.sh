#!/usr/bin/env bash
set -euo pipefail

POLICY_FILE="${1:-}"
if [[ -z "${POLICY_FILE}" || ! -f "${POLICY_FILE}" ]]; then
  echo "Usage: validate-runtime-policy.sh <runtime.production.env>" >&2
  exit 1
fi

EXPECTED="$(cat <<'EOF'
SMARTPLOY_ENVIRONMENT=production
SMARTPLOY_HOST=0.0.0.0
SMARTPLOY_PORT=8090
SMARTPLOY_PUBLIC_ORIGIN=https://smartploy.obumai.com
SMARTPLOY_ALLOWED_HOSTS=smartploy.obumai.com
SMARTPLOY_ACCESS_ENABLED=true
EOF
)"

ACTUAL="$(
  sed -e 's/[[:space:]]*$//' "${POLICY_FILE}"     | grep -v '^[[:space:]]*#'     | grep -v '^[[:space:]]*$'
)"

if [[ "${ACTUAL}" != "${EXPECTED}" ]]; then
  echo "Committed SmartPloy production policy does not match the approved allowlist." >&2
  exit 1
fi

echo "SmartPloy production policy: validated"

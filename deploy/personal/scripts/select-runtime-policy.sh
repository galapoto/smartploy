#!/usr/bin/env bash
set -euo pipefail

# Reuse the original immutable runtime.production.env rather than creating
# an independent deployment stack. Only two committed policy choices exist.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODE="${SMARTPLOY_PRODUCTION_IDENTITY_MODE:-cloudflare}"
case "${MODE}" in
  cloudflare) POLICY="${COMPOSE_DIR}/runtime.production.env" ;;
  oidc) POLICY="${COMPOSE_DIR}/runtime.oidc.production.env" ;;
  *) echo "SmartPloy identity profile must be cloudflare or oidc" >&2; exit 1 ;;
esac

if [[ ! -f "${POLICY}" || -L "${POLICY}" ]]; then
  echo "SmartPloy committed identity profile is absent or a symlink" >&2
  exit 1
fi
printf '%s\n' "${POLICY}"

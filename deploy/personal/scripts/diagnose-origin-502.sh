#!/usr/bin/env bash
# Read-only origin triage. Does not print environment values, tokens, or logs.
set -u

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ENV_FILE="$REPO_ROOT/deploy/personal/env"
SCRIPT_DIR="$REPO_ROOT/deploy/personal/scripts"
POLICY_FILE="$(bash "$SCRIPT_DIR/select-runtime-policy.sh" 2>/dev/null || true)"
if [ -z "$POLICY_FILE" ] || ! bash "$SCRIPT_DIR/validate-runtime-policy.sh" "$POLICY_FILE" >/dev/null 2>&1; then
  printf 'diagnostic=smartploy-502-v1\nruntime_policy=invalid_or_missing\n'
  exit 0
fi
PRODUCTION_ORIGIN="$(sed -n 's/^SMARTPLOY_PUBLIC_ORIGIN=//p' "$POLICY_FILE")"
PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"
COMPOSE_FILE="$REPO_ROOT/deploy/personal/docker-compose.yml"
WEB_PORT=8091
printf 'diagnostic=smartploy-502-v1\nread_only=true\n'

if [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ]; then
  printf 'production_env=present\n'
  custom_port="$(sed -n 's/^SMARTPLOY_WEB_HOST_PORT=//p' "$ENV_FILE" | tail -n 1)"
  if [ -n "$custom_port" ]; then
    if [[ "$custom_port" =~ ^[0-9]+$ ]] && (( custom_port >= 1024 && custom_port <= 65535 )); then
      WEB_PORT="$custom_port"
    else
      printf 'configured_web_port=invalid\n'
    fi
  fi
else
  printf 'production_env=missing_or_symlink\n'
fi
printf 'web_port=%s\n' "$WEB_PORT"

if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  printf 'docker=available\n'
  if [ -f "$ENV_FILE" ] && [ -f "$POLICY_FILE" ] && [ -f "$COMPOSE_FILE" ]; then
    running="$(docker compose --env-file "$ENV_FILE" --env-file "$POLICY_FILE" -f "$COMPOSE_FILE" ps --status running --services 2>/dev/null || true)"
    for service in postgres api worker web; do
      if grep -Fxq "$service" <<< "$running"; then
        printf 'service_%s=running\n' "$service"
      else
        printf 'service_%s=not_running_or_unavailable\n' "$service"
      fi
    done
  else
    printf 'compose_runtime=not_configured\n'
  fi
else
  printf 'docker=unavailable_or_permission_denied\n'
fi

if command -v systemctl >/dev/null; then
  for unit in caddy cloudflared; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    printf 'systemd_%s=%s\n' "$unit" "$state"
  done
fi
if command -v ss >/dev/null; then
  for port in 443 "$WEB_PORT"; do
    if ss -H -ltn "( sport = :$port )" 2>/dev/null | grep -q .; then
      printf 'tcp_listen_%s=yes\n' "$port"
    else
      printf 'tcp_listen_%s=no_or_unavailable\n' "$port"
    fi
  done
fi

probe() {
  curl --silent --max-time 7 --connect-timeout 3 --output /dev/null \
    --write-out '%{http_code}' "$@" 2>/dev/null || true
}
if ! command -v curl >/dev/null; then
  printf 'curl=unavailable\n'
  exit 0
fi
health="$(probe -H "Host: ${PRODUCTION_HOST}" "http://127.0.0.1:$WEB_PORT/healthz")"
root="$(probe -H "Host: ${PRODUCTION_HOST}" "http://127.0.0.1:$WEB_PORT/")"
host_https="$(probe --connect-to "${PRODUCTION_HOST}:443:127.0.0.1:443" "${PRODUCTION_ORIGIN}/healthz")"
printf 'loopback_health_http=%s\nloopback_root_http=%s\nhost_https_health_http=%s\n' "$health" "$root" "$host_https"
if [ "$health" != '200' ]; then
  printf 'next_check=smartploy_web_api_or_database\n'
elif [ "$host_https" != '200' ]; then
  printf 'next_check=host_ingress_or_origin_tls\n'
else
  printf 'next_check=cloudflare_origin_route_or_policy\n'
fi
printf 'diagnostic_complete=true\n'

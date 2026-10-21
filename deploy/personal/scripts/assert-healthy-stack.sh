#!/usr/bin/env bash
# Read-only bounded health gate for all four SmartPloy services.
# Does not print secret-bearing environment values or container logs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

fail() {
  echo "SmartPloy stack health: $1" >&2
  exit 1
}

for command_name in docker sleep seq; do
  command -v "$command_name" >/dev/null 2>&1 || fail "required command unavailable: $command_name"
done

[[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]] || fail "private production env is missing"
[[ -f "$POLICY_FILE" && ! -L "$POLICY_FILE" ]] || fail "production runtime policy is missing"
bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "$POLICY_FILE" >/dev/null

COMPOSE=(
  docker compose
  --env-file "$ENV_FILE"
  --env-file "$POLICY_FILE"
  -f "$COMPOSE_FILE"
)

# Inspect only Docker's state/health flags; never call an app endpoint or
# trust a healthy status from an exited container.
service_health() {
  local service="$1" container_id=""
  container_id="$("${COMPOSE[@]}" ps -q "$service" 2>/dev/null || true)"
  if [[ -z "$container_id" ]]; then
    echo "missing"
    return
  fi
  docker inspect --format '{{if .State.Running}}{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}{{else}}not-running{{end}}' "$container_id" 2>/dev/null || echo "unavailable"
}

for attempt in $(seq 1 60); do
  all_healthy=true
  for service in postgres api worker web; do
    status="$(service_health "$service")"
    if [[ "$status" != healthy ]]; then
      all_healthy=false
    fi
  done
  if "$all_healthy"; then
    echo "SmartPloy stack health: PASS (postgres, api, worker, web healthy)"
    exit 0
  fi
  if (( attempt < 60 )); then
    sleep 2
  fi
done

echo "SmartPloy stack health: FAILED after bounded wait" >&2
for service in postgres api worker web; do
  printf 'service_%s=%s\n' "$service" "$(service_health "$service")" >&2
done
exit 1

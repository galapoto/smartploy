#!/usr/bin/env bash
# A tiny, opt-in, model-only Docker bridge. No host ports or Core redeployment.
# --status is read-only; --connect is the only mutating action.
set -euo pipefail

MODE="${1:---status}"
if [[ "$#" -gt 1 || ( "$MODE" != "--status" && "$MODE" != "--connect" ) ]]; then
  echo "Usage: bridge-local-ollama.sh [--status|--connect]" >&2
  exit 2
fi

NETWORK="smartploy-ollama-private"
LABEL="smartploy.local-ollama=private"
MODEL="${SMARTPLOY_BRIDGE_MODEL:-qwen3:4b}"

fail() {
  echo "SmartPloy private Ollama bridge: $1" >&2
  exit 1
}

for command_name in docker grep; do
  command -v "$command_name" >/dev/null 2>&1 || fail "missing required command: $command_name"
done

if [[ ! "$MODEL" =~ ^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,95}$ ]]; then
  fail "model name must be a simple Ollama model identifier"
fi

service_id() {
  local project="$1" service="$2" rows
  rows="$(docker ps --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=$service" --format '{{.ID}}')"
  if [[ -z "$rows" || "$rows" == *$'\n'* ]]; then
    fail "expected exactly one running $project/$service service"
  fi
  printf '%s' "$rows"
}

CORE="$(service_id obumai-personal ollama)"
API="$(service_id smartploy api)"

# Both containers must be healthy before attaching a trusted model network.
container_health() {
  docker inspect --format '{{if .State.Running}}{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}{{else}}stopped{{end}}' "$1"
}
[[ "$(container_health "$CORE")" == "healthy" ]] || fail "ObumAI Ollama container is not healthy"
[[ "$(container_health "$API")" == "healthy" ]] || fail "SmartPloy API container is not healthy"

CORE_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$CORE")"
API_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$API")"
case "$CORE_IMAGE" in ollama/ollama:*) ;; *) fail "unexpected ObumAI model image" ;; esac
case "$API_IMAGE" in smartploy-api:*) ;; *) fail "unexpected SmartPloy API image" ;; esac

network_present=false
if docker network inspect "$NETWORK" >/dev/null 2>&1; then
  network_present=true
  driver="$(docker network inspect --format '{{.Driver}}' "$NETWORK")"
  internal="$(docker network inspect --format '{{.Internal}}' "$NETWORK")"
  actual_label="$(docker network inspect --format '{{index .Labels "smartploy.local-ollama"}}' "$NETWORK")"
  [[ "$driver" == "bridge" && "$internal" == "true" && "$actual_label" == "private" ]] ||
    fail "existing network is not the approved internal model-only bridge"
fi

member() {
  # Exact container-id comparison; never trust a similar-looking container name.
  local network="$1" target="$2"
  docker network inspect --format '{{range .Containers}}{{println .Name}}{{end}}' "$network" |
    grep -Fxq "$(docker inspect --format '{{.Name}}' "$target" | tr -d '/')"
}

if [[ "$MODE" == "--connect" ]]; then
  if [[ "$network_present" != true ]]; then
    docker network create --driver bridge --internal --label "$LABEL" "$NETWORK" >/dev/null
    network_present=true
  fi
  # Only these two named Compose services may join this model-only network.
  if ! member "$NETWORK" "$CORE"; then
    docker network connect --alias ollama "$NETWORK" "$CORE"
  fi
  if ! member "$NETWORK" "$API"; then
    docker network connect "$NETWORK" "$API"
  fi
fi

echo "model_container_healthy=true"
echo "smartploy_api_healthy=true"
echo "model_network_internal=$network_present"

if [[ "$network_present" != true ]]; then
  echo "model_container_attached=false"
  echo "smartploy_api_attached=false"
  echo "model_endpoint_reachable=false"
  echo "required_model_present=false"
  echo "diagnosis=private_bridge_not_yet_commissioned"
  exit 0
fi

if member "$NETWORK" "$CORE"; then echo "model_container_attached=true"; else
  echo "model_container_attached=false"
  [[ "$MODE" == "--connect" ]] && fail "model could not join isolated network"
  exit 0
fi
if member "$NETWORK" "$API"; then echo "smartploy_api_attached=true"; else
  echo "smartploy_api_attached=false"
  [[ "$MODE" == "--connect" ]] && fail "API could not join isolated network"
  exit 0
fi

# Probe model catalog only, never infer and never print any CV, secret,
# authorization header, full error body, or model-generated output.
docker exec -i "$API" python - "$MODEL" <<'PY'
import json
import sys
import urllib.request

wanted = sys.argv[1]
try:
    with urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5) as response:
        result = json.loads(response.read(500000))
    names = {
        item.get("name") for item in result.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    print("model_endpoint_reachable=true")
    print("installed_model_count=" + str(len(names)))
    print("required_model_present=" + str(wanted in names).lower())
    if wanted not in names:
        sys.exit(4)
except (OSError, ValueError, TypeError, KeyError):
    print("model_endpoint_reachable=false")
    print("required_model_present=false")
    sys.exit(5)
PY

echo "SmartPloy private Ollama bridge: PASS"

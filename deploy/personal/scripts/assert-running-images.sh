#!/usr/bin/env bash
# Read-only: verify running SmartPloy services use precisely the built release images.
# Do not emit production environment, container labels, or credentials.
set -euo pipefail

EXPECTED_SHA="${1:-}"
if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SmartPloy image provenance: expected an exact 40-character Git SHA" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="${COMPOSE_DIR}/runtime.production.env"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
[[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]] || {
  echo "SmartPloy image provenance: private production env missing" >&2
  exit 1
}
[[ -f "$POLICY_FILE" && ! -L "$POLICY_FILE" ]] || {
  echo "SmartPloy image provenance: production policy missing" >&2
  exit 1
}

export SMARTPLOY_IMAGE_TAG="${EXPECTED_SHA:0:12}"
COMPOSE=(
  docker compose
  --env-file "$ENV_FILE"
  --env-file "$POLICY_FILE"
  -f "$COMPOSE_FILE"
)

for service in api worker web; do
  image_name="smartploy-api"
  if [[ "$service" == "web" ]]; then
    image_name="smartploy-web"
  fi
  ref="${image_name}:${SMARTPLOY_IMAGE_TAG}"
  expected_id="$(docker image inspect --format '{{.Id}}' "$ref" 2>/dev/null || true)"
  if [[ ! "$expected_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "SmartPloy image provenance: missing built image for $service" >&2
    exit 1
  fi

  container_id="$("${COMPOSE[@]}" ps -q "$service" 2>/dev/null || true)"
  if [[ ! "$container_id" =~ ^[0-9a-f]{12,64}$ ]]; then
    echo "SmartPloy image provenance: expected exactly one running $service container" >&2
    exit 1
  fi

  # .Image is the immutable image ID used to create this container.
  running_id="$(docker inspect --format '{{.Image}}' "$container_id" 2>/dev/null || true)"
  if [[ "$running_id" != "$expected_id" ]]; then
    echo "SmartPloy image provenance: $service runs an image other than expected release $SMARTPLOY_IMAGE_TAG" >&2
    exit 1
  fi
  printf 'service_%s_image_verified=true\n' "$service"
done

echo "SmartPloy image provenance: PASS"

#!/usr/bin/env bash
set -euo pipefail

ONLINE=false
if [[ "${1:-}" == "--online" ]]; then
  ONLINE=true
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: preflight.sh [--online]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="${COMPOSE_DIR}/runtime.production.env"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

fail() {
  echo "SmartPloy preflight: $1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

read_env_value() {
  local name="$1"
  sed -n "s/^${name}=//p" "${ENV_FILE}" | tail -n 1
}

is_placeholder() {
  local value="$1"
  local folded
  folded="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')"
  [[ "${folded}" == *"replace-with"* || "${folded}" == *"your-team"* || "${folded}" == *"<"* || "${folded}" == *">"* ]]
}

for command_name in docker git curl flock realpath sha256sum stat grep sed awk python; do
  require_command "${command_name}"
done

[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]]   || fail "deploy/personal/env must exist as a regular non-symlink file"
[[ -f "${POLICY_FILE}" && ! -L "${POLICY_FILE}" ]]   || fail "runtime.production.env must exist as a regular non-symlink file"
[[ -f "${COMPOSE_FILE}" && ! -L "${COMPOSE_FILE}" ]]   || fail "docker-compose.yml must exist as a regular non-symlink file"

ENV_MODE="$(stat -c '%a' "${ENV_FILE}")"
[[ "${ENV_MODE}" =~ ^[0-7]{3,4}$ ]] || fail "unable to determine deploy/personal/env permissions"
if (( (8#${ENV_MODE} & 077) != 0 )); then
  fail "deploy/personal/env must not be group/world readable; chmod 600 is recommended"
fi

docker info >/dev/null 2>&1 || fail "Docker Engine is unavailable to the current operator"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"

bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null

POSTGRES_DB="$(read_env_value POSTGRES_DB)"
POSTGRES_USER="$(read_env_value POSTGRES_USER)"
POSTGRES_PASSWORD="$(read_env_value POSTGRES_PASSWORD)"
WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
ACCESS_ISSUER="$(read_env_value SMARTPLOY_ACCESS_ISSUER)"
ACCESS_AUDIENCE="$(read_env_value SMARTPLOY_ACCESS_AUDIENCE)"
ACCESS_EMAIL="$(read_env_value SMARTPLOY_ACCESS_ALLOWED_EMAIL)"
BACKUP_DIR="$(read_env_value SMARTPLOY_BACKUP_DIR)"
STATE_DIR="$(read_env_value SMARTPLOY_DEPLOY_STATE_DIR)"
ATS_JSON="$(read_env_value SMARTPLOY_PUBLIC_ATS_SOURCES_JSON)"
ATS_FILE="$(read_env_value SMARTPLOY_PUBLIC_ATS_SOURCES_FILE)"
OBUMAI_BASE_URL="$(read_env_value OBUMAI_BASE_URL)"
JOBMARKET_ENABLED="$(read_env_value JOBMARKET_FINLAND_API_ENABLED)"
JOBMARKET_KEY="$(read_env_value JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY)"
KUNTAREKRY_URL="$(read_env_value KUNTAREKRY_FEED_URL)"

[[ "${POSTGRES_DB}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}$ ]]   || fail "POSTGRES_DB has an invalid format"
[[ "${POSTGRES_USER}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}$ ]]   || fail "POSTGRES_USER has an invalid format"

if is_placeholder "${POSTGRES_PASSWORD}" || [[ ! "${POSTGRES_PASSWORD}" =~ ^[A-Za-z0-9._~-]{24,}$ ]]; then
  fail "POSTGRES_PASSWORD must be a non-placeholder URL-safe value of at least 24 characters"
fi

[[ "${WEB_PORT}" =~ ^[0-9]+$ ]] || fail "SMARTPLOY_WEB_HOST_PORT must be numeric"
if (( WEB_PORT < 1024 || WEB_PORT > 65535 )); then
  fail "SMARTPLOY_WEB_HOST_PORT must be between 1024 and 65535"
fi

if is_placeholder "${ACCESS_ISSUER}" || [[ ! "${ACCESS_ISSUER}" =~ ^https://[A-Za-z0-9.-]+$ ]]; then
  fail "SMARTPLOY_ACCESS_ISSUER must be a non-placeholder origin-style HTTPS issuer"
fi
if is_placeholder "${ACCESS_AUDIENCE}" || [[ ! "${ACCESS_AUDIENCE}" =~ ^[A-Za-z0-9._~:/+-]{10,2048}$ ]]; then
  fail "SMARTPLOY_ACCESS_AUDIENCE must be a non-placeholder audience identifier"
fi
if is_placeholder "${ACCESS_EMAIL}" || [[ ! "${ACCESS_EMAIL}" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  fail "SMARTPLOY_ACCESS_ALLOWED_EMAIL must contain one non-placeholder email"
fi

[[ "${BACKUP_DIR}" == /* ]] || fail "SMARTPLOY_BACKUP_DIR must be an absolute path"
[[ "${STATE_DIR}" == /* ]] || fail "SMARTPLOY_DEPLOY_STATE_DIR must be an absolute path"

if [[ -n "${ATS_FILE}" ]]; then
  fail "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE is not mounted by this production stack; use SMARTPLOY_PUBLIC_ATS_SOURCES_JSON"
fi

if [[ -n "${ATS_JSON}" ]]; then
  if ! printf '%s' "${ATS_JSON}" | python -c '
import json
import sys

try:
    value = json.load(sys.stdin)
except json.JSONDecodeError as exc:
    raise SystemExit(f"SMARTPLOY_PUBLIC_ATS_SOURCES_JSON is invalid JSON: {exc}")
if not isinstance(value, list):
    raise SystemExit("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON must be a JSON array")
'; then
    fail "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON failed validation"
  fi
fi

if [[ -n "${OBUMAI_BASE_URL}" && ! "${OBUMAI_BASE_URL}" =~ ^https:// ]]; then
  fail "OBUMAI_BASE_URL must use HTTPS when configured"
fi

case "${JOBMARKET_ENABLED,,}" in
  true|1|yes|on)
    [[ -n "${JOBMARKET_KEY}" ]] || fail "Job Market Finland is enabled but its subscription key is empty"
    is_placeholder "${JOBMARKET_KEY}" && fail "Job Market Finland is enabled with a placeholder subscription key"
    JOBMARKET_STATUS=enabled
    ;;
  false|0|no|off|"")
    JOBMARKET_STATUS=disabled
    ;;
  *)
    fail "JOBMARKET_FINLAND_API_ENABLED must be boolean"
    ;;
esac

KUNTAREKRY_STATUS=disabled
[[ -n "${KUNTAREKRY_URL}" ]] && KUNTAREKRY_STATUS=enabled
ATS_STATUS=disabled
[[ -n "${ATS_JSON}" ]] && ATS_STATUS=enabled
OBUMAI_STATUS=disabled
[[ -n "${OBUMAI_BASE_URL}" ]] && OBUMAI_STATUS=enabled

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  --env-file "${POLICY_FILE}"
  -f "${COMPOSE_FILE}"
)

COMPOSE_JSON="$(mktemp)"
cleanup() {
  rm -f "${COMPOSE_JSON}"
}
trap cleanup EXIT

"${COMPOSE[@]}" config --format json > "${COMPOSE_JSON}"

python - "${COMPOSE_JSON}" "${WEB_PORT}" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_port = int(sys.argv[2])
services = config.get("services") or {}
required = {"postgres", "api", "worker", "web"}
missing = required - services.keys()
if missing:
    raise SystemExit("Compose is missing services: " + ", ".join(sorted(missing)))

for name in ("postgres", "api", "worker"):
    if services[name].get("ports"):
        raise SystemExit(f"{name} must not publish a host port")

ports = services["web"].get("ports") or []
if len(ports) != 1:
    raise SystemExit("web must publish exactly one host port")
port = ports[0]
host_ip = str(port.get("host_ip") or "")
published = int(port.get("published"))
target = int(port.get("target"))
if host_ip != "127.0.0.1" or published != expected_port or target != 8080:
    raise SystemExit("web ingress must be exactly 127.0.0.1:<configured>:8080")

api_env = services["api"].get("environment") or {}
worker_env = services["worker"].get("environment") or {}
web_env = services["web"].get("environment") or {}
postgres_env = services["postgres"].get("environment") or {}

api_forbidden = {
    "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY",
    "JOBMARKET_FINLAND_HTTP_HEADERS_JSON",
    "KUNTAREKRY_FEED_URL",
    "KUNTAREKRY_HTTP_HEADERS_JSON",
    "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON",
    "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE",
    "SMARTPLOY_WORKER_LOOP_SECONDS",
}
worker_forbidden = {
    "SMARTPLOY_ACCESS_ISSUER",
    "SMARTPLOY_ACCESS_AUDIENCE",
    "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
}
web_forbidden_prefixes = (
    "POSTGRES_",
    "SMARTPLOY_DATABASE_",
    "SMARTPLOY_ACCESS_",
    "OBUMAI_",
    "JOBMARKET_",
    "KUNTAREKRY_",
)
postgres_forbidden_prefixes = (
    "SMARTPLOY_ACCESS_",
    "OBUMAI_",
    "JOBMARKET_",
    "KUNTAREKRY_",
)

leaked_api = sorted(api_forbidden & api_env.keys())
leaked_worker = sorted(worker_forbidden & worker_env.keys())
leaked_web = sorted(
    key for key in web_env if key.startswith(web_forbidden_prefixes)
)
leaked_postgres = sorted(
    key for key in postgres_env if key.startswith(postgres_forbidden_prefixes)
)

if leaked_api:
    raise SystemExit("API environment contains forbidden keys: " + ", ".join(leaked_api))
if leaked_worker:
    raise SystemExit("Worker environment contains forbidden keys: " + ", ".join(leaked_worker))
if leaked_web:
    raise SystemExit("Web environment contains forbidden keys: " + ", ".join(leaked_web))
if leaked_postgres:
    raise SystemExit("PostgreSQL environment contains forbidden keys: " + ", ".join(leaked_postgres))

required_api = {
    "SMARTPLOY_DATABASE_URL",
    "SMARTPLOY_ACCESS_ISSUER",
    "SMARTPLOY_ACCESS_AUDIENCE",
    "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
}
required_worker = {
    "SMARTPLOY_DATABASE_URL",
    "JOBMARKET_FINLAND_API_ENABLED",
    "KUNTAREKRY_ALLOWED_HOSTS",
    "SMARTPLOY_WORKER_LOOP_SECONDS",
}
if not required_api <= api_env.keys():
    raise SystemExit("API environment is missing required allowlisted keys")
if not required_worker <= worker_env.keys():
    raise SystemExit("Worker environment is missing required allowlisted keys")
PY

if "${ONLINE}"; then
  require_command getent
  getent ahosts smartploy.obumai.com >/dev/null 2>&1     || fail "smartploy.obumai.com does not resolve"
  HTTP_STATUS="$(curl --silent --show-error --output /dev/null --max-time 10 --write-out '%{http_code}' https://smartploy.obumai.com/ || true)"
  [[ "${HTTP_STATUS}" =~ ^[0-9]{3}$ && "${HTTP_STATUS}" != "000" ]]     || fail "smartploy.obumai.com is not reachable over HTTPS"
  if (( HTTP_STATUS >= 500 )); then
    fail "smartploy.obumai.com returned server error HTTP ${HTTP_STATUS}"
  fi
fi

echo "SmartPloy preflight: PASS"
echo "  production environment: private"
echo "  loopback ingress: validated"
echo "  Cloudflare Access configuration: present"
echo "  ObumAI integration: ${OBUMAI_STATUS}"
echo "  Job Market Finland: ${JOBMARKET_STATUS}"
echo "  Kuntarekry: ${KUNTAREKRY_STATUS}"
echo "  Public ATS: ${ATS_STATUS}"
if "${ONLINE}"; then
  echo "  online reachability: validated"
else
  echo "  online reachability: skipped"
fi

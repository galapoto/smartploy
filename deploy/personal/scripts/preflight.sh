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
POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"
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

for command_name in docker git curl flock realpath sha256sum stat grep sed awk python3; do
  require_command "${command_name}"
done

[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]]   || fail "deploy/personal/env must exist as a regular non-symlink file"
[[ -f "${POLICY_FILE}" && ! -L "${POLICY_FILE}" ]]   || fail "selected runtime identity policy must be a regular non-symlink file"
[[ -f "${COMPOSE_FILE}" && ! -L "${COMPOSE_FILE}" ]]   || fail "docker-compose.yml must exist as a regular non-symlink file"

ENV_MODE="$(stat -c '%a' "${ENV_FILE}")"
[[ "${ENV_MODE}" =~ ^[0-7]{3,4}$ ]] || fail "unable to determine deploy/personal/env permissions"
if (( (8#${ENV_MODE} & 077) != 0 )); then
  fail "deploy/personal/env must not be group/world readable; chmod 600 is recommended"
fi

docker info >/dev/null 2>&1 || fail "Docker Engine is unavailable to the current operator"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"

bash "${SCRIPT_DIR}/validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null
# The selected, validated committed policy determines the ONLY public hostname.
# Never check the legacy hostname when a Komplyint OIDC cutover is requested.
POLICY_ORIGIN="$(sed -n 's/^SMARTPLOY_PUBLIC_ORIGIN=//p' "${POLICY_FILE}")"
POLICY_HOST="${POLICY_ORIGIN#https://}"

POSTGRES_DB="$(read_env_value POSTGRES_DB)"
POSTGRES_USER="$(read_env_value POSTGRES_USER)"
POSTGRES_PASSWORD="$(read_env_value POSTGRES_PASSWORD)"
WEB_PORT="$(read_env_value SMARTPLOY_WEB_HOST_PORT)"
ACCESS_ISSUER="$(read_env_value SMARTPLOY_ACCESS_ISSUER)"
ACCESS_AUDIENCE="$(read_env_value SMARTPLOY_ACCESS_AUDIENCE)"
ACCESS_EMAIL="$(read_env_value SMARTPLOY_ACCESS_ALLOWED_EMAIL)"
PROFILE="${SMARTPLOY_PRODUCTION_IDENTITY_MODE:-cloudflare}"
OIDC_ISSUER="$(read_env_value SMARTPLOY_OIDC_ISSUER)"
OIDC_CLIENT_ID="$(read_env_value SMARTPLOY_OIDC_CLIENT_ID)"
OIDC_REDIRECT_URI="$(read_env_value SMARTPLOY_OIDC_REDIRECT_URI)"
OIDC_LOGOUT_URI="$(read_env_value SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI)"
OIDC_SCOPE="$(read_env_value SMARTPLOY_OIDC_SCOPE)"
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

if [[ "${PROFILE}" == "cloudflare" ]]; then
  if is_placeholder "${ACCESS_ISSUER}" || [[ ! "${ACCESS_ISSUER}" =~ ^https://[A-Za-z0-9.-]+$ ]]; then
    fail "SMARTPLOY_ACCESS_ISSUER must be a non-placeholder origin-style HTTPS issuer"
  fi
  if is_placeholder "${ACCESS_AUDIENCE}" || [[ ! "${ACCESS_AUDIENCE}" =~ ^[A-Za-z0-9._~:/+-]{10,2048}$ ]]; then
    fail "SMARTPLOY_ACCESS_AUDIENCE must be a non-placeholder audience identifier"
  fi
  if is_placeholder "${ACCESS_EMAIL}" || [[ ! "${ACCESS_EMAIL}" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
    fail "SMARTPLOY_ACCESS_ALLOWED_EMAIL must contain one non-placeholder email"
  fi
else
  # Existing first-party OIDC settings: no new sign-in service or auth stack.
  if is_placeholder "${OIDC_ISSUER}" || [[ ! "${OIDC_ISSUER}" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{2,5})?$ ]]; then
    fail "SMARTPLOY_OIDC_ISSUER must be a real origin-only HTTPS issuer"
  fi
  if is_placeholder "${OIDC_CLIENT_ID}" || [[ -z "${OIDC_CLIENT_ID}" || "${#OIDC_CLIENT_ID}" -gt 2048 ]]; then
    fail "SMARTPLOY_OIDC_CLIENT_ID must be a real registered public-client identifier"
  fi
  # Never trust a callback from an operator-controlled alternative hostname.
  [[ "${OIDC_REDIRECT_URI}" == "${POLICY_ORIGIN}/auth/callback" ]] ||
    fail "OIDC redirect must exactly match SmartPloy signed-in callback"
  [[ "${OIDC_LOGOUT_URI}" == "${POLICY_ORIGIN}/auth/logged-out" ]] ||
    fail "OIDC logout must exactly match SmartPloy signed-out callback"
  [[ " ${OIDC_SCOPE:-openid profile email} " == *" openid "* ]] ||
    fail "OIDC scope must include openid"
fi
[[ "${BACKUP_DIR}" == /* ]] || fail "SMARTPLOY_BACKUP_DIR must be an absolute path"
[[ "${STATE_DIR}" == /* ]] || fail "SMARTPLOY_DEPLOY_STATE_DIR must be an absolute path"

if [[ -n "${ATS_FILE}" ]]; then
  fail "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE is not mounted by this production stack; use SMARTPLOY_PUBLIC_ATS_SOURCES_JSON"
fi

if [[ -n "${ATS_JSON}" ]]; then
  if ! printf '%s' "${ATS_JSON}" | python3 -c '
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

python3 - "${COMPOSE_JSON}" "${WEB_PORT}" "${PROFILE}" <<'PY'
import json
import re
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_port = int(sys.argv[2])
identity_profile = sys.argv[3]
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
    "SMARTPLOY_WORKER_AGENT_ZERO_ENABLED",
    "SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS",
    "SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT",
}
worker_forbidden = {
    "SMARTPLOY_ACCESS_ISSUER",
    "SMARTPLOY_OIDC_ISSUER",
    "SMARTPLOY_OIDC_CLIENT_ID",
    "SMARTPLOY_OIDC_REDIRECT_URI",
    "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
    "SMARTPLOY_ACCESS_AUDIENCE",
    "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
    "SMARTPLOY_LEVER_PARTNER_JOBS_JSON",
    "SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY",
    "SMARTPLOY_LEVER_PARTNER_KEY_SECONDARY",
    "SMARTPLOY_LEVER_PARTNER_KEY_TERTIARY",
}
web_forbidden_prefixes = (
    "SMARTPLOY_WORKER_AGENT_ZERO_",
    "POSTGRES_",
    "SMARTPLOY_DATABASE_",
    "SMARTPLOY_ACCESS_",
    "SMARTPLOY_OIDC_",
    "SMARTPLOY_LEVER_PARTNER_",
    "OBUMAI_",
    "JOBMARKET_",
    "KUNTAREKRY_",
)
postgres_forbidden_prefixes = (
    "SMARTPLOY_WORKER_AGENT_ZERO_",
    "SMARTPLOY_ACCESS_",
    "SMARTPLOY_LEVER_PARTNER_",
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


allowed_keys = {
    "SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY",
    "SMARTPLOY_LEVER_PARTNER_KEY_SECONDARY",
    "SMARTPLOY_LEVER_PARTNER_KEY_TERTIARY",
}
raw_partners = api_env.get("SMARTPLOY_LEVER_PARTNER_JOBS_JSON", "")
if not isinstance(raw_partners, str):
    raise SystemExit("Partner configuration must be a string")
try:
    partners = json.loads(raw_partners) if raw_partners.strip() else {}
except (ValueError, TypeError):
    raise SystemExit("Partner configuration JSON is invalid") from None
if not isinstance(partners, dict) or len(partners) > 100:
    raise SystemExit("Maximum 100 exact independently reviewed partner postings per stack")
selected_keys: set[str] = set()
for job, config in partners.items():
    if not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", job):
        raise SystemExit("Partner job must be an exact Lever site/posting ID")
    if not isinstance(config, dict) or set(config) != {
        "region", "form_review_sha256", "api_key_env",
        "standard_form_only_reviewed", "consent_policy_reviewed",
    }:
        raise SystemExit("Partner job must include exact audited form and consent fields")
    if (config["api_key_env"] not in allowed_keys
        or config["region"] not in {"eu", "global"}
        or config["standard_form_only_reviewed"] is not True
        or config["consent_policy_reviewed"] is not True
        or not isinstance(config["form_review_sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", config["form_review_sha256"])):
        raise SystemExit("Partner API configuration lacks reviewed form, consent or fixed key slot")
    key_slot = config["api_key_env"]
    key_value = api_env.get(key_slot, "")
    if (not isinstance(key_value, str) or not 16 <= len(key_value) <= 512
        or "replace-with" in key_value.casefold()
        or any(ord(char) < 33 or ord(char) > 126 for char in key_value)):
        raise SystemExit("Partner API credential is absent or invalid")
    selected_keys.add(key_slot)
for key_slot in allowed_keys - selected_keys:
    if str(api_env.get(key_slot, "")).strip():
        raise SystemExit("Unused partner API credential must not be present")

if identity_profile == "oidc":
    required_api = {
        "SMARTPLOY_DATABASE_URL", "SMARTPLOY_AUTH_MODE", "SMARTPLOY_ACCESS_ENABLED",
        "SMARTPLOY_OIDC_ISSUER", "SMARTPLOY_OIDC_CLIENT_ID",
        "SMARTPLOY_OIDC_REDIRECT_URI", "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
    }
    if (api_env.get("SMARTPLOY_AUTH_MODE") != "oidc"
        or str(api_env.get("SMARTPLOY_ACCESS_ENABLED")).lower() != "false"):
        raise SystemExit("OIDC-only profile must NOT enable Cloudflare assertion authentication")
else:
    required_api = {
        "SMARTPLOY_DATABASE_URL", "SMARTPLOY_AUTH_MODE", "SMARTPLOY_ACCESS_ENABLED",
        "SMARTPLOY_ACCESS_ISSUER", "SMARTPLOY_ACCESS_AUDIENCE", "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
    }
    if (api_env.get("SMARTPLOY_AUTH_MODE") != "cloudflare"
        or str(api_env.get("SMARTPLOY_ACCESS_ENABLED")).lower() != "true"):
        raise SystemExit("Legacy protected profile must require Cloudflare Access")

required_worker = {
    "SMARTPLOY_DATABASE_URL",
    "JOBMARKET_FINLAND_API_ENABLED",
    "KUNTAREKRY_ALLOWED_HOSTS",
    "SMARTPLOY_WORKER_LOOP_SECONDS",
    "SMARTPLOY_WORKER_AGENT_ZERO_ENABLED",
    "SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS",
    "SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT",
}
# Fail before backup, migrations or Docker recreation.  A private host
# env flag is not a valid activation until Compose actually passes it
# to the worker. No credentials or private values appear in errors.
if worker_env.get("SMARTPLOY_WORKER_AGENT_ZERO_ENABLED") not in {"true", "false"}:
    raise SystemExit("Agent Zero worker activation must be a literal boolean")
for key, maximum in (
    ("SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS", 86400),
    ("SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT", 50),
):
    raw = worker_env.get(key)
    if not isinstance(raw, str) or not raw.isdigit() or not 1 <= int(raw) <= maximum:
        raise SystemExit("Agent Zero worker cadence/batch policy invalid")
if not required_api <= api_env.keys():
    raise SystemExit("API environment is missing required allowlisted keys")
if not required_worker <= worker_env.keys():
    raise SystemExit("Worker environment is missing required allowlisted keys")
PY

if "${ONLINE}"; then
  require_command getent
  getent ahosts "${POLICY_HOST}" >/dev/null 2>&1 ||
    fail "selected production hostname does not resolve"
  HTTP_STATUS="$(curl --silent --show-error --output /dev/null --max-time 10 --write-out '%{http_code}' "${POLICY_ORIGIN}/" || true)"
  [[ "${HTTP_STATUS}" =~ ^[0-9]{3}$ && "${HTTP_STATUS}" != "000" ]] ||
    fail "selected production origin is not reachable over HTTPS"
  # On a FIRST new-host rollout, TLS may already work but the reverse
  # proxy can return 502 until this release installs the app containers.
  # This is *only* a pre-deploy exception for OIDC; post-deploy acceptance
  # still rejects any 5xx before writing the verified running SHA.
  if [[ "${PROFILE}" != "oidc" ]] && (( HTTP_STATUS >= 500 )); then
    fail "selected production origin returned server error HTTP ${HTTP_STATUS}"
  fi
  if [[ "${PROFILE}" == "oidc" ]]; then
    # Pre-deploy cannot require a working new login shell: that shell is
    # installed by THIS release. The post-deploy live-acceptance gate checks
    # the actual public root (200), signed-out API (401), trusted ZITADEL
    # redirect, and absence of a Cloudflare Access challenge BEFORE writing
    # the deployed SHA. Here verify TLS/DNS and issuer metadata only.
    OIDC_DISCOVERY="$(curl --fail --silent --show-error --max-time 10 \
      --max-filesize 65536 "${OIDC_ISSUER}/.well-known/openid-configuration")" ||
      fail "configured OIDC issuer discovery is unavailable over HTTPS"
    if ! printf '%s' "${OIDC_DISCOVERY}" | \
      python3 "${SCRIPT_DIR}/../../../scripts/check_oidc_metadata.py" "${OIDC_ISSUER}" >/dev/null; then
      fail "OIDC discovery issuer or public PKCE metadata does not match configuration"
    fi
    unset OIDC_DISCOVERY
  fi
fi

echo "SmartPloy preflight: PASS"
echo "  production environment: private"
echo "  loopback ingress: validated"
echo "  production identity profile: ${PROFILE} (no secrets echoed)"
echo "  ObumAI integration: ${OBUMAI_STATUS}"
echo "  Job Market Finland: ${JOBMARKET_STATUS}"
echo "  Kuntarekry: ${KUNTAREKRY_STATUS}"
echo "  Public ATS: ${ATS_STATUS}"
if "${ONLINE}"; then
  echo "  online reachability: validated"
else
  echo "  online reachability: skipped"
fi

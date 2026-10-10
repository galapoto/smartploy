#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${COMPOSE_DIR}/env"
POLICY_FILE="${COMPOSE_DIR}/runtime.production.env"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "SmartPloy environment-boundary smoke: production env missing" >&2
  exit 1
fi

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  --env-file "${POLICY_FILE}"
  -f "${COMPOSE_FILE}"
)

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT
chmod 700 "${TMP_DIR}"
umask 077

# Capture names only. Values are never written or printed.
"${COMPOSE[@]}" exec -T api \
  python -c 'import os; print("\n".join(sorted(os.environ)))' \
  > "${TMP_DIR}/api.keys"

"${COMPOSE[@]}" exec -T worker \
  python -c 'import os; print("\n".join(sorted(os.environ)))' \
  > "${TMP_DIR}/worker.keys"

"${COMPOSE[@]}" exec -T postgres \
  sh -c 'env | sed "s/=.*//" | sort -u' \
  > "${TMP_DIR}/postgres.keys"

"${COMPOSE[@]}" exec -T web \
  sh -c 'env | sed "s/=.*//" | sort -u' \
  > "${TMP_DIR}/web.keys"

python3 - "${TMP_DIR}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])


def names(service: str) -> set[str]:
    return {
        line.strip()
        for line in (root / f"{service}.keys").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


api = names("api")
worker = names("worker")
postgres = names("postgres")
web = names("web")

api_forbidden = {
    "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY",
    "JOBMARKET_FINLAND_HTTP_HEADERS_JSON",
    "KUNTAREKRY_FEED_URL",
    "KUNTAREKRY_HTTP_HEADERS_JSON",
    "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON",
    "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE",
    "SMARTPLOY_WORKER_LOOP_SECONDS",
    "SMARTPLOY_WORKER_LEASE_SECONDS",
    "SMARTPLOY_WORKER_MAX_BACKOFF_SECONDS",
    "SMARTPLOY_WORKER_CLAIM_LIMIT",
}
worker_forbidden = {
    "SMARTPLOY_ACCESS_ISSUER",
    "SMARTPLOY_OIDC_ISSUER",
    "SMARTPLOY_OIDC_CLIENT_ID",
    "SMARTPLOY_OIDC_REDIRECT_URI",
    "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
    "SMARTPLOY_ACCESS_AUDIENCE",
    "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
}
web_forbidden_prefixes = (
    "POSTGRES_",
    "SMARTPLOY_DATABASE_",
    "SMARTPLOY_ACCESS_",
    "SMARTPLOY_OIDC_",
    "OBUMAI_",
    "JOBMARKET_",
    "KUNTAREKRY_",
)
postgres_forbidden_prefixes = (
    "SMARTPLOY_",
    "OBUMAI_",
    "JOBMARKET_",
    "KUNTAREKRY_",
)

api_required = {
    "SMARTPLOY_DATABASE_URL",
    "SMARTPLOY_AUTH_MODE",
    "SMARTPLOY_ACCESS_ISSUER",
    "SMARTPLOY_ACCESS_AUDIENCE",
    "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
}
worker_required = {
    "SMARTPLOY_DATABASE_URL",
    "JOBMARKET_FINLAND_API_ENABLED",
    "KUNTAREKRY_ALLOWED_HOSTS",
    "SMARTPLOY_WORKER_LOOP_SECONDS",
}
postgres_required = {"POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "PGDATA"}


def fail(message: str) -> None:
    raise SystemExit(message)


if missing := sorted(api_required - api):
    fail("API runtime is missing required environment keys: " + ", ".join(missing))
if leaked := sorted(api_forbidden & api):
    fail("API runtime contains forbidden environment keys: " + ", ".join(leaked))

if missing := sorted(worker_required - worker):
    fail("Worker runtime is missing required environment keys: " + ", ".join(missing))
if leaked := sorted(worker_forbidden & worker):
    fail("Worker runtime contains forbidden environment keys: " + ", ".join(leaked))

if missing := sorted(postgres_required - postgres):
    fail("PostgreSQL runtime is missing required environment keys: " + ", ".join(missing))
if leaked := sorted(key for key in postgres if key.startswith(postgres_forbidden_prefixes)):
    fail("PostgreSQL runtime contains forbidden environment keys: " + ", ".join(leaked))

if leaked := sorted(key for key in web if key.startswith(web_forbidden_prefixes)):
    fail("Web runtime contains forbidden environment keys: " + ", ".join(leaked))

print("SmartPloy environment-boundary smoke: PASS")
print("  api: allowlist verified")
print("  worker: allowlist verified")
print("  postgres: bootstrap-only policy verified")
print("  web: no application/source secret classes present")
PY

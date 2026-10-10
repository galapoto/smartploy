from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\\n(.*?)(?=^  [a-zA-Z0-9_-]+:\\n|^networks:)",
        compose,
    )
    assert match is not None, f"missing service {service}"
    return match.group(1)


def test_compose_publishes_only_loopback_web_gateway():
    compose = (ROOT / "deploy/personal/docker-compose.yml").read_text(encoding="utf-8")

    for service in ("postgres", "api", "worker"):
        assert "ports:" not in _service_block(compose, service)

    web = _service_block(compose, "web")
    assert "ports:" in web
    assert "127.0.0.1:${SMARTPLOY_WEB_HOST_PORT:-8091}:8080" in web


def test_web_gateway_keeps_backend_routes_out_of_spa_fallback():
    caddy = (ROOT / "deploy/personal/web.Caddyfile").read_text(encoding="utf-8")

    assert "@backend path /api/* /healthz" in caddy
    assert "handle @backend" in caddy
    assert "reverse_proxy api:8090" in caddy
    assert "header_up Host smartploy.obumai.com" in caddy
    assert "Cf-Access-Jwt-Assertion" in caddy
    assert "try_files {path} /index.html" in caddy
    assert caddy.index("handle @backend") < caddy.index("try_files {path} /index.html")


def test_backup_is_private_checksummed_and_bounded():
    backup = (ROOT / "deploy/personal/scripts/backup.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in backup
    assert "umask 077" in backup
    assert "pg_dump" in backup
    assert "sha256sum" in backup
    assert "chmod 600" in backup
    assert "SMARTPLOY_BACKUP_KEEP" in backup


def test_deploy_gate_orders_backup_migration_start_health_and_sha_recording():
    deploy = (ROOT / "deploy/personal/scripts/deploy.sh").read_text(encoding="utf-8")

    assert "flock -n 9" in deploy
    backup_at = deploy.index('bash "${SCRIPT_DIR}/backup.sh"')
    migrate_at = deploy.index("python scripts/migrate.py")
    start_at = deploy.index("up -d --remove-orphans api worker web")
    health_at = deploy.index('http://127.0.0.1:${WEB_PORT}/healthz')
    record_at = deploy.index('"${STATE_DIR}/deployed-sha"')

    assert backup_at < migrate_at < start_at < health_at < record_at
    assert 'health["external_actions_authorized"] is False' in deploy


def test_committed_runtime_policy_contains_no_account_secrets():
    policy = (ROOT / "deploy/personal/runtime.production.env").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "SMARTPLOY_ENVIRONMENT=production" in policy
    assert "SMARTPLOY_ACCESS_ENABLED=true" in policy
    for forbidden in (
        "POSTGRES_PASSWORD",
        "SMARTPLOY_ACCESS_AUDIENCE",
        "SMARTPLOY_ACCESS_ALLOWED_EMAIL",
        "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY",
        "OBUMAI_HTTP_HEADERS_JSON",
    ):
        assert forbidden not in policy
    assert "deploy/personal/env" in gitignore


def test_host_caddy_targets_only_local_smartploy_gateway():
    host_caddy = (ROOT / "deploy/personal/Caddyfile.host.example").read_text(
        encoding="utf-8"
    )
    assert "smartploy.obumai.com" in host_caddy
    assert "reverse_proxy 127.0.0.1:8091" in host_caddy

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SCRIPT_DIR = ROOT / "deploy/personal/scripts"
EXPECTED_PRODUCTION_SCRIPTS = {
    "backup.sh",
    "deploy.sh",
    "live-acceptance.sh",
    "preflight.sh",
    "release-evidence.sh",
    "restore.sh",
    "smoke-env-boundaries.sh",
    "validate-runtime-policy.sh",
}


def test_all_production_shell_scripts_are_present_and_parse():
    scripts = sorted(PRODUCTION_SCRIPT_DIR.glob("*.sh"))
    names = {script.name for script in scripts}

    assert EXPECTED_PRODUCTION_SCRIPTS <= names
    assert scripts, "no production shell scripts discovered"

    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"invalid shell syntax in {script.relative_to(ROOT)}: "
            f"{result.stderr.strip()}"
        )


def _service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^networks:)",
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

    assert "@backend path /api/* /auth/* /healthz" in caddy
    assert "handle @backend" in caddy
    assert "reverse_proxy api:8090" in caddy
    assert "header_up Host smartploy.obumai.com" not in caddy
    assert "header_up X-Forwarded-Proto https" in caddy
    assert "Preserve the original Host header" in caddy
    assert "Cf-Access-Jwt-Assertion" in caddy
    assert "try_files {path} /index.html" in caddy
    assert caddy.index("handle @backend") < caddy.index("try_files {path} /index.html")


def test_komplyint_host_cutover_config_keeps_loopback_and_temporary_legacy_redirect():
    caddy = (ROOT / "deploy/personal/Caddyfile.host.example").read_text(
        encoding="utf-8"
    )
    assert "smartploy.komplyint.fi {" in caddy
    assert "reverse_proxy 127.0.0.1:8091" in caddy
    assert "smartploy.obumai.com {" in caddy
    assert "redir https://smartploy.komplyint.fi{uri} temporary" in caddy
    assert "0.0.0.0:8091" not in caddy
    assert "tls internal" not in caddy


def test_backup_is_private_checksummed_and_bounded():
    backup = (ROOT / "deploy/personal/scripts/backup.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in backup
    assert "umask 077" in backup
    assert "pg_dump" in backup
    assert "sha256sum" in backup
    assert "chmod 600" in backup
    assert "SMARTPLOY_BACKUP_KEEP" in backup
    assert 'up -d --wait postgres' in backup
    assert "production-operation.lock" in backup
    assert "SMARTPLOY_OPERATION_LOCK_HELD" in backup
    assert "format=smartploy-db-backup-v1" in backup
    assert "source_deployed_sha=" in backup
    assert '".meta"' in backup or ".meta" in backup


def test_deploy_gate_orders_backup_migration_start_health_and_sha_recording():
    deploy = (ROOT / "deploy/personal/scripts/deploy.sh").read_text(encoding="utf-8")

    assert "flock -n 9" in deploy
    assert 'up -d --wait postgres' in deploy
    backup_at = deploy.index('bash "${SCRIPT_DIR}/backup.sh"')
    migrate_at = deploy.index("python scripts/migrate.py")
    start_at = deploy.index("up -d --no-deps --force-recreate worker web")
    health_at = deploy.index('http://127.0.0.1:${WEB_PORT}/healthz')
    record_at = deploy.index('"${STATE_DIR}/deployed-sha"')

    image_at = deploy.index('assert-running-images.sh" "${DEPLOY_SHA}"')
    assert backup_at < migrate_at < start_at < health_at < image_at < record_at
    assert "up -d --wait --wait-timeout 120 --no-deps --force-recreate api" in deploy
    assert "up -d --no-deps --force-recreate worker web" in deploy
    assert 'health["external_actions_authorized"] is False' in deploy
    assert 'SMARTPLOY_OPERATION_LOCK_HELD=1 bash "${SCRIPT_DIR}/backup.sh"' in deploy


def test_committed_runtime_policy_contains_no_account_secrets():
    policy = (ROOT / "deploy/personal/runtime.production.env").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "SMARTPLOY_ENVIRONMENT=production" in policy
    assert "SMARTPLOY_AUTH_MODE=cloudflare" in policy
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


def test_compose_uses_single_init_boundary():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "deploy/personal/docker-compose.yml").read_text(encoding="utf-8")

    assert "PYTHONPATH=/workspace" in dockerfile
    assert 'ENTRYPOINT ["/usr/bin/tini"' not in dockerfile
    assert "/usr/bin/tini" not in _service_block(compose, "worker")
    assert "init: true" in _service_block(compose, "api")
    assert "init: true" in _service_block(compose, "worker")


def test_host_caddy_targets_only_local_smartploy_gateway():
    host_caddy = (ROOT / "deploy/personal/Caddyfile.host.example").read_text(
        encoding="utf-8"
    )
    assert "smartploy.obumai.com" in host_caddy
    assert "reverse_proxy 127.0.0.1:8091" in host_caddy


def test_restore_gate_verifies_artifact_quiesces_writes_and_records_evidence():
    restore = (ROOT / "deploy/personal/scripts/restore.sh").read_text(encoding="utf-8")

    assert "production-operation.lock" in restore
    assert 'BACKUP_ROOT="$(realpath "${BACKUP_DIR}")"' in restore
    assert "smartploy-*.dump" in restore
    assert "sha256sum -c" in restore
    assert "SMARTPLOY_BACKUP_SKIP_RETENTION=1" in restore

    safety_at = restore.index("SAFETY_OUTPUT=")
    stop_at = restore.index('"${COMPOSE[@]}" stop api worker web')
    restore_at = restore.index(
        "pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error"
    )
    migrate_at = restore.index("python scripts/migrate.py")
    health_at = restore.index('http://127.0.0.1:${WEB_PORT}/healthz')
    evidence_at = restore.index("format=smartploy-db-restore-v1")

    assert safety_at < stop_at < restore_at < migrate_at < health_at < evidence_at
    assert 'health["external_actions_authorized"] is False' in restore
    assert "health_verified=true" in restore
    assert 'export SMARTPLOY_IMAGE_TAG="${DEPLOYED_SHA:0:12}"' in restore
    assert 'assert-running-images.sh" "${DEPLOYED_SHA}"' in restore
    assert '> "${STATE_DIR}/deployed-sha"' not in restore


def test_compose_does_not_inject_whole_production_env_into_services():
    compose = (ROOT / "deploy/personal/docker-compose.yml").read_text(encoding="utf-8")

    for service in ("api", "worker", "web", "postgres"):
        block = _service_block(compose, service)
        assert "env_file:" not in block

    api = _service_block(compose, "api")
    worker = _service_block(compose, "worker")
    web = _service_block(compose, "web")
    postgres = _service_block(compose, "postgres")

    assert "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY" not in api
    assert "KUNTAREKRY_HTTP_HEADERS_JSON" not in api
    assert "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON" not in api
    assert "SMARTPLOY_WORKER_LOOP_SECONDS" not in api

    assert "SMARTPLOY_ACCESS_ISSUER" not in worker
    assert "SMARTPLOY_OIDC_ISSUER" not in worker
    assert "SMARTPLOY_OIDC_CLIENT_ID" not in worker
    assert "SMARTPLOY_ACCESS_AUDIENCE" not in worker
    assert "SMARTPLOY_ACCESS_ALLOWED_EMAIL" not in worker

    assert "SMARTPLOY_DATABASE_URL" not in web
    assert "SMARTPLOY_OIDC_" not in web
    assert "OBUMAI_" not in web
    assert "JOBMARKET_" not in web
    assert "KUNTAREKRY_" not in web

    assert "OBUMAI_" not in postgres
    assert "SMARTPLOY_ACCESS_" not in postgres
    assert "JOBMARKET_" not in postgres
    assert "KUNTAREKRY_" not in postgres


def test_environment_boundary_smoke_has_valid_shell_syntax():
    script = ROOT / "deploy/personal/scripts/smoke-env-boundaries.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_environment_boundary_smoke_never_prints_values():
    smoke = (ROOT / "deploy/personal/scripts/smoke-env-boundaries.sh").read_text(
        encoding="utf-8"
    )

    assert "print(" in smoke
    assert "sorted(os.environ)" in smoke
    assert 'sed "s/=.*//"' in smoke
    assert "os.environ.items()" not in smoke
    assert "printenv" not in smoke
    assert "SmartPloy environment-boundary smoke: PASS" in smoke


def test_preflight_keeps_secret_payloads_off_process_argv():
    preflight = (ROOT / "deploy/personal/scripts/preflight.sh").read_text(encoding="utf-8")

    assert 'python - "${ATS_JSON}"' not in preflight
    assert "printf '%s' \"${ATS_JSON}\" | python3 -c" in preflight
    assert "docker compose" in preflight
    assert "config --format json" in preflight
    assert "SMARTPLOY_ACCESS_AUDIENCE must be a non-placeholder audience identifier" in preflight
    assert "deploy/personal/env must not be group/world readable" in preflight


def test_live_acceptance_script_is_read_only_and_secret_safe():
    script = ROOT / "deploy/personal/scripts/live-acceptance.sh"
    text = script.read_text(encoding="utf-8")

    subprocess.run(["bash", "-n", str(script)], check=True)

    assert 'PRODUCTION_ORIGIN="$(sed -n' in text
    assert 'PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"' in text
    assert 'validate-runtime-policy.sh' in text
    assert text.index('validate-runtime-policy.sh" "${POLICY_FILE}" >/dev/null') < text.index('PRODUCTION_ORIGIN="$(sed -n')
    assert "--write-out" in text
    assert "%header{cf-ray}" in text
    assert "%header{server}" in text
    assert "%header{location}" in text
    assert "--location" not in text
    assert " --insecure" not in text
    assert " -k " not in text
    assert "Cf-Access-Jwt-Assertion" not in text
    assert "Authorization:" not in text
    assert "Cookie:" not in text
    assert "docker compose up" not in text
    assert "docker compose down" not in text
    assert "git checkout" not in text
    assert "live_acceptance=pass" in text


def test_release_evidence_script_is_private_read_only_and_secret_safe():
    script = ROOT / "deploy/personal/scripts/release-evidence.sh"
    text = script.read_text(encoding="utf-8")

    subprocess.run(["bash", "-n", str(script)], check=True)

    assert "format=smartploy-release-evidence-v1" in text
    assert 'assert-running-images.sh" "${DEPLOYED_SHA}"' in text
    assert "running_release_images_verified=true" in text
    assert "deployed_sha_matches_code=true" in text
    assert "preflight_passed=true" in text
    assert "env_boundary_smoke_passed=true" in text
    assert 'chmod 600 "${EVIDENCE_TMP}"' in text
    assert 'chmod 600 "${FINAL}.sha256"' in text
    assert 'sha256sum -c' in text
    assert 'current code SHA does not match deployed-sha' in text
    assert 'deployment state directory must not be group/world accessible' in text

    assert "POSTGRES_PASSWORD" not in text
    assert "SMARTPLOY_ACCESS_ISSUER" not in text
    assert "SMARTPLOY_ACCESS_AUDIENCE" not in text
    assert "SMARTPLOY_ACCESS_ALLOWED_EMAIL" not in text
    assert "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY" not in text
    assert "KUNTAREKRY_FEED_URL" not in text
    assert "OBUMAI_HTTP_HEADERS_JSON" not in text
    assert "Cf-Access-Jwt-Assertion" not in text
    assert "Authorization:" not in text
    assert "Cookie:" not in text

    assert "docker compose up" not in text
    assert "docker compose down" not in text
    assert "pg_dump" not in text
    assert "pg_restore" not in text


def test_release_evidence_ci_parses_artifact_path_without_fragile_shell_quoting():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "sed -n 's/^Evidence artifact: //p'" in workflow
    assert "printf '%s\\n'" in workflow
    assert "EVIDENCE_OUTPUT#*" not in workflow

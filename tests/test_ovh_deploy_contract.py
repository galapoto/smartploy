from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SCRIPT_DIR = ROOT / "deploy/personal/scripts"
EXPECTED_PRODUCTION_SCRIPTS = {
    "backup.sh",
    "deploy.sh",
    "assert-auto-draft-worker.sh",
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
    # Installing the *new* host must never silently redirect users away
    # from a still-working legacy site before login has been accepted.
    assert "smartploy.obumai.com {" not in caddy
    assert "redir " not in caddy
    optional = (ROOT / "deploy/personal/Caddyfile.legacy-redirect.example").read_text(
        encoding="utf-8"
    )
    assert "smartploy.obumai.com {" in optional
    assert "redir https://smartploy.komplyint.fi{uri} temporary" in optional
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
    assert "smartploy.komplyint.fi {" in host_caddy
    assert "smartploy.obumai.com {" not in host_caddy
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


def test_both_identity_deploy_and_restore_probes_enforce_selected_host(tmp_path):
    """Run the original in-script Python health gate, with synthetic data.

    No OVH access, real user data, or network used. The legacy Cloudflare
    and first-party Komplyint modes must never be interchanged.
    """
    import json
    import sys

    for name in ("deploy.sh", "restore.sh"):
        script = (PRODUCTION_SCRIPT_DIR / name).read_text(encoding="utf-8")
        marker = (
            'python3 - "${HEALTH_FILE}" "${IDENTITY_PROFILE}" '
            '"${PRODUCTION_ORIGIN}" "${DEPLOY_SHA:0:12}" <<\'PY\'\n'
            if name == "deploy.sh"
            else 'python3 - "${HEALTH_FILE}" "${IDENTITY_PROFILE}" "${PRODUCTION_ORIGIN}" <<\'PY\'\n'
        )
        assert marker in script
        source = script.split(marker, 1)[1].split("\nPY\n", 1)[0]
        assert 'PRODUCTION_ORIGIN="$(sed -n' in script
        assert 'PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"' in script
        assert '-H "Host: ${PRODUCTION_HOST}"' in script
        assert "-H 'Host: smartploy.obumai.com'" not in script

        for identity, origin in (
            ("cloudflare", "https://smartploy.obumai.com"),
            ("oidc", "https://smartploy.komplyint.fi"),
        ):
            state = {
                "ok": True, "service": "smartploy", "public_origin": origin,
                "release_revision": "1" * 12,
                "storage": {"ready": True},
                "access": {
                    "environment": "production",
                    "enabled": identity == "cloudflare",
                    "owner_restricted": identity == "cloudflare",
                },
                "external_actions_authorized": False,
            }
            input_path = tmp_path / f"{name}-{identity}.json"
            input_path.write_text(json.dumps(state), encoding="utf-8")

            def check(expected_origin, mode=identity):
                return subprocess.run(
                    ([sys.executable, "-c", source, str(input_path), mode, expected_origin]
                     + (["1" * 12] if name == "deploy.sh" else [])),
                    capture_output=True, text=True, check=False, timeout=4,
                )

            assert check(origin).returncode == 0
            wrong = ("https://smartploy.komplyint.fi" if identity == "cloudflare"
                     else "https://smartploy.obumai.com")
            assert check(wrong).returncode != 0
            assert check(origin, "oidc" if identity == "cloudflare" else "cloudflare").returncode != 0
            if name == "deploy.sh":
                input_path.write_text(
                    json.dumps({**state, "release_revision": "2" * 12}),
                    encoding="utf-8",
                )
                assert check(origin).returncode != 0  # Old image, healthy process



def test_release_image_health_and_evidence_proofs_select_same_identity_policy():
    for name in ("assert-healthy-stack.sh", "assert-running-images.sh"):
        script = (PRODUCTION_SCRIPT_DIR / name).read_text(encoding="utf-8")
        assert 'POLICY_FILE="$(bash "${SCRIPT_DIR}/select-runtime-policy.sh")"' in script
        assert 'validate-runtime-policy.sh' in script
        assert 'POLICY_FILE="${COMPOSE_DIR}/runtime.production.env"' not in script

    receipt = (PRODUCTION_SCRIPT_DIR / "release-evidence.sh").read_text(encoding="utf-8")
    assert 'PRODUCTION_ORIGIN="$(sed -n' in receipt
    assert '-H "Host: ${PRODUCTION_HOST}"' in receipt
    assert 'origin-health "${HEALTH_FILE}" "${IDENTITY_PROFILE}"' in receipt
    assert "-H 'Host: smartploy.obumai.com'" not in receipt

    diagnostic = (PRODUCTION_SCRIPT_DIR / "diagnose-origin-502.sh").read_text(encoding="utf-8")
    assert 'PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"' in diagnostic
    assert 'probe --connect-to "${PRODUCTION_HOST}:443:127.0.0.1:443"' in diagnostic
    assert "smartploy.obumai.com:443" not in diagnostic

    preflight = (PRODUCTION_SCRIPT_DIR / "preflight.sh").read_text(encoding="utf-8")
    assert 'getent ahosts "${POLICY_HOST}"' in preflight
    assert 'if [[ "${PROFILE}" != "oidc" ]] && (( HTTP_STATUS >= 500 ))' in preflight
    assert "check_oidc_metadata.py" in preflight
    assert " --insecure" not in preflight


def test_sp36_agent_zero_worker_flags_reach_only_worker_not_api_web_or_db():
    """A private host flag alone was previously dropped by Compose."""
    compose = (ROOT / "deploy/personal/docker-compose.yml").read_text(
        encoding="utf-8"
    )
    worker = _service_block(compose, "worker")
    values = {
        "SMARTPLOY_WORKER_AGENT_ZERO_ENABLED": "false",
        "SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS": "60",
        "SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT": "20",
    }
    for key, default in values.items():
        assert f"${{{key}:-{default}}}" in worker
        for service in ("api", "web", "postgres"):
            assert key not in _service_block(compose, service)
    sample = (ROOT / "deploy/personal/env.example").read_text(encoding="utf-8")
    assert "SMARTPLOY_WORKER_AGENT_ZERO_ENABLED=false" in sample
    assert "SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS=60" in sample
    assert "SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT=20" in sample

    smoke = (PRODUCTION_SCRIPT_DIR / "smoke-env-boundaries.sh").read_text(
        encoding="utf-8"
    )
    assert smoke.count('"SMARTPLOY_WORKER_AGENT_ZERO_ENABLED"') >= 2
    assert '"SMARTPLOY_WORKER_AGENT_ZERO_CADENCE_SECONDS"' in smoke
    assert '"SMARTPLOY_WORKER_AGENT_ZERO_BATCH_LIMIT"' in smoke
    assert '"SMARTPLOY_WORKER_AGENT_ZERO_"' in smoke
    assert '"SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED"' in smoke


def test_sp36_agent_zero_acceptance_uses_actual_worker_process_and_no_private_logs():
    checker = (PRODUCTION_SCRIPT_DIR / "assert-agent-zero-worker.sh").read_text(
        encoding="utf-8"
    )
    subprocess.run(["bash", "-n", str(PRODUCTION_SCRIPT_DIR /
                    "assert-agent-zero-worker.sh")], check=True)
    assert "config --format json" in checker
    assert "ps -q worker" in checker
    assert "docker inspect" in checker
    assert "--require-run --not-before" in checker
    assert "--wait-seconds 100" in checker
    assert "python -m smartploy.agent_zero_runtime_acceptance" in checker
    assert "AGENT_ZERO_OPERATOR_OPT_IN_REQUIRED" not in checker
    assert "POSTGRES_PASSWORD" not in checker
    assert "docker compose up" not in checker
    assert "docker compose down" not in checker
    assert "docker compose exec" not in checker
    # The container invocation does not print variables, DB rows, CV or env.
    assert "printenv" not in checker
    assert "env |" not in checker
    assert '"${REPORT}"' in checker


def test_sp36_guarded_release_blocks_bad_worker_before_deploy_sha_success():
    deploy = (PRODUCTION_SCRIPT_DIR / "deploy.sh").read_text(encoding="utf-8")
    evidence = (PRODUCTION_SCRIPT_DIR / "release-evidence.sh").read_text(
        encoding="utf-8"
    )
    assert deploy.index("python scripts/migrate.py") < deploy.index(
        'assert-agent-zero-worker.sh"'
    ) < deploy.index('"${STATE_DIR}/deployed-sha"')
    assert 'bash "${SCRIPT_DIR}/assert-agent-zero-worker.sh"' in evidence
    assert "${AGENT_ZERO_FIELDS}" in evidence
    assert "agent_zero_mode=" in (
        PRODUCTION_SCRIPT_DIR / "assert-agent-zero-worker.sh"
    ).read_text(encoding="utf-8")
    assert "agent_zero_candidate_reminder_verified=false" in (
        PRODUCTION_SCRIPT_DIR / "assert-agent-zero-worker.sh"
    ).read_text(encoding="utf-8")


def test_sp57_oidc_public_https_release_parity_is_a_blocking_release_gate():
    live = (PRODUCTION_SCRIPT_DIR / "live-acceptance.sh").read_text(encoding="utf-8")
    deploy = (PRODUCTION_SCRIPT_DIR / "deploy.sh").read_text(encoding="utf-8")
    receipt = (PRODUCTION_SCRIPT_DIR / "release-evidence.sh").read_text(encoding="utf-8")

    # Public OIDC gateway proof must not be derived from the same loopback
    # response. TLS is verified by curl, and its URL is the validated policy.
    assert '"${PRODUCTION_ORIGIN}/healthz" > "${PUBLIC_HEALTH_FILE}"' in live
    assert 'public-release-parity "${HEALTH_FILE}" "${PUBLIC_HEALTH_FILE}" "oidc"' in live
    assert "public_revision_matches_origin=true" in live
    assert "public_revision_matches_origin=skipped_legacy_access" in live
    assert '--max-filesize 16384' in live
    assert 'public_release_revision=${PUBLIC_REVISION}' in live
    assert live.index('public-release-parity') < live.index('live_acceptance=pass')

    # Preserve original backup/image/companion/Agent Zero and OIDC checks.
    assert 'assert-running-images.sh" "${DEPLOY_SHA}"' in deploy
    assert 'assert-companion-release.sh' in deploy
    assert 'assert-agent-zero-worker.sh' in deploy
    assert 'bash "${SCRIPT_DIR}/live-acceptance.sh"' in deploy
    assert 'public HTTPS revision differs from approved deployed SHA' in receipt
    assert 'LIVE_PUBLIC_RELEASE_REVISION' in receipt
    assert 'LIVE_PUBLIC_REVISION_MATCH' in receipt
    assert 'live_public_release_revision=${LIVE_PUBLIC_RELEASE_REVISION}' in receipt
    assert 'live_public_revision_matches_origin=${LIVE_PUBLIC_REVISION_MATCH}' in receipt
    assert '"${DEPLOYED_SHA:0:12}"' in receipt


def test_sp57_chromium_runner_is_pinned_to_supported_ubuntu_image():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "  browser:\n" in workflow
    section = workflow.split("  browser:\n", 1)[1].split("\n  deploy-stack:", 1)[0]
    assert "runs-on: ubuntu-24.04" in section
    assert "runs-on: ubuntu-latest" not in section
    assert "npx playwright install chromium" in section
    assert "await chromium.launch({ headless: true })" in section


def test_sp59_explicit_private_draft_optin_is_not_inferred_from_host_defaults():
    compose = (ROOT / "deploy/personal/docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / "deploy/personal/env.example").read_text(encoding="utf-8")
    worker = _service_block(compose, "worker")
    assert "${SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED:-false}" in worker
    assert "SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED=true" in env_example
    for service in ("postgres", "api", "web"):
        assert "SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED:" not in _service_block(compose, service)


def test_sp59_real_worker_schedule_and_private_release_proof_are_blocking():
    gate = (PRODUCTION_SCRIPT_DIR / "assert-auto-draft-worker.sh").read_text(
        encoding="utf-8"
    )
    deploy = (PRODUCTION_SCRIPT_DIR / "deploy.sh").read_text(encoding="utf-8")
    evidence = (PRODUCTION_SCRIPT_DIR / "release-evidence.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m smartploy.auto_draft_runtime_acceptance" in gate
    assert "application:auto-draft-shortlist" in (
        ROOT / "smartploy/auto_draft_runtime_acceptance.py"
    ).read_text(encoding="utf-8")
    assert "auto_draft_mode=" in gate
    assert "auto_draft_candidate_drafts_verified=false" in gate
    assert "auto_draft_employer_contacts_authorized=false" in gate
    assert "POSTGRES_PASSWORD" not in gate
    assert "printenv" not in gate
    assert "docker compose up" not in gate
    assert 'assert-auto-draft-worker.sh"' in deploy
    assert deploy.index('assert-auto-draft-worker.sh"') < deploy.index(
        '"${STATE_DIR}/deployed-sha"'
    )
    assert 'bash "${SCRIPT_DIR}/assert-auto-draft-worker.sh"' in evidence
    assert "${AUTO_DRAFT_FIELDS}" in evidence
    assert "auto_draft_mode=healthy_scheduled_run" in workflow
    assert "AUTO_DRAFT_FRESH_RUN_MISSING" in workflow
    assert workflow.index("assert-auto-draft-worker.sh") < workflow.index(
        "AUTO_DRAFT_FRESH_RUN_MISSING"
    )

"""SP15i: exact-source production identity / partner release contract.

No internet, employer credentials or deployment performed by these checks.
Exercise the ORIGINAL bash policy verifier, opt-in selector and Compose
API-only environment surface without a second authentication stack.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROD = ROOT / "deploy/personal"
SCRIPTS = PROD / "scripts"


def _run(script: str, *args: str, profile: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("SMARTPLOY_PRODUCTION_IDENTITY_MODE", None)
    if profile is not None:
        env["SMARTPLOY_PRODUCTION_IDENTITY_MODE"] = profile
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args], text=True,
        capture_output=True, env=env, check=False, timeout=8,
    )


def test_original_cloudflare_mode_is_preserved_as_default():
    selected = _run("select-runtime-policy.sh")
    assert selected.returncode == 0, selected.stderr
    assert selected.stdout.strip() == str(PROD / "runtime.production.env")
    validated = _run("validate-runtime-policy.sh", selected.stdout.strip())
    assert validated.returncode == 0, validated.stderr
    assert "(cloudflare)" in validated.stdout


def test_firstparty_oidc_mode_is_opt_in_and_exactly_validated():
    selected = _run("select-runtime-policy.sh", profile="oidc")
    assert selected.returncode == 0, selected.stderr
    assert selected.stdout.strip() == str(PROD / "runtime.oidc.production.env")
    validated = _run("validate-runtime-policy.sh", selected.stdout.strip())
    assert validated.returncode == 0, validated.stderr
    assert "(oidc)" in validated.stdout
    source = (PROD / "runtime.oidc.production.env").read_text(encoding="utf-8")
    assert "SMARTPLOY_AUTH_MODE=oidc" in source
    assert "SMARTPLOY_ACCESS_ENABLED=false" in source
    assert "SMARTPLOY_PUBLIC_ORIGIN=https://smartploy.komplyint.fi" in source
    assert "SMARTPLOY_ALLOWED_HOSTS=smartploy.komplyint.fi" in source
    assert "POSTGRES_PASSWORD" not in source
    assert "SMARTPLOY_OIDC_CLIENT_ID" not in source


def test_identity_selector_fails_closed_for_unapproved_modes():
    for value in ("disabled", "hybrid", "oidc:skip", "../oidc", "OIDC"):
        result = _run("select-runtime-policy.sh", profile=value)
        assert result.returncode != 0
        assert not result.stdout.strip()


def test_policy_verifier_rejects_mutated_oidc_profile(tmp_path):
    original = (PROD / "runtime.oidc.production.env").read_text(encoding="utf-8")
    bad = tmp_path / "runtime.oidc.production.env"
    for modified in (
        original.replace("SMARTPLOY_ACCESS_ENABLED=false", "SMARTPLOY_ACCESS_ENABLED=true"),
        original.replace("SMARTPLOY_AUTH_MODE=oidc", "SMARTPLOY_AUTH_MODE=disabled"),
        original.replace("smartploy.komplyint.fi", "smartploy.obumai.com"),
        original + "\nSMARTPLOY_DEBUG=true\n",
    ):
        bad.write_text(modified, encoding="utf-8")
        result = _run("validate-runtime-policy.sh", str(bad))
        assert result.returncode != 0


def test_partner_credentials_are_in_api_only_and_strictly_preflight_checked():
    compose = (PROD / "docker-compose.yml").read_text(encoding="utf-8")
    api = compose.split("\n  api:\n", 1)[1].split("\n  worker:\n", 1)[0]
    worker = compose.split("\n  worker:\n", 1)[1].split("\n  web:\n", 1)[0]
    web = compose.split("\n  web:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    postgres = compose.split("\n  postgres:\n", 1)[1].split("\n  api:\n", 1)[0]
    for key in (
        "SMARTPLOY_LEVER_PARTNER_JOBS_JSON",
        "SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY",
        "SMARTPLOY_LEVER_PARTNER_KEY_SECONDARY",
        "SMARTPLOY_LEVER_PARTNER_KEY_TERTIARY",
    ):
        assert key in api
        assert key not in worker
        assert key not in postgres
        assert key not in web
    preflight = (SCRIPTS / "preflight.sh").read_text(encoding="utf-8")
    assert "Partner API credential is absent or invalid" in preflight
    assert "Unused partner API credential must not be present" in preflight
    assert "Partner API configuration lacks reviewed form, consent" in preflight
    assert "OIDC-only profile must NOT enable Cloudflare assertion authentication" in preflight
    assert "check_oidc_metadata.py" in preflight
    assert "POLICY_HOST" in preflight
    assert 'getent ahosts "${POLICY_HOST}"' in preflight
    assert '"${POLICY_ORIGIN}/"' in preflight
    assert "getent ahosts smartploy.obumai.com" not in preflight
    assert "the actual public root (200)" in preflight


def test_oidc_rollout_requires_explicit_approved_sha_and_verified_public_login():
    deploy = (SCRIPTS / "deploy.sh").read_text(encoding="utf-8")
    live = (SCRIPTS / "live-acceptance.sh").read_text(encoding="utf-8")
    restore = (SCRIPTS / "restore.sh").read_text(encoding="utf-8")
    evidence = (SCRIPTS / "release-evidence.sh").read_text(encoding="utf-8")
    smoke = (SCRIPTS / "smoke-env-boundaries.sh").read_text(encoding="utf-8")
    assert 'SMARTPLOY_RELEASE_APPROVED_SHA' in deploy
    assert 'SMARTPLOY_PRODUCTION_IDENTITY_MODE' in deploy
    assert 'preflight.sh" --online' in deploy
    assert "deployed-auth-profile" in deploy
    assert (
        deploy.index('bash "${SCRIPT_DIR}/assert-running-images.sh" "${DEPLOY_SHA}"')
        < deploy.index('bash "${SCRIPT_DIR}/live-acceptance.sh"')
        < deploy.rindex('> "${STATE_DIR}/deployed-sha"')
    )
    assert "deployed-auth-profile" in restore
    assert "deployed-auth-profile" in evidence
    assert "oidc-root" in live and "oidc-api" in live and "oidc-login" in live
    assert "SMARTPLOY_LEVER_PARTNER_" in smoke
    assert "No caller may silently switch" not in live



def _compose_preflight_script() -> str:
    """Execute the EXACT production JSON environment-boundary validator."""
    raw = (SCRIPTS / "preflight.sh").read_text(encoding="utf-8")
    start = raw.index("python3 -", raw.index('config --format json'))
    begin = raw.index("<<'PY'\n", start) + len("<<'PY'\n")
    end = raw.index("\nPY\n", begin)
    return raw[begin:end]


def _synthetic_compose(*, profile: str, partner: bool = False) -> dict:
    auth = {
        "SMARTPLOY_DATABASE_URL": "postgresql://synthetic@postgres/smartploy",
        "SMARTPLOY_AUTH_MODE": profile,
        "SMARTPLOY_ACCESS_ENABLED": "false" if profile == "oidc" else "true",
        "SMARTPLOY_ACCESS_ISSUER": "https://team.cloudflareaccess.com",
        "SMARTPLOY_ACCESS_AUDIENCE": "synthetic-test-audience",
        "SMARTPLOY_ACCESS_ALLOWED_EMAIL": "synthetic@example.invalid",
        "SMARTPLOY_OIDC_ISSUER": "https://auth.komplyint.fi",
        "SMARTPLOY_OIDC_CLIENT_ID": "synthetic-public-client",
        "SMARTPLOY_OIDC_REDIRECT_URI": "https://smartploy.komplyint.fi/auth/callback",
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI": "https://smartploy.komplyint.fi/auth/logged-out",
        "SMARTPLOY_LEVER_PARTNER_JOBS_JSON": "",
        "SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY": "",
        "SMARTPLOY_LEVER_PARTNER_KEY_SECONDARY": "",
        "SMARTPLOY_LEVER_PARTNER_KEY_TERTIARY": "",
    }
    if partner:
        import json
        auth["SMARTPLOY_LEVER_PARTNER_JOBS_JSON"] = json.dumps({
            "syntheticorg/posting1": {
                "region": "global",
                "form_review_sha256": "a" * 64,
                "api_key_env": "SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY",
                "standard_form_only_reviewed": True,
                "consent_policy_reviewed": True,
            }
        })
        auth["SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY"] = "synthetic-employer-issued-test-key-123"
    return {"services": {
        "postgres": {"environment": {}, "ports": []},
        "api": {"environment": auth, "ports": []},
        "worker": {"environment": {
            "SMARTPLOY_DATABASE_URL": "postgresql://synthetic@postgres/smartploy",
            "JOBMARKET_FINLAND_API_ENABLED": "false",
            "KUNTAREKRY_ALLOWED_HOSTS": "kuntarekry.fi",
            "SMARTPLOY_WORKER_LOOP_SECONDS": "15",
        }, "ports": []},
        "web": {"environment": {}, "ports": [{
            "host_ip": "127.0.0.1", "published": 8091, "target": 8080
        }]},
    }}


def _run_compose_preflight(tmp_path, fixture: dict, profile: str):
    import json
    import sys
    path = tmp_path / "synthetic-compose.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", _compose_preflight_script(),
         str(path), "8091", profile], check=False,
        capture_output=True, text=True, timeout=8,
    )


def test_real_preflight_python_accepts_oidc_only_and_legacy_isolated_compose(tmp_path):
    for profile in ("cloudflare", "oidc"):
        result = _run_compose_preflight(
            tmp_path, _synthetic_compose(profile=profile), profile
        )
        assert result.returncode == 0, result.stderr


def test_real_preflight_python_accepts_explicit_partner_without_leaking_secret(tmp_path):
    fixture = _synthetic_compose(profile="oidc", partner=True)
    result = _run_compose_preflight(tmp_path, fixture, "oidc")
    assert result.returncode == 0, result.stderr
    assert "synthetic-employer-issued" not in result.stdout + result.stderr


def test_real_preflight_python_blocks_invalid_partner_or_credential_scope(tmp_path):
    import json
    from copy import deepcopy
    baseline = _synthetic_compose(profile="oidc", partner=True)
    for mutate in (
        lambda f: f["services"]["api"]["environment"].update(
            SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY=""
        ),
        lambda f: f["services"]["worker"]["environment"].update(
            SMARTPLOY_LEVER_PARTNER_KEY_PRIMARY="synthetic-employer-issued-test-key-123"
        ),
        lambda f: f["services"]["web"]["environment"].update(
            SMARTPLOY_LEVER_PARTNER_JOBS_JSON="synthetic-fixture"
        ),
        lambda f: f["services"]["api"]["environment"].update(
            SMARTPLOY_AUTH_MODE="disabled"
        ),
        lambda f: f["services"]["api"]["environment"].update(
            SMARTPLOY_ACCESS_ENABLED="true"
        ),
        lambda f: f["services"]["api"]["environment"].update(
            SMARTPLOY_LEVER_PARTNER_JOBS_JSON=json.dumps({
                "syntheticorg/posting1": {
                    **json.loads(f["services"]["api"]["environment"][
                        "SMARTPLOY_LEVER_PARTNER_JOBS_JSON"
                    ])["syntheticorg/posting1"],
                    "consent_policy_reviewed": False,
                }
            })
        ),
        lambda f: f["services"]["api"]["environment"].update(
            SMARTPLOY_LEVER_PARTNER_JOBS_JSON=""
        ),
    ):
        candidate = deepcopy(baseline)
        mutate(candidate)
        result = _run_compose_preflight(tmp_path, candidate, "oidc")
        assert result.returncode != 0
        assert "synthetic-employer-issued" not in result.stdout + result.stderr


def test_zitadel_discovery_metadata_requires_real_issuer_and_public_pkce(tmp_path):
    import json
    import sys
    from copy import deepcopy

    checker = ROOT / "scripts/check_oidc_metadata.py"
    sample = {
        "issuer": "https://auth.komplyint.fi",
        "authorization_endpoint": "https://auth.komplyint.fi/oauth/v2/authorize",
        "token_endpoint": "https://auth.komplyint.fi/oauth/v2/token",
        "jwks_uri": "https://auth.komplyint.fi/oauth/v2/keys",
        "grant_types_supported": ["authorization_code"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }

    def verify(payload):
        return subprocess.run(
            [sys.executable, str(checker), "https://auth.komplyint.fi"],
            input=json.dumps(payload), text=True, capture_output=True,
            check=False, timeout=4,
        )

    assert verify(sample).returncode == 0
    for field, value in (
        ("issuer", "https://auth.obumai.com"),
        ("authorization_endpoint", "https://evil.example/oauth"),
        ("token_endpoint", "http://auth.komplyint.fi/oauth/v2/token"),
        ("jwks_uri", "https://auth.komplyint.fi.evil.example/keys"),
        ("code_challenge_methods_supported", ["plain"]),
        ("grant_types_supported", ["client_credentials"]),
        ("response_types_supported", ["id_token"]),
        ("token_endpoint_auth_methods_supported", ["client_secret_basic"]),
    ):
        changed = deepcopy(sample)
        changed[field] = value
        result = verify(changed)
        assert result.returncode != 0
        assert "OIDC_METADATA_INVALID" in result.stderr
        assert "evil.example" not in result.stderr

    assert verify({"issuer": sample["issuer"]}).returncode != 0

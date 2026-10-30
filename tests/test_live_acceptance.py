import json
import subprocess
import sys

import pytest

from smartploy.live_acceptance import (
    LiveAcceptanceError,
    PublicProbe,
    is_cloudflare_access_redirect,
    parse_probe_lines,
    validate_origin_health,
    validate_public_probe,
    validate_oidc_public_probe,
    validate_public_release_parity,
    validate_web_release_parity,
)


def healthy_origin():
    return {
        "ok": True,
        "service": "smartploy",
        "public_origin": "https://smartploy.obumai.com",
        "storage": {"ready": True},
        "access": {
            "enabled": True,
            "environment": "production",
            "owner_restricted": True,
        },
        "external_actions_authorized": False,
    }


def test_origin_health_accepts_exact_production_boundary():
    validate_origin_health(healthy_origin())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("ok",), False),
        (("service",), "other"),
        (("public_origin",), "https://example.com"),
        (("storage", "ready"), False),
        (("access", "enabled"), False),
        (("access", "environment"), "development"),
        (("access", "owner_restricted"), False),
        (("external_actions_authorized",), True),
    ],
)
def test_origin_health_rejects_weakened_boundary(path, value):
    payload = healthy_origin()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(LiveAcceptanceError):
        validate_origin_health(payload)


@pytest.mark.parametrize("status", [401, 403])
def test_public_denial_statuses_are_accepted_with_cloudflare_edge(status):
    assert (
        validate_public_probe(
            PublicProbe(status_code=status, cf_ray="abc-HEL", server="cloudflare")
        )
        == "protected"
    )


@pytest.mark.parametrize("status", [302, 303, 307, 308])
def test_cloudflare_access_redirect_is_accepted(status):
    assert (
        validate_public_probe(
            PublicProbe(
                status_code=status,
                cf_ray="abc-HEL",
                server="cloudflare",
                location=(
                    "https://team.cloudflareaccess.com/cdn-cgi/access/login/"
                    "smartploy.obumai.com?state=opaque"
                ),
            )
        )
        == "protected"
    )


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/login",
        "http://team.cloudflareaccess.com/cdn-cgi/access/login/x",
        "https://cloudflareaccess.com/cdn-cgi/access/login/x",
        "https://team.cloudflareaccess.com/not-access/login",
        "/cdn-cgi/access/login/x",
    ],
)
def test_non_access_redirect_is_rejected(location):
    assert is_cloudflare_access_redirect(location) is False
    with pytest.raises(LiveAcceptanceError, match="redirect"):
        validate_public_probe(
            PublicProbe(
                status_code=302,
                cf_ray="abc-HEL",
                server="cloudflare",
                location=location,
            )
        )


@pytest.mark.parametrize("status", [200, 404, 429, 500, 502, 503])
def test_public_or_unexpected_status_is_rejected(status):
    with pytest.raises(LiveAcceptanceError):
        validate_public_probe(
            PublicProbe(status_code=status, cf_ray="abc-HEL", server="cloudflare")
        )


def test_cloudflare_edge_evidence_is_required():
    with pytest.raises(LiveAcceptanceError, match="Cloudflare"):
        validate_public_probe(PublicProbe(status_code=403))


def test_probe_parser_uses_selected_headers_only():
    probe = parse_probe_lines(
        "302\nabc-HEL\ncloudflare\n"
        "https://team.cloudflareaccess.com/cdn-cgi/access/login/x?state=opaque\n"
    )
    assert probe.status_code == 302
    assert probe.cf_ray == "abc-HEL"
    assert probe.server == "cloudflare"



def oidc_healthy_origin():
    payload = healthy_origin()
    payload["public_origin"] = "https://smartploy.komplyint.fi"
    payload["access"]["enabled"] = False
    payload["access"]["owner_restricted"] = False
    return payload


def test_production_oidc_origin_requires_no_access_assertion_and_expected_profile():
    payload = oidc_healthy_origin()
    assert "authentication" not in payload
    validate_origin_health(payload, "oidc")
    with pytest.raises(LiveAcceptanceError):
        validate_origin_health(payload, "cloudflare")
    with pytest.raises(LiveAcceptanceError):
        validate_origin_health(payload, "disabled")
    payload["access"]["enabled"] = True
    with pytest.raises(LiveAcceptanceError):
        validate_origin_health(payload, "oidc")


def test_new_oidc_origin_refuses_legacy_host_and_cross_origin_health():
    payload = oidc_healthy_origin()
    validate_origin_health(payload, "oidc")
    payload["public_origin"] = "https://smartploy.obumai.com"
    with pytest.raises(LiveAcceptanceError, match="public URL"):
        validate_origin_health(payload, "oidc")
    legacy = healthy_origin()
    validate_origin_health(legacy, "cloudflare")
    legacy["public_origin"] = "https://smartploy.komplyint.fi"
    with pytest.raises(LiveAcceptanceError, match="public URL"):
        validate_origin_health(legacy, "cloudflare")


def test_oidc_public_static_shell_private_api_and_trusted_login_redirect():
    edge = {"server": "cloudflare", "cf_ray": "test-HEL"}
    assert validate_oidc_public_probe(
        PublicProbe(status_code=200, **edge), "root", "https://auth.obumai.com"
    ) == "public_login_shell"
    assert validate_oidc_public_probe(
        PublicProbe(status_code=401, **edge), "api", "https://auth.obumai.com"
    ) == "protected_by_app_session"
    assert validate_oidc_public_probe(
        PublicProbe(
            status_code=302, location="https://auth.obumai.com/oauth/v2/authorize?state=opaque",
            **edge
        ), "login", "https://auth.obumai.com"
    ) == "redirect_to_trusted_oidc"


@pytest.mark.parametrize(("surface", "status", "location"), [
    ("root", 302, "https://team.cloudflareaccess.com/cdn-cgi/access/login"),
    ("root", 403, ""),
    ("api", 200, ""),
    ("api", 500, ""),
    ("api", 302, "https://team.cloudflareaccess.com/cdn-cgi/access/login"),
    ("login", 200, ""),
    ("login", 302, "https://evil.invalid/login"),
    ("login", 302, "http://auth.obumai.com/oauth/v2/authorize"),
    ("login", 302, "https://auth.obumai.com.evil.invalid/oauth"),
    ("login", 302, "https://attacker@auth.obumai.com/oauth"),
    ("login", 302, "/cdn-cgi/access/login"),
])
def test_oidc_public_acceptance_rejects_bad_signin_or_unprotected_api(surface, status, location):
    with pytest.raises(LiveAcceptanceError):
        validate_oidc_public_probe(
            PublicProbe(status_code=status, location=location, server="cloudflare"),
            surface, "https://auth.obumai.com"
        )


def test_oidc_public_acceptance_supports_direct_ovh_https_ingress():
    """Cloudflare headers are not a ZITADEL or TLS security requirement.

    The production caller verifies the exact HTTPS host/certificate first;
    the app itself must still protect account data and route to the issuer.
    """
    issuer = "https://auth.komplyint.fi"
    assert validate_oidc_public_probe(
        PublicProbe(status_code=200), "root", issuer
    ) == "public_login_shell"
    assert validate_oidc_public_probe(
        PublicProbe(status_code=401), "api", issuer
    ) == "protected_by_app_session"
    assert validate_oidc_public_probe(
        PublicProbe(
            status_code=302,
            location="https://auth.komplyint.fi/oauth/v2/authorize?state=opaque",
        ), "login", issuer
    ) == "redirect_to_trusted_oidc"


@pytest.mark.parametrize(
    ("surface", "status", "location"),
    [
        ("root", 302, "https://team.cloudflareaccess.com/cdn-cgi/access/login"),
        ("root", 502, ""),
        ("api", 200, ""),
        ("api", 302, "https://team.cloudflareaccess.com/cdn-cgi/access/login"),
        ("login", 302, "https://team.cloudflareaccess.com/cdn-cgi/access/login"),
        ("login", 302, "https://auth.komplyint.fi.evil.invalid/oauth"),
    ],
)
def test_oidc_direct_https_does_not_weaken_app_or_issuer_gates(
    surface, status, location
):
    with pytest.raises(LiveAcceptanceError):
        validate_oidc_public_probe(
            PublicProbe(status_code=status, location=location),
            surface, "https://auth.komplyint.fi"
        )

# SP57: independent public hostname may still point at stale API/Ingress.
# All fixtures are synthetic: no DNS, accounts or internet calls.
def _release_pair():
    local = oidc_healthy_origin()
    public = oidc_healthy_origin()
    local["release_revision"] = "ab12cd34ef56"
    public["release_revision"] = "ab12cd34ef56"
    return local, public


def test_public_release_parity_accepts_only_identical_valid_oidc_revisions():
    local, public = _release_pair()
    assert validate_public_release_parity(local, public, "oidc") == "ab12cd34ef56"


@pytest.mark.parametrize("bad_version", [
    "", "dev", None, "ABCDEF123456", "ab12cd34ef5", "a" * 40,
    "other_commit", "ab12cd34ef57",
])
def test_public_release_parity_refuses_unattested_or_stale_gateway(bad_version):
    local, public = _release_pair()
    public["release_revision"] = bad_version
    with pytest.raises(LiveAcceptanceError):
        validate_public_release_parity(local, public, "oidc")


def test_public_release_parity_refuses_unattested_local_api():
    local, public = _release_pair()
    del local["release_revision"]
    with pytest.raises(LiveAcceptanceError):
        validate_public_release_parity(local, public, "oidc")


@pytest.mark.parametrize(("key", "value"), [
    ("public_origin", "https://smartploy.obumai.com"),
    ("service", "impostor"),
    ("ok", False),
    ("external_actions_authorized", True),
    ("storage", {"ready": False}),
    ("access", {"environment": "development", "enabled": False}),
])
def test_public_release_parity_refuses_wrong_service_identity_and_policy(key, value):
    local, public = _release_pair()
    public[key] = value
    with pytest.raises(LiveAcceptanceError):
        validate_public_release_parity(local, public, "oidc")


@pytest.mark.parametrize("mode", ["cloudflare", "disabled", ""])
def test_public_release_parity_never_loosens_legacy_access(mode):
    local, public = _release_pair()
    with pytest.raises(LiveAcceptanceError):
        validate_public_release_parity(local, public, mode)


def test_public_release_parity_cli_emits_only_verified_digest_and_fails_closed(tmp_path):
    local, public = _release_pair()
    origin_file = tmp_path / "origin.json"
    public_file = tmp_path / "public.json"
    origin_file.write_text(json.dumps(local), encoding="utf-8")
    public_file.write_text(json.dumps(public), encoding="utf-8")

    def probe():
        return subprocess.run(
            [sys.executable, "-m", "smartploy.live_acceptance",
             "public-release-parity", str(origin_file), str(public_file), "oidc"],
            capture_output=True, text=True, check=False, timeout=5,
        )

    ok = probe()
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == "ab12cd34ef56"
    assert not ok.stderr

    public_file.write_text('{"secret": "PRIVATE_CV_PAYLOAD"}', encoding="utf-8")
    failed = probe()
    assert failed.returncode != 0
    assert "PRIVATE_CV_PAYLOAD" not in failed.stdout + failed.stderr
    assert "ab12cd34ef56" not in failed.stdout


# SP74: API + Caddy web + public HTTPS must share the exact release identity.
# All fixtures are synthetic; no actual user, production URL fetch or credential.
def _web_manifest(version="ab12cd34ef56"):
    return {
        "schema": "smartploy-web-release-v1",
        "release_revision": version,
    }


def test_web_release_parity_accepts_exact_api_and_static_build():
    local, _ = _release_pair()
    assert validate_web_release_parity(
        local, _web_manifest(), "ab12cd34ef56", "oidc",
        _web_manifest()
    ) == "ab12cd34ef56"
    legacy = healthy_origin()
    legacy["release_revision"] = "ab12cd34ef56"
    assert validate_web_release_parity(
        legacy, _web_manifest(), "ab12cd34ef56", "cloudflare"
    ) == "ab12cd34ef56"


@pytest.mark.parametrize("bad", [
    "", "dev", "main", None, "AB12CD34EF56", "ab12cd34ef5",
    "ab12cd34ef57", "0" * 40, "PRIVATE-CV",
])
def test_web_release_parity_rejects_unattested_and_stale_web_version(bad):
    local, _ = _release_pair()
    with pytest.raises(LiveAcceptanceError):
        validate_web_release_parity(
            local, _web_manifest(bad), "ab12cd34ef56", "oidc"
        )


@pytest.mark.parametrize("bad", [
    {"release_revision": "ab12cd34ef56"},
    {"schema": "other", "release_revision": "ab12cd34ef56"},
    {"schema": "smartploy-web-release-v1",
     "release_revision": "ab12cd34ef56", "private_note": "NEVER"},
    {"schema": "smartploy-web-release-v1"},
    {},
])
def test_web_release_parity_rejects_broken_or_secret_bearing_manifest(bad):
    local, _ = _release_pair()
    with pytest.raises(LiveAcceptanceError):
        validate_web_release_parity(local, bad, "ab12cd34ef56", "oidc")


def test_web_release_parity_rejects_stale_api_even_if_web_looks_current():
    local, _ = _release_pair()
    local["release_revision"] = "ab12cd34ef57"
    with pytest.raises(LiveAcceptanceError, match="API release fingerprint"):
        validate_web_release_parity(
            local, _web_manifest(), "ab12cd34ef56", "oidc"
        )


def test_web_release_parity_rejects_stale_public_web_edge_and_legacy_public_mode():
    local, _ = _release_pair()
    with pytest.raises(LiveAcceptanceError, match="static artifact"):
        validate_web_release_parity(
            local, _web_manifest(), "ab12cd34ef56", "oidc",
            _web_manifest("ab12cd34ef57")
        )
    legacy = healthy_origin()
    legacy["release_revision"] = "ab12cd34ef56"
    with pytest.raises(LiveAcceptanceError, match="first-party OIDC"):
        validate_web_release_parity(
            legacy, _web_manifest(), "ab12cd34ef56", "cloudflare",
            _web_manifest()
        )


@pytest.mark.parametrize("bad", ["", "main", "AB12CD34EF56", "0" * 40])
def test_web_release_parity_requires_exact_reviewed_source_prefix(bad):
    local, _ = _release_pair()
    with pytest.raises(LiveAcceptanceError, match="approved"):
        validate_web_release_parity(local, _web_manifest(), bad, "oidc")


def test_web_release_cli_positive_and_generic_negative_without_private_payload(tmp_path):
    local, _ = _release_pair()
    health = tmp_path / "health.json"
    origin_web = tmp_path / "web.json"
    public_web = tmp_path / "public.json"
    health.write_text(json.dumps(local), encoding="utf-8")
    origin_web.write_text(json.dumps(_web_manifest()), encoding="utf-8")
    public_web.write_text(json.dumps(_web_manifest()), encoding="utf-8")

    def probe():
        return subprocess.run(
            [sys.executable, "-m", "smartploy.live_acceptance",
             "web-release-parity", str(health), str(origin_web),
             "ab12cd34ef56", "oidc", str(public_web)],
            check=False, capture_output=True, text=True, timeout=5,
        )

    assert probe().stdout.strip() == "ab12cd34ef56"
    public_web.write_text(
        '{"private_cv":"SENSITIVE_CV_FIXTURE","release_revision":"old"}',
        encoding="utf-8",
    )
    denied = probe()
    assert denied.returncode != 0
    assert "web release parity: verification failed" in denied.stderr
    assert "SENSITIVE_CV_FIXTURE" not in denied.stdout + denied.stderr
    assert "ab12cd34ef56" not in denied.stdout

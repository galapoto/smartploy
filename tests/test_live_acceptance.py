import pytest

from smartploy.live_acceptance import (
    LiveAcceptanceError,
    PublicProbe,
    is_cloudflare_access_redirect,
    parse_probe_lines,
    validate_origin_health,
    validate_public_probe,
    validate_oidc_public_probe,
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

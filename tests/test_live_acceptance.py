import pytest

from smartploy.live_acceptance import (
    LiveAcceptanceError,
    PublicProbe,
    is_cloudflare_access_redirect,
    parse_probe_lines,
    validate_origin_health,
    validate_public_probe,
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

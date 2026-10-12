"""Same-origin write barrier for OIDC cookie sessions.

The identities, job data and origins below are synthetic; no real account,
browser, Cloudflare policy or employer system is touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


ORIGIN = "https://smartploy.obumai.com"
IDENTITY_ISSUER = "https://auth.obumai.com"
ACCESS_ISSUER = "https://example.cloudflareaccess.com"


def configure(monkeypatch, *, mode="oidc"):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", mode)
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", IDENTITY_ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "smartploy-synthetic")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
        ORIGIN + "/auth/logged-out",
    )
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true" if mode == "hybrid" else "false")
    if mode == "hybrid":
        monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", ACCESS_ISSUER)
        monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "fixture")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "shared@example.invalid")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)


def signed_in_client(monkeypatch, *, mode="oidc", access_verifier=None):
    configure(monkeypatch, mode=mode)
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    principal = AuthenticatedPrincipal(
        issuer=IDENTITY_ISSUER, subject="synthetic-user-a",
        email="shared@example.invalid", auth_source="oidc",
    )
    binding = identities.resolve_or_create(principal)
    session = sessions.create(
        user_id=binding.user_id, principal=principal,
        provider_session_id="synthetic", ttl_seconds=3600,
    )
    api = TestClient(
        create_app(
            SmartployService(),
            oidc_client=object(),
            identity_repository=identities,
            session_repository=sessions,
            access_verifier=access_verifier,
        ),
        base_url=ORIGIN,
    )
    api.cookies.set(SESSION_COOKIE_NAME, session.token)
    return api


FACT = {"fact_type": "skill", "value": "Synthetic SQL", "approved": False}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_oidc_cookie_write_requires_explicit_origin(monkeypatch, method):
    api = signed_in_client(monkeypatch)
    request = api.request(
        method, "/api/v1/profile/facts", json=FACT,
    )
    assert request.status_code == 403
    assert request.json()["error"]["code"] == "csrf_origin_denied"
    assert request.headers["cache-control"] == "no-store"
    assert api.get("/api/v1/profile/facts").json()["count"] == 0


@pytest.mark.parametrize("origin", [
    "https://other.obumai.com",  # sibling subdomain is same-site, not same-origin
    "https://smartploy.obumai.com.attacker.invalid",
    "http://smartploy.obumai.com",
    "https://smartploy.obumai.com:444",
    "null",
    "https://smartploy.obumai.com/",
    "",
])
def test_oidc_cookie_write_rejects_cross_origin_or_opaque_origins(monkeypatch, origin):
    api = signed_in_client(monkeypatch)
    headers = {"Origin": origin, "Sec-Fetch-Site": "same-site"}
    response = api.post("/api/v1/profile/facts", json=FACT, headers=headers)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "csrf_origin_denied"
    assert api.get("/api/v1/profile/facts").json()["count"] == 0


@pytest.mark.parametrize("fetch_site", ["cross-site", "same-site"])
def test_cookie_mutation_rejects_bad_fetch_site_even_with_valid_origin(
    monkeypatch, fetch_site
):
    api = signed_in_client(monkeypatch)
    response = api.post(
        "/api/v1/profile/facts", json=FACT,
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": fetch_site},
    )
    assert response.status_code == 403
    assert api.get("/api/v1/profile/facts").json()["count"] == 0


def test_oidc_cookie_same_origin_api_mutation_succeeds(monkeypatch):
    api = signed_in_client(monkeypatch)
    response = api.post(
        "/api/v1/profile/facts",
        json=FACT,
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["fact"]["value"] == FACT["value"]
    # Safe reads never need an Origin header.
    profile = api.get("/api/v1/profile/facts")
    assert profile.status_code == 200
    assert profile.json()["count"] == 1


def test_cross_origin_cookie_write_is_denied_before_application_side_effect(
    monkeypatch,
):
    api = signed_in_client(monkeypatch)
    blocked = api.post(
        "/api/v1/preparations/unknown/refresh",
        headers={
            "Origin": "https://other.obumai.com",
            "Sec-Fetch-Site": "same-site",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data="irrelevant=form",
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_origin_denied"
    allowed = api.post(
        "/api/v1/preparations/unknown/refresh",
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )
    assert allowed.status_code == 404  # reaches normal tenant route, not CSRF guard


class FixtureAccessVerifier:
    def verify(self, assertion: str) -> AccessPrincipal:
        assert assertion == "valid-fixture-access"
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer=ACCESS_ISSUER,
            subject="fixture-cloudflare-user",
            email="shared@example.invalid",
            audience="fixture",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            key_id="synthetic",
        )


def test_hybrid_access_without_cookie_keeps_existing_bearer_behavior(monkeypatch):
    api = signed_in_client(monkeypatch, mode="hybrid", access_verifier=FixtureAccessVerifier())
    api.cookies.clear()
    response = api.post(
        "/api/v1/profile/facts",
        json=FACT,
        headers={"Cf-Access-Jwt-Assertion": "valid-fixture-access"},
    )
    assert response.status_code == 201, response.text


def test_hybrid_cannot_bypass_cookie_csrf_with_access_header(monkeypatch):
    api = signed_in_client(monkeypatch, mode="hybrid", access_verifier=FixtureAccessVerifier())
    response = api.post(
        "/api/v1/profile/facts",
        json=FACT,
        headers={
            "Cf-Access-Jwt-Assertion": "valid-fixture-access",
            "Origin": "https://other.obumai.com",
            "Sec-Fetch-Site": "same-site",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_denied"

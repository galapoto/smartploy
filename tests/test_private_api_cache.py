"""Successful private API responses must not be cached between accounts.

Synthetic OIDC and Cloudflare identities only. No production browser,
real identity provider, ATS polling or employer application is involved.
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
OIDC_ISSUER = "https://auth.obumai.com"
ACCESS_ISSUER = "https://synthetic.cloudflareaccess.com"


class SyntheticAccessVerifier:
    def verify(self, assertion: str) -> AccessPrincipal:
        assert assertion == "fixture-owner-a"
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer=ACCESS_ISSUER,
            subject="synthetic-owner-a",
            email="owner@example.invalid",
            audience="smartploy-synthetic",
            issued_at=now - timedelta(seconds=5),
            expires_at=now + timedelta(minutes=5),
            key_id="synthetic",
        )


@pytest.fixture(params=["oidc", "cloudflare"])
def authenticated_client(request, monkeypatch):
    mode = request.param
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", mode)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true" if mode == "cloudflare" else "false")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    headers = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
    verifier = None
    if mode == "oidc":
        monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", OIDC_ISSUER)
        monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic-smartploy")
        monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
        monkeypatch.setenv(
            "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
            ORIGIN + "/auth/logged-out",
        )
        principal = AuthenticatedPrincipal(
            issuer=OIDC_ISSUER, subject="synthetic-owner-a",
            email="owner@example.invalid", auth_source="oidc",
        ).normalized()
        binding = identities.resolve_or_create(principal)
        issued = sessions.create(
            user_id=binding.user_id,
            principal=principal,
            provider_session_id="synthetic-only",
            ttl_seconds=3600,
        )
    else:
        monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", ACCESS_ISSUER)
        monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-synthetic")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "owner@example.invalid")
        verifier = SyntheticAccessVerifier()
        headers["Cf-Access-Jwt-Assertion"] = "fixture-owner-a"

    client = TestClient(
        create_app(
            SmartployService(),
            identity_repository=identities,
            session_repository=sessions,
            oidc_client=object(),
            access_verifier=verifier,
        ),
        base_url=ORIGIN,
    )
    if mode == "oidc":
        client.cookies.set(SESSION_COOKIE_NAME, issued.token)

    with client:
        yield client, headers


@pytest.mark.parametrize("path", [
    "/api/v1/session",
    "/api/v1/dashboard",
    "/api/v1/profile/facts",
    "/api/v1/profile/cv",
    "/api/v1/search-preferences",
    "/api/v1/application-workspaces",
    "/api/v1/jobs",
])
def test_authenticated_private_api_gets_never_cached(authenticated_client, path):
    client, headers = authenticated_client
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_authenticated_private_api_writes_never_cached(authenticated_client):
    client, headers = authenticated_client
    response = client.post(
        "/api/v1/profile/facts",
        headers=headers,
        json={"fact_type": "skill", "value": "Fictional testing", "approved": False},
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_public_health_contract_stays_separate(authenticated_client):
    client, _ = authenticated_client
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["service"] == "smartploy"

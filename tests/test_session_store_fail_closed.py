"""Synthetic failure gates for first-party OIDC session-store outages.

The tests never authenticate live accounts, call a real identity provider,
or access production Postgres. A failing session lookup MUST NOT become
a successful Cloudflare fallback in hybrid mode.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.identity import MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


class BrokenSessionRepository(MemorySessionRepository):
    def get(self, token: str):
        del token
        raise RuntimeError("synthetic-private-session-storage-secret-never-expose")


class SyntheticAccessVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, assertion: str) -> AccessPrincipal:
        self.calls += 1
        assert assertion == "fixture-access-assertion"
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer="https://example.cloudflareaccess.com",
            subject="cloudflare-synthetic-owner",
            email="owner@example.com",
            audience="fixture-audience-123",
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(minutes=5),
            key_id="fixture-only",
        )


def configure(monkeypatch, *, mode: str = "oidc") -> None:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", mode)
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true" if mode == "hybrid" else "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", "https://auth.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "smartploy-synthetic")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/callback",
    )
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/logged-out",
    )
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    if mode == "hybrid":
        monkeypatch.setenv(
            "SMARTPLOY_ACCESS_ISSUER", "https://example.cloudflareaccess.com"
        )
        monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "fixture-audience-123")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "owner@example.com")


def test_oidc_cookie_storage_outage_returns_bounded_503_without_running_private_api(monkeypatch):
    configure(monkeypatch)
    api = TestClient(
        create_app(
            SmartployService(),
            oidc_client=object(),
            session_repository=BrokenSessionRepository(),
            identity_repository=MemoryIdentityRepository(),
        ),
        base_url="https://smartploy.obumai.com",
    )
    api.cookies.set(SESSION_COOKIE_NAME, "fixture-cookie-never-a-real-user-token")

    for verb, path, kwargs in [
        ("get", "/api/v1/session", {}),
        ("get", "/api/v1/jobs", {}),
        ("post", "/api/v1/private-jobs", {
            "json": {
                "company": "Example Ltd",
                "role_title": "Synthetic data analyst",
                "description": "Only a fictional saved job",
            },
            "headers": {
                "Origin": "https://smartploy.obumai.com",
                "Sec-Fetch-Site": "same-origin",
            },
        }),
    ]:
        response = getattr(api, verb)(path, **kwargs)
        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "session_unavailable",
                "message": "SmartPloy session verification is temporarily unavailable.",
            }
        }
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "synthetic-private-session-storage-secret" not in response.text
        assert "set-cookie" not in response.headers

    # Public readiness and confirmation GET must not depend on a private
    # cookie-store lookup or trigger server revocation.
    assert api.get("/healthz").status_code == 200
    assert api.get("/auth/logout").status_code == 200


def test_hybrid_broken_oidc_cookie_never_downgrades_to_cloudflare_identity(monkeypatch):
    configure(monkeypatch, mode="hybrid")
    verifier = SyntheticAccessVerifier()
    api = TestClient(
        create_app(
            SmartployService(),
            access_verifier=verifier,
            oidc_client=object(),
            session_repository=BrokenSessionRepository(),
            identity_repository=MemoryIdentityRepository(),
        ),
        base_url="https://smartploy.obumai.com",
    )
    headers = {"Cf-Access-Jwt-Assertion": "fixture-access-assertion"}
    api.cookies.set(SESSION_COOKIE_NAME, "fixture-opaque-oidc-cookie")
    denied = api.get("/api/v1/session", headers=headers)
    assert denied.status_code == 503
    assert denied.json()["error"]["code"] == "session_unavailable"
    assert verifier.calls == 0
    assert "login_url" not in denied.json()
    assert "synthetic-private-session-storage-secret" not in denied.text

    # An assertion-only request is independently verified as before.
    # We are not disabling Cloudflare Access fallback for cookie-free users.
    api.cookies.clear()
    asserted = api.get("/api/v1/session", headers=headers)
    assert asserted.status_code == 200
    assert asserted.json()["authenticated"] is True
    assert asserted.json()["auth_source"] == "cloudflare_access"
    assert verifier.calls == 1

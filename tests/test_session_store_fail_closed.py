"""Synthetic failure gates for first-party OIDC session-store outages.

The tests never authenticate live accounts, call a real identity provider,
or access production Postgres. A failing session lookup MUST NOT become
a successful Cloudflare fallback in hybrid mode.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
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


@pytest.mark.parametrize("stale_cookie", ["unknown", "expired", "revoked"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_hybrid_stale_oidc_cookie_never_switches_to_cloudflare_owner(
    monkeypatch, stale_cookie, method
):
    """Same-email identities: a failed OIDC session must not become CF user A."""
    configure(monkeypatch, mode="hybrid")
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    verifier = SyntheticAccessVerifier()
    principal_b = AuthenticatedPrincipal(
        issuer="https://auth.obumai.com",
        subject="synthetic-oidc-user-b",
        email="owner@example.com",
        auth_source="oidc",
    ).normalized()
    binding_b = identities.resolve_or_create(principal_b)
    issued = sessions.create(
        user_id=binding_b.user_id, principal=principal_b,
        provider_session_id="synthetic-provider-b", ttl_seconds=3600,
    )
    with TestClient(
        create_app(
            SmartployService(),
            access_verifier=verifier,
            oidc_client=object(),
            session_repository=sessions,
            identity_repository=identities,
        ),
        base_url="https://smartploy.obumai.com",
    ) as api:
        headers = {"Cf-Access-Jwt-Assertion": "fixture-access-assertion"}
        api.cookies.set(SESSION_COOKIE_NAME, issued.token)

        # Valid OIDC B takes precedence over valid Cloudflare assertion A.
        before = api.get("/api/v1/session", headers=headers)
        assert before.status_code == 200, before.text
        assert before.json()["user_id"] == binding_b.user_id
        assert before.json()["auth_source"] == "oidc"
        assert verifier.calls == 0

        if stale_cookie == "revoked":
            sessions.revoke(issued.token)
        elif stale_cookie == "expired":
            expired = sessions.create(
                user_id=binding_b.user_id, principal=principal_b,
                ttl_seconds=0,
            )
            api.cookies.set(SESSION_COOKIE_NAME, expired.token)
        else:
            api.cookies.set(SESSION_COOKIE_NAME, "unknown-synthetic-session-token")

        if method == "GET":
            result = api.get("/api/v1/session", headers=headers)
        else:
            result = api.post(
                "/api/v1/profile/facts", headers={
                    **headers,
                    "Origin": "https://smartploy.obumai.com",
                    "Sec-Fetch-Site": "same-origin",
                },
                json={"fact_type": "skill", "value": "Must never write as A",
                      "approved": True},
            )

        assert result.status_code == 401, result.text
        assert result.json()["error"]["code"] == "session_expired"
        assert result.json()["login_url"] == "/auth/login"
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-content-type-options"] == "nosniff"
        assert "Max-Age=0" in result.headers["set-cookie"]
        assert verifier.calls == 0

        # After the rejected response has cleared the browser's old cookie,
        # a fresh cookie-free Access request still follows the old fallback.
        cookie_free = api.get("/api/v1/session", headers=headers)
        assert cookie_free.status_code == 200, cookie_free.text
        assert cookie_free.json()["auth_source"] == "cloudflare_access"
        assert cookie_free.json()["user_id"] != binding_b.user_id
        assert verifier.calls == 1
        facts_a = api.get("/api/v1/profile/facts", headers=headers)
        assert facts_a.status_code == 200
        assert facts_a.json()["count"] == 0


@pytest.mark.parametrize("stale_cookie", ["unknown", "revoked"])
def test_oidc_only_stale_cookie_clears_session_without_private_reads(
    monkeypatch, stale_cookie
):
    configure(monkeypatch, mode="oidc")
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    principal = AuthenticatedPrincipal(
        issuer="https://auth.obumai.com", subject="synthetic-oidc-user",
        email="reader@example.invalid", auth_source="oidc",
    ).normalized()
    binding = identities.resolve_or_create(principal)
    issued = sessions.create(
        user_id=binding.user_id, principal=principal, ttl_seconds=3600,
    )
    if stale_cookie == "revoked":
        sessions.revoke(issued.token)
        token = issued.token
    else:
        token = "unknown-synthetic-session-token"

    with TestClient(
        create_app(
            SmartployService(), oidc_client=object(),
            identity_repository=identities, session_repository=sessions,
        ), base_url="https://smartploy.obumai.com",
    ) as api:
        api.cookies.set(SESSION_COOKIE_NAME, token)
        denied = api.get("/api/v1/profile/facts")
        assert denied.status_code == 401, denied.text
        assert denied.json()["error"]["code"] == "session_expired"
        assert denied.headers["cache-control"] == "no-store"
        assert "Max-Age=0" in denied.headers["set-cookie"]

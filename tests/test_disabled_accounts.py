"""Server-enforced disabled-account and changed-session request boundary.

All identities and assertions here are synthetic.  They do not count as
owner-authenticated production browser acceptance.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from psycopg import connect

from smartploy.access import AccessPrincipal, AccessVerificationError
from smartploy.api import create_app
from smartploy.identity import (
    AuthenticatedPrincipal,
    MemoryIdentityRepository,
    PostgresIdentityRepository,
)
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


ISSUER = "https://example.cloudflareaccess.com"
OIDC_ISSUER = "https://auth.obumai.com"
EMAIL = "shared@example.invalid"


class FictionalAccessVerifier:
    def verify(self, assertion: str) -> AccessPrincipal:
        if assertion not in {"owner-a", "owner-b"}:
            raise AccessVerificationError("invalid_token", "Synthetic assertion rejected")
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer=ISSUER, subject=assertion, email=EMAIL,
            audience="smartploy-synthetic", key_id="test-key",
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(minutes=5),
        )


class FakeOIDCCallback:
    async def authorize_access_token(self, request):
        del request
        return {
            "userinfo": {
                "sub": "owner-a",
                "email": EMAIL,
                "sid": "synthetic-provider-session",
            }
        }


class BrokenIdentityRepository(MemoryIdentityRepository):
    def resolve_or_create(self, principal: AuthenticatedPrincipal):
        raise RuntimeError("internal identity storage exception -- never expose")


def cloudflare_env(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", ISSUER)
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-synthetic")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", EMAIL)
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)


def oidc_env(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", OIDC_ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "smartploy-test")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/callback",
    )
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/logged-out",
    )
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)


def identity(subject: str, issuer: str = OIDC_ISSUER) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=issuer, subject=subject, email=EMAIL,
        auth_source="oidc" if issuer == OIDC_ISSUER else "cloudflare_access",
    )


def disable_memory(repo: MemoryIdentityRepository, user_id: str) -> None:
    repo._bindings[user_id] = replace(repo._bindings[user_id], status="disabled")


def test_disabled_cloudflare_identity_denies_all_protected_reads_and_writes(monkeypatch):
    cloudflare_env(monkeypatch)
    identities = MemoryIdentityRepository()
    app = TestClient(create_app(
        SmartployService(),
        access_verifier=FictionalAccessVerifier(),
        identity_repository=identities,
    ))
    headers_a = {"Cf-Access-Jwt-Assertion": "owner-a"}
    headers_b = {"Cf-Access-Jwt-Assertion": "owner-b"}
    first = app.get("/api/v1/session", headers=headers_a)
    assert first.status_code == 200
    user_a = first.json()["user_id"]
    user_b = app.get("/api/v1/session", headers=headers_b).json()["user_id"]
    assert user_a != user_b
    disable_memory(identities, user_a)

    for method, path, payload in [
        ("get", "/api/v1/session", None),
        ("get", "/api/v1/jobs", None),
        ("get", "/api/v1/sources/health", None),
        ("get", "/api/v1/profile/cv", None),
        ("post", "/api/v1/profile/facts", {"fact_type": "skill", "value": "Python"}),
        ("post", "/api/v1/jobs/ingest", {"observation": {"source_id": "manual-import"}}),
    ]:
        response = getattr(app, method)(path, headers=headers_a, **(
            {"json": payload} if payload is not None else {}
        ))
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["error"]["code"] == "account_disabled"
        assert response.headers["cache-control"] == "no-store"
        assert "user_id" not in response.text

    healthy_other = app.get("/api/v1/session", headers=headers_b)
    assert healthy_other.status_code == 200
    assert healthy_other.json()["user_id"] == user_b
    assert app.get("/healthz").status_code == 200


def test_identity_repository_outage_does_not_fall_back_to_old_session(monkeypatch):
    cloudflare_env(monkeypatch)
    api = TestClient(create_app(
        SmartployService(),
        access_verifier=FictionalAccessVerifier(),
        identity_repository=BrokenIdentityRepository(),
    ))
    response = api.get("/api/v1/jobs", headers={"Cf-Access-Jwt-Assertion": "owner-a"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "identity_unavailable"
    assert "internal identity storage exception" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_oidc_cookie_is_revoked_when_account_becomes_disabled(monkeypatch):
    oidc_env(monkeypatch)
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    account = identity("owner-a")
    binding = identities.resolve_or_create(account)
    issued = sessions.create(
        user_id=binding.user_id, principal=account,
        provider_session_id="synthetic-sid", ttl_seconds=3600,
    )
    api = TestClient(
        create_app(
            SmartployService(), oidc_client=FakeOIDCCallback(),
            identity_repository=identities, session_repository=sessions,
        ),
        base_url="https://smartploy.obumai.com",
        follow_redirects=False,
    )
    api.cookies.set(SESSION_COOKIE_NAME, issued.token)
    assert api.get("/api/v1/session").status_code == 200

    disable_memory(identities, binding.user_id)
    denied = api.get("/api/v1/profile/facts")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "account_disabled"
    assert sessions.get(issued.token) is None

    # Re-enabling the account cannot restore an old revoked session.
    identities._bindings[binding.user_id] = replace(
        identities._bindings[binding.user_id], status="active"
    )
    assert api.get("/api/v1/session").status_code == 401
    preview = api.get("/auth/logout")
    assert preview.status_code == 200
    assert "Confirm sign out" in preview.text
    logout = api.post("/auth/logout", headers={
        "Origin": "https://smartploy.obumai.com",
        "Sec-Fetch-Site": "same-origin",
    })
    assert logout.status_code == 303
    assert logout.headers["location"] == "/auth/logged-out"
    assert "Max-Age=0" in logout.headers["set-cookie"]


def test_oidc_callback_rejects_disabled_identity_without_issuing_cookie(monkeypatch):
    oidc_env(monkeypatch)
    identities = MemoryIdentityRepository()
    account = identity("owner-a")
    binding = identities.resolve_or_create(account)
    disable_memory(identities, binding.user_id)
    sessions = MemorySessionRepository()
    api = TestClient(
        create_app(
            SmartployService(), oidc_client=FakeOIDCCallback(),
            identity_repository=identities, session_repository=sessions,
        ),
        base_url="https://smartploy.obumai.com",
        follow_redirects=False,
    )
    result = api.get("/auth/callback?code=synthetic&state=synthetic")
    assert result.status_code == 403
    assert "access is disabled" in result.text
    assert SESSION_COOKIE_NAME not in result.headers.get("set-cookie", "")
    assert api.get("/api/v1/session").status_code == 401


def test_oidc_session_cannot_silently_change_bound_user(monkeypatch):
    oidc_env(monkeypatch)
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    actual = identity("owner-a")
    different = identity("owner-b")
    identities.resolve_or_create(actual)
    other_binding = identities.resolve_or_create(different)
    issued = sessions.create(
        user_id=other_binding.user_id, principal=actual,
        provider_session_id="synthetic-relinked-account",
        ttl_seconds=3600,
    )
    api = TestClient(
        create_app(
            SmartployService(), oidc_client=FakeOIDCCallback(),
            identity_repository=identities, session_repository=sessions,
        ),
        base_url="https://smartploy.obumai.com",
        follow_redirects=False,
    )
    api.cookies.set(SESSION_COOKIE_NAME, issued.token)
    result = api.get("/api/v1/session")
    assert result.status_code == 401
    assert result.json()["error"]["code"] == "session_identity_changed"
    assert sessions.get(issued.token) is None


@pytest.mark.skipif(
    not os.getenv("SMARTPLOY_TEST_DATABASE_URL"),
    reason="Requires PostgreSQL test database",
)
def test_disabled_postgres_identity_stays_disabled_when_a_valid_access_token_arrives(
    monkeypatch,
):
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    cloudflare_env(monkeypatch)
    identities = PostgresIdentityRepository(dsn)
    subject = "pg-disabled-" + uuid4().hex
    principal = identity(subject, ISSUER)
    binding = identities.resolve_or_create(principal)
    with connect(dsn) as conn:
        conn.execute(
            "UPDATE smartploy_users SET status = 'disabled' WHERE user_id = %s",
            (binding.user_id,),
        )
    try:
        assert identities.resolve_or_create(principal).status == "disabled"
        class SpecificSyntheticVerifier:
            def verify(self, token: str) -> AccessPrincipal:
                assert token == "only-this-user"
                now = datetime.now(timezone.utc)
                return AccessPrincipal(
                    issuer=ISSUER, subject=subject, email=EMAIL,
                    audience="smartploy-synthetic", key_id="test-key",
                    issued_at=now, expires_at=now + timedelta(minutes=5),
                )
        api = TestClient(create_app(
            SmartployService(),
            access_verifier=SpecificSyntheticVerifier(),
            identity_repository=identities,
        ))
        denied = api.get(
            "/api/v1/profile/status",
            headers={"Cf-Access-Jwt-Assertion": "only-this-user"},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "account_disabled"
    finally:
        with connect(dsn) as conn:
            conn.execute(
                "DELETE FROM smartploy_users WHERE user_id = %s",
                (binding.user_id,),
            )

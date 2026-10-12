import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.identity import MemoryIdentityRepository
from smartploy.oidc import (
    MemoryOIDCStateCache,
    MemorySessionRepository,
    OIDCSettings,
    SESSION_COOKIE_NAME,
    AuthenticationSettings,
    build_oidc_registry,
)
from smartploy.service import SmartployService


OIDC_ISSUER = "https://auth.obumai.com"
OIDC_CLIENT_ID = "smartploy-test-client"


def configure_oidc(monkeypatch, *, mode="oidc"):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", mode)
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false" if mode == "oidc" else "true")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", OIDC_ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", OIDC_CLIENT_ID)
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/callback",
    )
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/logged-out",
    )
    if mode == "hybrid":
        monkeypatch.setenv(
            "SMARTPLOY_ACCESS_ISSUER",
            "https://example.cloudflareaccess.com",
        )
        monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "access-audience")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "owner@example.com")


class FakeOIDCClient:
    def __init__(self):
        self.login_redirect_uri = ""
        self.logout_called = False

    async def authorize_redirect(self, request, redirect_uri):
        del request
        self.login_redirect_uri = str(redirect_uri)
        return RedirectResponse(
            "https://auth.obumai.com/oauth/v2/authorize"
            "?response_type=code&code_challenge=fixture&code_challenge_method=S256",
            status_code=302,
        )

    async def authorize_access_token(self, request):
        del request
        return {
            "userinfo": {
                "sub": "obum-user-123",
                "email": "user@example.com",
                "sid": "provider-session-123",
            },
            "access_token": "must-not-be-persisted",
            "refresh_token": "must-not-be-persisted",
            "id_token": "must-not-be-persisted",
        }

    async def logout_redirect(
        self,
        request,
        post_logout_redirect_uri=None,
        client_id=None,
    ):
        del request, post_logout_redirect_uri, client_id
        self.logout_called = True
        return RedirectResponse(
            "https://auth.obumai.com/oidc/v1/end_session",
            status_code=302,
        )


class FakeAccessVerifier:
    def verify(self, token):
        assert token == "fixture-access-assertion"
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            email="owner@example.com",
            subject="cloudflare-owner",
            issuer="https://example.cloudflareaccess.com",
            audience="access-audience",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            key_id="fixture",
        )


def test_authlib_authorization_request_uses_pkce_nonce_and_server_side_state():
    authentication = AuthenticationSettings(environment="production", mode="oidc")
    settings = OIDCSettings(
        issuer=OIDC_ISSUER,
        client_id=OIDC_CLIENT_ID,
        public_origin="https://smartploy.obumai.com",
        redirect_uri="https://smartploy.obumai.com/auth/callback",
        post_logout_redirect_uri="https://smartploy.obumai.com/auth/logged-out",
        scope="openid profile email",
        session_ttl_seconds=43200,
        state_ttl_seconds=600,
    )
    cache = MemoryOIDCStateCache()
    oauth = build_oidc_registry(settings, cache)
    client = oauth.create_client("obum_identity")
    client.server_metadata.update(
        {
            "issuer": OIDC_ISSUER,
            "authorization_endpoint": OIDC_ISSUER + "/oauth/v2/authorize",
            "token_endpoint": OIDC_ISSUER + "/oauth/v2/token",
            "jwks_uri": OIDC_ISSUER + "/oauth/v2/keys",
            "_loaded_at": time.time(),
        }
    )

    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "path": "/auth/login",
        "raw_path": b"/auth/login",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("smartploy.obumai.com", 443),
        "root_path": "",
        "session": {},
    }
    request = Request(scope)

    async def run():
        response = await client.authorize_redirect(request, settings.redirect_uri)
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"][0]
        assert query["nonce"][0]
        assert query["state"][0]
        assert query["redirect_uri"] == [settings.redirect_uri]
        state = query["state"][0]
        cached = await cache.get("_state_obum_identity_" + state)
        assert cached is not None
        payload = json.loads(cached)["data"]
        assert payload["nonce"] == query["nonce"][0]
        assert payload["code_verifier"]
        assert payload["redirect_uri"] == settings.redirect_uri

    import asyncio

    asyncio.run(run())
    assert authentication.oidc_enabled is True


def test_oidc_mode_denies_api_then_creates_opaque_host_only_session(monkeypatch):
    configure_oidc(monkeypatch)
    sessions = MemorySessionRepository()
    identity = MemoryIdentityRepository()
    provider = FakeOIDCClient()
    api = TestClient(
        create_app(
            SmartployService(),
            oidc_client=provider,
            session_repository=sessions,
            identity_repository=identity,
        ),
        base_url="https://smartploy.obumai.com",
        follow_redirects=False,
    )

    denied = api.get("/api/v1/dashboard")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "authentication_required"
    assert denied.json()["login_url"] == "/auth/login"

    login = api.get("/auth/login")
    assert login.status_code == 302
    assert provider.login_redirect_uri == "https://smartploy.obumai.com/auth/callback"
    assert "code_challenge_method=S256" in login.headers["location"]

    callback = api.get("/auth/callback?code=fixture&state=fixture")
    assert callback.status_code == 303
    cookie = callback.headers["set-cookie"]
    assert SESSION_COOKIE_NAME + "=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Domain=" not in cookie

    raw = api.cookies.get(SESSION_COOKIE_NAME)
    assert raw
    record = sessions.get(raw)
    assert record is not None
    assert record.subject == "obum-user-123"
    assert record.user_id.startswith("usr-")
    assert "must-not-be-persisted" not in repr(record)

    current = api.get("/api/v1/session")
    assert current.status_code == 200
    body = current.json()
    assert body["authenticated"] is True
    assert body["auth_source"] == "oidc"
    assert body["user_id"].startswith("usr-")
    assert body["profile_id"].startswith("profile-")
    assert "obum-user-123" not in str(body)


def test_logout_revokes_local_session_before_provider_redirect(monkeypatch):
    configure_oidc(monkeypatch)
    sessions = MemorySessionRepository()
    provider = FakeOIDCClient()
    api = TestClient(
        create_app(
            SmartployService(),
            oidc_client=provider,
            session_repository=sessions,
            identity_repository=MemoryIdentityRepository(),
        ),
        base_url="https://smartploy.obumai.com",
        follow_redirects=False,
    )
    api.get("/auth/callback?code=fixture&state=fixture")
    raw = api.cookies.get(SESSION_COOKIE_NAME)
    assert raw and sessions.get(raw) is not None

    preview = api.get("/auth/logout")
    assert preview.status_code == 200
    assert "Confirm sign out" in preview.text
    assert sessions.get(raw) is not None
    assert provider.logout_called is False
    assert "set-cookie" not in preview.headers

    logout = api.post("/auth/logout", headers={
        "Origin": "https://smartploy.obumai.com",
        "Sec-Fetch-Site": "same-origin",
    })
    assert logout.status_code == 302
    assert provider.logout_called is True
    assert sessions.get(raw) is None
    assert logout.headers["location"].startswith("https://auth.obumai.com/")
    assert "Max-Age=0" in logout.headers["set-cookie"]


def test_hybrid_accepts_cloudflare_fallback_without_oidc_session(monkeypatch):
    configure_oidc(monkeypatch, mode="hybrid")
    api = TestClient(
        create_app(
            SmartployService(),
            access_verifier=FakeAccessVerifier(),
            oidc_client=FakeOIDCClient(),
            session_repository=MemorySessionRepository(),
            identity_repository=MemoryIdentityRepository(),
        ),
        base_url="https://smartploy.obumai.com",
    )
    response = api.get(
        "/api/v1/session",
        headers={"Cf-Access-Jwt-Assertion": "fixture-access-assertion"},
    )
    assert response.status_code == 200
    assert response.json()["auth_source"] == "cloudflare_access"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SMARTPLOY_OIDC_ISSUER", "http://auth.obumai.com"),
        ("SMARTPLOY_OIDC_CLIENT_ID", ""),
        ("SMARTPLOY_OIDC_REDIRECT_URI", "https://evil.example/auth/callback"),
        ("SMARTPLOY_OIDC_SCOPE", "profile email"),
    ],
)
def test_invalid_oidc_production_configuration_fails_closed(monkeypatch, name, value):
    configure_oidc(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        create_app(SmartployService(), oidc_client=FakeOIDCClient())

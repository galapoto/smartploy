"""Logout is a deliberate same-origin POST, never an effect of GET navigation.

All sessions, principals and identity providers in this module are synthetic.
"""
from __future__ import annotations

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


ORIGIN = "https://smartploy.obumai.com"


class TestProvider:
    __test__ = False
    def __init__(self, *, fail: bool = False):
        self.logout_count = 0
        self.fail = fail

    async def logout_redirect(
        self, request, post_logout_redirect_uri=None, client_id=None
    ):
        assert post_logout_redirect_uri == ORIGIN + "/auth/logged-out"
        assert client_id == "smartploy-fixture"
        self.logout_count += 1
        if self.fail:
            raise RuntimeError("synthetic provider secret should not be disclosed")
        return RedirectResponse(
            "https://auth.obumai.com/oidc/v1/end_session",
            status_code=302,
        )


class BrokenRevokeSessionRepository(MemorySessionRepository):
    def revoke(self, token: str) -> None:
        del token
        raise RuntimeError("synthetic database password: never reveal")


def make_client(monkeypatch, *, provider=None, session_store=None, disabled=False):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", "https://auth.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "smartploy-fixture")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback"
    )
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out"
    )
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    store = session_store or MemorySessionRepository()
    identity = MemoryIdentityRepository()
    principal = AuthenticatedPrincipal(
        issuer="https://auth.obumai.com",
        subject="synthetic-account",
        email="example@example.invalid",
        auth_source="oidc",
    )
    binding = identity.resolve_or_create(principal)
    if disabled:
        from dataclasses import replace
        identity._bindings[binding.user_id] = replace(binding, status="disabled")
    issued = store.create(
        user_id=binding.user_id, principal=principal,
        provider_session_id="synthetic-provider-session", ttl_seconds=3600,
    )
    remote = provider or TestProvider()
    client = TestClient(
        create_app(
            SmartployService(), oidc_client=remote,
            identity_repository=identity, session_repository=store,
        ),
        base_url=ORIGIN,
        follow_redirects=False,
    )
    client.cookies.set(SESSION_COOKIE_NAME, issued.token)
    return client, store, issued.token, remote


@pytest.mark.parametrize("origin", [
    "https://malicious.example.invalid",
    "https://sub.obumai.com",
    "",
])
def test_cross_site_get_logout_is_inert(monkeypatch, origin):
    api, sessions, cookie, provider = make_client(monkeypatch)
    response = api.get("/auth/logout", headers={"Origin": origin, "Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 200
    assert 'method="post"' in response.text
    assert 'action="/auth/logout"' in response.text
    assert "Confirm sign out" in response.text
    assert sessions.get(cookie) is not None
    assert provider.logout_count == 0
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert "form-action 'self'" in response.headers["content-security-policy"]


def test_logged_out_landing_get_cannot_clear_an_existing_cookie(monkeypatch):
    api, sessions, cookie, provider = make_client(monkeypatch)
    result = api.get("/auth/logged-out", headers={"Sec-Fetch-Site": "cross-site"})
    assert result.status_code == 200
    assert "set-cookie" not in result.headers
    assert sessions.get(cookie) is not None
    assert api.cookies.get(SESSION_COOKIE_NAME) == cookie
    assert provider.logout_count == 0


@pytest.mark.parametrize("origin,site", [
    ("", ""),
    ("null", "cross-site"),
    ("https://sub.obumai.com", "same-site"),
    ("https://smartploy.obumai.com.attacker.invalid", "cross-site"),
    ("http://smartploy.obumai.com", "same-site"),
    ("https://smartploy.obumai.com:444", "same-site"),
    ("https://smartploy.obumai.com/", "same-origin"),
    (ORIGIN, "same-site"),
    (ORIGIN, "cross-site"),
])
def test_cross_origin_logout_post_never_revokes_or_redirects(
    monkeypatch, origin, site
):
    api, sessions, cookie, provider = make_client(monkeypatch)
    response = api.post(
        "/auth/logout",
        headers={"Origin": origin, "Sec-Fetch-Site": site},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_denied"
    assert response.headers["cache-control"] == "no-store"
    assert sessions.get(cookie) is not None
    assert provider.logout_count == 0
    assert api.cookies.get(SESSION_COOKIE_NAME) == cookie


def test_explicit_same_origin_post_revokes_before_provider_redirect(monkeypatch):
    api, sessions, cookie, provider = make_client(monkeypatch)
    confirmation = api.get("/auth/logout")
    assert confirmation.status_code == 200
    assert sessions.get(cookie) is not None

    response = api.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 302
    assert sessions.get(cookie) is None
    assert provider.logout_count == 1
    assert response.headers["location"] == "https://auth.obumai.com/oidc/v1/end_session"
    assert response.headers["cache-control"] == "no-store"
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert api.cookies.get(SESSION_COOKIE_NAME) is None


def test_disabled_user_can_confirm_same_origin_logout(monkeypatch):
    api, sessions, cookie, provider = make_client(monkeypatch, disabled=True)
    # Account status is enforced on API requests, but not the logout form.
    assert api.get("/api/v1/session").status_code == 403
    response = api.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 302
    assert sessions.get(cookie) is None
    assert provider.logout_count == 1


def test_failed_provider_redirect_does_not_restore_local_session(monkeypatch):
    provider = TestProvider(fail=True)
    api, sessions, cookie, _ = make_client(monkeypatch, provider=provider)
    response = api.post("/auth/logout", headers={"Origin": ORIGIN})
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/logged-out"
    assert sessions.get(cookie) is None
    assert api.cookies.get(SESSION_COOKIE_NAME) is None
    assert "synthetic provider secret" not in response.text


def test_revocation_outage_reports_incomplete_logout_and_clears_browser_cookie(
    monkeypatch,
):
    store = BrokenRevokeSessionRepository()
    provider = TestProvider()
    api, sessions, cookie, _ = make_client(
        monkeypatch, provider=provider, session_store=store,
    )
    response = api.post("/auth/logout", headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert "Sign-out could not be completed" in response.text
    assert "could not confirm session revocation" in response.text
    assert "synthetic database password" not in response.text
    assert sessions.get(cookie) is not None  # Do not claim revocation.
    assert api.cookies.get(SESSION_COOKIE_NAME) is None
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert provider.logout_count == 0
    assert response.headers["cache-control"] == "no-store"

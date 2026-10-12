"""Operator-only shared job/source mutation authorization.

All subjects and jobs are fictional. No external network/source is accessed.
A logged-in user and operator intentionally share the same email; the
server-issued user identity is the authorization boundary, not that email.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from smartploy.access import AccessPrincipal, AccessVerificationError
from smartploy.api import create_app
from smartploy.identity import (
    AuthenticatedPrincipal,
    MemoryIdentityRepository,
    UserProfileBinding,
    stable_user_id,
)
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.operator_access import (
    OperatorAccessPolicy,
    OperatorConfigurationError,
)
from smartploy.service import SmartployService


CF_ISSUER = "https://example.cloudflareaccess.com"
OIDC_ISSUER = "https://auth.obumai.com"
EMAIL = "shared@example.invalid"


class SyntheticAccessVerifier:
    def verify(self, assertion: str) -> AccessPrincipal:
        if assertion not in {"operator", "ordinary"}:
            raise AccessVerificationError("invalid_synthetic_assertion", "Invalid Access assertion")
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer=CF_ISSUER,
            subject="subject-" + assertion,
            email=EMAIL,
            audience="fixture-smartploy",
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(minutes=5),
            key_id="synthetic",
        )


SOURCE_PAYLOAD = {
    "source_id": "fixture-manual",
    "display_name": "Synthetic manual source",
    "source_class": "manual",
    "allowed_modes": ["manual"],
    "terms_review_status": "approved",
}
INGEST_PAYLOAD = {
    "observation": {
        "source_id": "fixture-manual",
        "source_mode": "manual",
        "source_url": "",
        "raw_text": "Synthetic Oy Junior Data Analyst Python SQL",
        "payload": {
            "company": "Synthetic Oy",
            "role_title": "Junior Data Analyst",
            "location": "Helsinki",
            "description": "Fictional Python and SQL posting",
        },
        "observed_at": "2026-10-12T00:00:00+00:00",
    }
}


def configure_cloudflare(monkeypatch, operators: str = "") -> None:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", CF_ISSUER)
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "fixture-smartploy")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", EMAIL)
    monkeypatch.setenv("SMARTPLOY_OPERATOR_USER_IDS", operators)
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)


def test_shared_writes_denied_by_default_to_every_authenticated_user(monkeypatch):
    configure_cloudflare(monkeypatch)
    service = SmartployService()
    api = TestClient(create_app(service, access_verifier=SyntheticAccessVerifier()))
    for account in ["operator", "ordinary"]:
        headers = {"Cf-Access-Jwt-Assertion": account}
        session = api.get("/api/v1/session", headers=headers)
        assert session.status_code == 200
        assert session.json()["authenticated"] is True
        assert session.json()["email"] == EMAIL
        assert api.post("/api/v1/sources", json=SOURCE_PAYLOAD, headers=headers).status_code == 403
        denied = api.post("/api/v1/jobs/ingest", json=INGEST_PAYLOAD, headers=headers)
        assert denied.status_code == 403
        assert denied.headers["cache-control"] == "no-store"
        assert denied.json()["detail"] == "Operator authorization required for shared job sources"
        # Read-only source introspection and public catalog remain accessible.
        assert api.get("/api/v1/sources/health", headers=headers).status_code == 200
        assert api.get("/api/v1/jobs", headers=headers).json()["count"] == 0

    assert service.source("fixture-manual") is None
    assert service.list_jobs() == []


def test_explicit_stable_operator_id_can_write_but_same_email_cannot(monkeypatch):
    operator_id = stable_user_id(CF_ISSUER, "subject-operator")
    ordinary_id = stable_user_id(CF_ISSUER, "subject-ordinary")
    assert operator_id != ordinary_id
    configure_cloudflare(monkeypatch, operator_id)
    service = SmartployService()
    api = TestClient(create_app(service, access_verifier=SyntheticAccessVerifier()))

    operator = {"Cf-Access-Jwt-Assertion": "operator"}
    ordinary = {
        "Cf-Access-Jwt-Assertion": "ordinary",
        "X-SmartPloy-Operator-User-ID": operator_id,
        "X-SmartPloy-Role": "administrator",
    }
    assert api.get("/api/v1/session", headers=operator).json()["user_id"] == operator_id
    assert api.get("/api/v1/session", headers=ordinary).json()["user_id"] == ordinary_id

    forbidden = api.post("/api/v1/sources", json=SOURCE_PAYLOAD, headers=ordinary)
    assert forbidden.status_code == 403
    assert api.post("/api/v1/jobs/ingest", json=INGEST_PAYLOAD, headers=ordinary).status_code == 403
    assert service.source("fixture-manual") is None
    assert service.list_jobs() == []

    registered = api.post("/api/v1/sources", json=SOURCE_PAYLOAD, headers=operator)
    assert registered.status_code == 200, registered.text
    assert service.source("fixture-manual") is not None
    # An ordinary user still cannot ingest after the operator registered it.
    assert api.post("/api/v1/jobs/ingest", json=INGEST_PAYLOAD, headers=ordinary).status_code == 403
    assert service.list_jobs() == []

    imported = api.post("/api/v1/jobs/ingest", json=INGEST_PAYLOAD, headers=operator)
    assert imported.status_code == 200, imported.text
    assert imported.json()["status"] == "discovered"
    assert api.get("/api/v1/jobs", headers=ordinary).json()["count"] == 1
    assert len(service.list_jobs()) == 1


def test_missing_or_invalid_access_session_cannot_mutate(monkeypatch):
    configure_cloudflare(monkeypatch, stable_user_id(CF_ISSUER, "subject-operator"))
    api = TestClient(create_app(SmartployService(), access_verifier=SyntheticAccessVerifier()))
    for path, payload in [
        ("/api/v1/sources", SOURCE_PAYLOAD),
        ("/api/v1/jobs/ingest", INGEST_PAYLOAD),
    ]:
        assert api.post(path, json=payload).status_code == 401
        assert api.post(
            path, json=payload, headers={"Cf-Access-Jwt-Assertion": "bogus"}
        ).status_code == 401


def test_only_active_resolved_users_may_be_operators():
    user_id = stable_user_id(CF_ISSUER, "subject-operator")
    policy = OperatorAccessPolicy(user_ids=frozenset({user_id}))
    binding = UserProfileBinding(
        user_id=user_id, profile_id="profile-example", email=EMAIL,
    )
    assert policy.allows(binding)
    assert not policy.allows(replace(binding, status="disabled"))
    assert not policy.allows(replace(binding, user_id=stable_user_id(CF_ISSUER, "other")))
    assert not policy.allows(None)


@pytest.mark.parametrize("bad", [
    "*",
    "owner@example.invalid",
    "usr-abcdef",
    "usr-" + "a" * 32 + ",",
    "usr-" + "a" * 32 + ",usr-" + "a" * 32,
    "usr-" + "a" * 32 + ",not-an-operator",
    ",".join("usr-" + f"{i:032x}" for i in range(17)),
    "X" * 1025,
])
def test_invalid_operator_allowlist_fails_closed_during_startup(monkeypatch, bad):
    configure_cloudflare(monkeypatch, bad)
    with pytest.raises(OperatorConfigurationError):
        create_app(SmartployService(), access_verifier=SyntheticAccessVerifier())


def test_development_only_disabled_auth_retains_manual_ingest_fixtures(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "development")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "disabled")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.delenv("SMARTPLOY_OPERATOR_USER_IDS", raising=False)
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    service = SmartployService()
    api = TestClient(create_app(service))
    assert api.post("/api/v1/sources", json=SOURCE_PAYLOAD).status_code == 200
    assert api.post("/api/v1/jobs/ingest", json=INGEST_PAYLOAD).json()["status"] == "discovered"

    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="authentication cannot be disabled"):
        create_app(SmartployService())


def test_oidc_session_and_cloudflare_assertion_cannot_bypass_allowlist(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", OIDC_ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "smartploy-fixture")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/callback",
    )
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
        "https://smartploy.obumai.com/auth/logged-out",
    )
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    identity = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    operator = AuthenticatedPrincipal(
        issuer=OIDC_ISSUER, subject="operator-oidc", email=EMAIL, auth_source="oidc"
    )
    user = AuthenticatedPrincipal(
        issuer=OIDC_ISSUER, subject="other-oidc", email=EMAIL, auth_source="oidc"
    )
    monkeypatch.setenv("SMARTPLOY_OPERATOR_USER_IDS", stable_user_id(operator.issuer, operator.subject))
    api = TestClient(
        create_app(
            SmartployService(),
            oidc_client=object(),
            session_repository=sessions,
            identity_repository=identity,
        ),
        base_url="https://smartploy.obumai.com",
    )

    def authenticate(principal: AuthenticatedPrincipal) -> None:
        binding = identity.resolve_or_create(principal)
        issued = sessions.create(
            user_id=binding.user_id,
            principal=principal,
            provider_session_id="synthetic-provider-session",
            ttl_seconds=3600,
        )
        api.cookies.set(SESSION_COOKIE_NAME, issued.token)

    authenticate(user)
    assert api.get("/api/v1/session").json()["authenticated"] is True
    forbidden = api.post(
        "/api/v1/sources", json=SOURCE_PAYLOAD,
        headers={
            "X-SmartPloy-Role": "operator",
            "Cf-Access-Jwt-Assertion": "operator",
        },
    )
    assert forbidden.status_code == 403
    authenticate(operator)
    ok = api.post("/api/v1/sources", json=SOURCE_PAYLOAD)
    assert ok.status_code == 200, ok.text

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from smartploy.access import (
    AccessConfigurationError,
    AccessSettings,
    CloudflareAccessVerifier,
)
from smartploy.api import create_app
from smartploy.service import SmartployService


ISSUER = "https://example.cloudflareaccess.com"
AUDIENCE = "smartploy-audience"
OWNER = "owner@example.com"


@pytest.fixture(scope="module")
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def settings():
    return AccessSettings(
        environment="production",
        enabled=True,
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_email=OWNER,
    )


def token(
    private_key,
    *,
    email=OWNER,
    audience=AUDIENCE,
    issuer=ISSUER,
    token_type="app",
    subject="user-subject-123",
):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iat": int((now - timedelta(seconds=1)).timestamp()),
            "iss": issuer,
            "aud": audience,
            "sub": subject,
            "email": email,
            "type": token_type,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "fixture-key"},
    )


def configure_production(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", ISSUER)
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", OWNER)


def verifier(public_key):
    return CloudflareAccessVerifier(
        settings(),
        signing_key_resolver=lambda encoded: public_key,
    )


def test_production_fails_closed_when_access_is_disabled(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.delenv("SMARTPLOY_ACCESS_ISSUER", raising=False)
    monkeypatch.delenv("SMARTPLOY_ACCESS_AUDIENCE", raising=False)
    monkeypatch.delenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", raising=False)

    with pytest.raises(AccessConfigurationError, match="must be true"):
        create_app(SmartployService())


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("SMARTPLOY_ACCESS_ISSUER", "", "ISSUER"),
        ("SMARTPLOY_ACCESS_AUDIENCE", "", "AUDIENCE"),
        ("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "", "ALLOWED_EMAIL"),
    ],
)
def test_production_rejects_incomplete_access_configuration(
    monkeypatch,
    name,
    value,
    message,
):
    configure_production(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(AccessConfigurationError, match=message):
        create_app(SmartployService())


def test_health_is_public_but_api_requires_access(monkeypatch, signing_keys):
    _, public_key = signing_keys
    configure_production(monkeypatch)
    api = TestClient(
        create_app(SmartployService(), access_verifier=verifier(public_key))
    )

    health = api.get("/healthz")
    assert health.status_code == 200
    assert health.json()["access"] == {
        "enabled": True,
        "environment": "production",
        "owner_restricted": True,
    }

    denied = api.get("/api/v1/dashboard")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "access_token_missing"
    assert "Cf-Access-Jwt-Assertion" not in str(denied.json())


def test_valid_owner_token_allows_api_and_session_is_sanitized(
    monkeypatch,
    signing_keys,
):
    private_key, public_key = signing_keys
    configure_production(monkeypatch)
    api = TestClient(
        create_app(SmartployService(), access_verifier=verifier(public_key))
    )
    encoded = token(private_key)

    response = api.get(
        "/api/v1/session",
        headers={"Cf-Access-Jwt-Assertion": encoded},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["email"] == OWNER
    assert body["auth_source"] == "cloudflare_access"
    assert body["user_id"].startswith("usr-")
    assert body["profile_id"].startswith("profile-")
    assert len(body["subject_fingerprint"]) == 16
    serialized = str(body)
    assert encoded not in serialized
    assert "user-subject-123" not in serialized

    dashboard = api.get(
        "/api/v1/dashboard",
        headers={"Cf-Access-Jwt-Assertion": encoded},
    )
    assert dashboard.status_code == 200


@pytest.mark.parametrize(
    ("overrides", "expected_status"),
    [
        ({"email": "other@example.com"}, 403),
        ({"audience": "wrong-audience"}, 401),
        ({"issuer": "https://wrong.cloudflareaccess.com"}, 401),
        ({"token_type": "org"}, 401),
    ],
)
def test_wrong_identity_or_claims_are_denied(
    monkeypatch,
    signing_keys,
    overrides,
    expected_status,
):
    private_key, public_key = signing_keys
    configure_production(monkeypatch)
    api = TestClient(
        create_app(SmartployService(), access_verifier=verifier(public_key))
    )
    encoded = token(private_key, **overrides)

    response = api.get(
        "/api/v1/session",
        headers={"Cf-Access-Jwt-Assertion": encoded},
    )
    assert response.status_code == expected_status


def test_wrong_signing_key_is_denied(monkeypatch, signing_keys):
    private_key, public_key = signing_keys
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    configure_production(monkeypatch)
    api = TestClient(
        create_app(SmartployService(), access_verifier=verifier(public_key))
    )
    encoded = token(other_private_key)

    response = api.get(
        "/api/v1/session",
        headers={"Cf-Access-Jwt-Assertion": encoded},
    )
    assert response.status_code == 401


def test_development_remains_usable_without_access(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "development")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.delenv("SMARTPLOY_ACCESS_ISSUER", raising=False)
    monkeypatch.delenv("SMARTPLOY_ACCESS_AUDIENCE", raising=False)
    monkeypatch.delenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", raising=False)

    api = TestClient(create_app(SmartployService()))
    session = api.get("/api/v1/session")
    assert session.status_code == 200
    assert session.json() == {
        "authenticated": False,
        "email": "",
        "user_id": "",
        "profile_id": "",
        "subject_fingerprint": "",
        "auth_source": "none",
    }

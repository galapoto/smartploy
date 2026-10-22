"""Public health disclosures are bounded and release probes remain compatible.

No real profile, source, credentials or internet endpoints are accessed.
"""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.live_acceptance import validate_origin_health
from smartploy.service import SmartployService


api_module = importlib.import_module("smartploy.api")
PUBLIC_FIELDS = frozenset({
    "ok", "service", "release_revision", "public_origin", "storage",
    "worker", "access", "obumai_configured",
    "external_actions_authorized",
})


def test_public_health_never_evaluates_or_discloses_private_profile_data(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "development")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "disabled")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    service = SmartployService()
    def forbidden_profile_summary():
        raise AssertionError("public health must not read private profile data")
    monkeypatch.setattr(service, "profile_summary", forbidden_profile_summary)
    monkeypatch.setattr(api_module, "_worker_snapshot", lambda: {
        "configured": True,
        "ready": False,
        "count": 7,
        "error": "PRIVATE_WORKER_CONNECTION_SECRET",
        "tasks": [{"metadata": {"token": "PRIVATE-TOKEN"}}],
    })
    health = TestClient(create_app(service)).get("/healthz")

    assert health.status_code == 200
    assert health.json().keys() == PUBLIC_FIELDS
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.json()["worker"] == {"configured": True, "ready": False, "count": 7}
    assert "profile" not in health.json()
    assert "authentication" not in health.json()
    assert "PRIVATE_" not in health.text
    assert "fact" not in health.text.lower()


def test_public_health_strips_storage_exception_and_keeps_readiness(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "development")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "disabled")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    service = SmartployService()
    monkeypatch.setattr(service.repository, "storage_status", lambda: {
        "mode": "postgres", "ready": False,
        "error": "PRIVATE_DATABASE_HOST_AND_PASSWORD",
        "exception": "PRIVATE_STACK_TRACE",
    })
    response = TestClient(create_app(service)).get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["storage"] == {"mode": "postgres", "ready": False}
    assert "PRIVATE_" not in response.text


def test_minimal_health_still_satisfies_owner_restricted_release_evidence(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", "https://example.cloudflareaccess.com")
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-fixture")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "owner@example.invalid")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    api = TestClient(
        create_app(SmartployService(), access_verifier=object()),
        base_url="https://smartploy.obumai.com",
    )
    response = api.get("/healthz")
    assert response.status_code == 200
    assert response.json().keys() == PUBLIC_FIELDS
    validate_origin_health(response.json())
    assert response.json()["storage"]["ready"] is True
    assert response.json()["access"] == {
        "enabled": True,
        "environment": "production",
        "owner_restricted": True,
    }
    assert response.json()["external_actions_authorized"] is False
    assert "profile" not in response.text

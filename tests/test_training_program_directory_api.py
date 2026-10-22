"""The training directory API must not look like an employer vacancy feed."""
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.service import SmartployService


def test_training_directory_returns_honest_read_only_provider_links(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "development")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "disabled")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    app = TestClient(create_app(SmartployService()))
    result = app.get("/api/v1/training-programs")
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "private, no-store"
    response = result.json()
    assert response["count"] == 12
    assert response["job_count_included"] == 0
    assert response["opening_status"] == "check_provider"
    assert response["external_actions_authorized"] is False
    assert all(r["automatic_application_authorized"] is False
               for r in response["programs"])
    assert any(r["provider"] == "Saranen" for r in response["programs"])
    assert any(r["provider"] == "Siemens" for r in response["programs"])
    # Provider directories are not stored in the global live job repository.
    assert app.get("/api/v1/jobs").json()["count"] == 0
    assert "POSTGRES" not in result.text
    assert "subscription_key" not in result.text

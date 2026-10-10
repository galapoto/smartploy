from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.domain import SourcePolicy
from smartploy.service import SmartployService


def client():
    service = SmartployService()
    service.register_source(
        SourcePolicy(
            source_id="manual-import",
            display_name="Manual import",
            source_class="manual",
            allowed_modes=("manual",),
        )
    )
    return TestClient(create_app(service))


def test_health_and_manual_ingest_without_obumai():
    api = client()
    health = api.get("/healthz")
    assert health.status_code == 200
    assert health.json()["obumai_configured"] is False

    response = api.post(
        "/api/v1/jobs/ingest",
        json={
            "observation": {
                "source_id": "manual-import",
                "source_mode": "manual",
                "source_url": "",
                "raw_text": "Example Oy Data Analyst",
                "payload": {
                    "company": "Example Oy",
                    "role_title": "Data Analyst",
                    "description": "Python SQL analytics",
                    "location": "Helsinki",
                },
                "observed_at": "2026-10-10T00:00:00+00:00",
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "discovered"

    listing = api.get("/api/v1/jobs")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1


def test_obumai_request_is_truthfully_unavailable_when_not_configured():
    api = client()
    created = api.post(
        "/api/v1/jobs/ingest",
        json={
            "observation": {
                "source_id": "manual-import",
                "source_mode": "manual",
                "raw_text": "Example Oy Data Analyst",
                "payload": {
                    "company": "Example Oy",
                    "role_title": "Data Analyst",
                    "description": "Python SQL analytics",
                },
                "observed_at": "2026-10-10T00:00:00+00:00",
            }
        },
    ).json()
    key = created["candidate"]["canonical_key"]
    result = api.post(
        f"/api/v1/jobs/{key}/obumai",
        json={"action": "fit_analysis", "candidate_evidence": {}},
    )
    assert result.status_code == 503
    assert "not configured" in result.json()["detail"]

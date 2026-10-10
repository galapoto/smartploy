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
    assert health.json()["profile"]["approved_fact_count"] == 0

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

    ranking = api.get("/api/v1/rankings")
    assert ranking.status_code == 200
    assert ranking.json()["rankings"][0]["status"] == "insufficient_evidence"


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
        json={"action": "fit_analysis"},
    )
    assert result.status_code == 503
    assert "not configured" in result.json()["detail"]


def test_application_summary_and_dashboard_are_read_only_truthful_views():
    api = client()
    summary = api.get("/api/v1/applications/summary")
    assert summary.status_code == 200
    assert summary.json()["total_records"] == 0
    assert summary.json()["actually_submitted"] == 0

    dashboard = api.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["applications"]["actually_submitted"] == 0
    assert body["external_actions_authorized"] is False
    assert body["top_matches"] == []
    assert body["possible_matches"] == []

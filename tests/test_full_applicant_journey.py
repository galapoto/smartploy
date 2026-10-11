"""Single synthetic, owner-reviewed job application journey across actual API routes.

Never contacts an employer, sends a CV to a third party, or fabricates a
verified submission. Distinct from the still-pending live Chrome acceptance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.domain import SourcePolicy
from smartploy.service import SmartployService


LEVER_JOB = "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply"


def test_first_run_general_to_documents_and_observed_receipt_without_submission():
    service = SmartployService()
    service.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    api = TestClient(create_app(service))

    # A real URL SHAPE, but a synthetic posting and candidate. No HTTP request
    # is made to Lever; the application is not submitted as part of this test.
    inserted = api.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "source_url": LEVER_JOB, "raw_text": "Junior Data Analyst, Helsinki",
            "payload": {
                "company": "Example Data Oy", "role_title": "Junior Data Analyst",
                "description": "Seeking Python and SQL analytics experience",
                "location": "Helsinki", "language": "English",
                "application_url": LEVER_JOB,
            },
        }
    })
    assert inserted.status_code == 200, inserted.text
    key = inserted.json()["candidate"]["canonical_key"]

    preferences = api.get("/api/v1/search-preferences").json()
    assert preferences["completed"] is False
    assert api.get("/api/v1/search-results").json()["mode"] == "setup_required"

    # General browsing works BEFORE a personal profile or uploaded CV exists.
    initial = api.put("/api/v1/search-preferences", json={
        "mode": "general", "expected_revision": 0,
    })
    assert initial.status_code == 200, initial.text
    results = api.get("/api/v1/search-results").json()
    assert results["mode"] == "general"
    assert results["all_jobs"][0]["canonical_key"] == key
    assert results["all_jobs"][0]["preference_score"] is None
    assert results["external_actions_authorized"] is False

    # Preparing a real application DOES require user-supplied career facts.
    assert api.post(f"/api/v1/jobs/{key}/application-workspace").status_code == 409
    for kind, value in (
        ("identity", "Demo Candidate"),
        ("email", "demo@example.org"),
        ("skill", "Python"),
    ):
        posted = api.post("/api/v1/profile/facts", json={
            "fact_type": kind, "value": value, "approved": True,
        })
        assert posted.status_code == 201, posted.text

    created = api.post(f"/api/v1/jobs/{key}/application-workspace")
    assert created.status_code == 200, created.text
    draft = created.json()["workspace"]
    wid = draft["workspace_id"]
    assert draft["status"] == "draft"
    assert draft["authority"]["may_submit_to_employer"] is False

    # A real user reviews and edits the documents before export.
    cv = "Demo Candidate\nJunior Data Analyst\nApproved skill: Python"
    letter = (
        "Dear Hiring Team,\n\nI am interested in this junior data analyst position. "
        "I have approved Python skills relevant to your vacancy.\n\n"
        "Kind regards,\nDemo Candidate"
    )
    edited = api.put(f"/api/v1/application-workspaces/{wid}", json={
        "expected_revision": draft["revision"],
        "cv_text": cv, "cover_letter_text": letter,
    })
    assert edited.status_code == 200, edited.text
    saved = edited.json()["workspace"]
    assert saved["revision"] == draft["revision"] + 1
    for part in ("cv", "letter"):
        for ext, magic in (("pdf", b"%PDF-"), ("docx", b"PK")):
            response = api.get(f"/api/v1/application-workspaces/{wid}/download/{part}/{ext}")
            assert response.status_code == 200
            assert response.content.startswith(magic)
            assert response.headers["cache-control"] == "private, no-store"

    # Browser handoff has *separate*, explicit personal-data approval.
    ready = api.get(f"/api/v1/application-workspaces/{wid}/handoff-readiness")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    route = f"/api/v1/application-workspaces/{wid}/browser-packet"
    assert api.post(route, json={
        "expected_revision": saved["revision"],
        "confirm_private_data_transfer": False,
    }).status_code == 422
    packet_response = api.post(route, json={
        "expected_revision": saved["revision"],
        "confirm_private_data_transfer": True,
    })
    assert packet_response.status_code == 200, packet_response.text
    assert packet_response.json()["external_actions_performed"] is False
    packet = packet_response.json()["packet"]
    assert packet["fields"]["email"] == "demo@example.org"
    assert packet["privacy"]["original_cv_included"] is False
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert "Demo Candidate" not in str(packet.get("raw_uploaded_cv", ""))

    # A simulated visible browser receipt is evidence of an observation,
    # never independent confirmation that the employer accepted a submission.
    observed = {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": wid,
        "document_revision": saved["revision"],
        "document_sha256": sha256((cv + "\0" + letter).encode()).hexdigest(),
        "application_url": LEVER_JOB,
        "confirmation_page_url": LEVER_JOB + "?tracking=private",
        "reference": "DEMO-REF-123456",
        "confirmation_page_sha256": "b" * 64,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_visible": True,
    }
    accepted = api.post(f"/api/v1/application-workspaces/{wid}/browser-receipt", json={
        "confirm_user_observed": True, "receipt": observed,
    })
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["receipt"]["status"] == "browser_observed_unverified"
    assert accepted.json()["external_confirmation_verified"] is False
    assert "tracking=private" not in accepted.text

    # A receipt freezes the exact reviewed documents and blocks duplicate
    # browser handoffs, even though it does not claim employer acceptance.
    assert api.put(f"/api/v1/application-workspaces/{wid}", json={
        "expected_revision": saved["revision"],
        "cv_text": "later", "cover_letter_text": "later",
    }).status_code == 409
    assert api.post(route, json={
        "expected_revision": saved["revision"],
        "confirm_private_data_transfer": True,
    }).status_code == 409
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0

    # All synthetic private records can be removed without affecting jobs.
    assert api.delete(f"/api/v1/application-workspaces/{wid}").status_code == 200
    assert api.get(f"/api/v1/application-workspaces/{wid}/browser-receipt").status_code == 404
    assert api.get("/api/v1/search-results").json()["available_count"] == 1

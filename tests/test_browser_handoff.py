"""First-party owner-scoped form handoff packets and outbound action boundaries."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.application_workspace import new_workspace, render_document
from smartploy.browser_handoff import HandoffError, make_browser_packet, review_handoff
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.service import SmartployService


APPLICATION_URL = "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply"


def candidate():
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url=APPLICATION_URL,
            raw_text="Job advert data analyst at Upright in Helsinki",
            payload={
                "role_title": "Junior Data Analyst",
                "company": "Upright Project",
                "description": "Python, SQL, dashboards",
                "application_url": APPLICATION_URL,
                "location": "Helsinki",
            },
            observed_at="2026-10-11T05:01:00+00:00",
        ),
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    )
    assert result.candidate
    return result.candidate


def profile(pid="person-a"):
    return CandidateProfile(pid, (
        ProfileFact("identity", "Test Candidate", "user-entered", approved=True).normalized(),
        ProfileFact("email", "test.candidate@example.com", "user-entered", approved=True).normalized(),
        ProfileFact("phone", "+358 40 1234567", "user-entered", approved=True).normalized(),
        ProfileFact("linkedin", "https://www.linkedin.com/in/test-candidate", "user-entered", approved=True).normalized(),
        ProfileFact("skill", "Python", "user-entered", approved=True).normalized(),
        ProfileFact("experience", "Secret uploaded CV content must never leave", "user-entered", approved=False).normalized(),
    ))


def ready_workspace():
    p = profile()
    item = new_workspace(candidate(), p, source_cv_text="This is an uploaded CV. Private."),
    # Starter letter contains review prompts; simulate an explicit owner edit
    return replace(item[0], cover_letter_text=(
        "Dear Hiring Team,\n\nI am applying for the Junior Data Analyst role. "
        "I have reviewed the letter and want to discuss my approved Python skills.\n\n"
        "Kind regards,\nTest Candidate"
    ))


def test_structured_contact_facts_require_real_email_phone_and_public_links():
    p = profile()
    assert len(p.approved_facts) == 5
    for name, value in [
        ("email", "nobody-at-example"),
        ("email", "candidate@example\\com"),
        ("phone", "012"),
        ("phone", "not a real number"),
        ("linkedin", "http://linkedin.com/in/person"),
        ("linkedin", "https://evil.com/in/person"),
        ("github", "https://127.0.0.1/admin"),
    ]:
        with pytest.raises(ValueError):
            ProfileFact(name, value, "user-entered", approved=True).normalized()


def test_review_ready_packet_is_bounded_and_never_contains_original_cv():
    item = ready_workspace()
    p = profile()
    now = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
    review = review_handoff(item, candidate(), p)
    assert review["ready"] is True
    assert review["files_attached"] is False
    packet = make_browser_packet(item, candidate(), p, now=now)
    assert packet["application_url"] == APPLICATION_URL
    assert packet["schema"] == "smartploy.browser_handoff.v2"
    first_pdf, mime, filename = render_document(item, kind="cv", file_format="pdf")
    second_pdf, _, _ = render_document(item, kind="cv", file_format="pdf")
    assert mime == "application/pdf" and filename.endswith(".pdf")
    assert first_pdf == second_pdf  # export is byte-for-byte deterministic
    assert packet["cv_pdf_sha256"] == sha256(first_pdf).hexdigest()
    assert packet["cv_pdf_size"] == len(first_pdf) and packet["cv_pdf_size"] > 100
    assert packet["revision"] == item.revision
    assert packet["expires_at"] == (now + timedelta(minutes=15)).isoformat()
    assert packet["fields"]["email"] == "test.candidate@example.com"
    assert packet["fields"]["phone"] == "+358 40 1234567"
    assert packet["fields"]["first_name"] == "Test"
    assert packet["fields"]["last_name"] == "Candidate"
    assert "This is an uploaded CV" not in json.dumps(packet)
    assert "Secret uploaded CV" not in json.dumps(packet)
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert "browser_form_fill_allowed_after_user_click" in packet["privacy"]


def test_missing_contact_or_unreviewed_letter_prevents_handoff():
    item = new_workspace(candidate(), profile())
    initial = review_handoff(item, candidate(), profile())
    assert initial["ready"] is False
    assert any("placeholders" in b for b in initial["blockers"])
    with pytest.raises(HandoffError, match="not ready"):
        make_browser_packet(item, candidate(), profile())

    without_email = CandidateProfile("person-a", tuple(
        f for f in profile().facts if f.fact_type != "email"
    ))
    assert not review_handoff(ready_workspace(), candidate(), without_email)["ready"]


def test_changed_job_expired_listing_or_url_mismatch_blocks():
    item = ready_workspace()
    assert not review_handoff(item, replace(candidate(), source_current=False), profile())["ready"]
    bad = replace(item, application_url="https://jobs.lever.co/other-company/somewhere/apply")
    assert not review_handoff(bad, candidate(), profile())["ready"]
    wrong_person = profile("person-b")
    with pytest.raises(HandoffError, match="not owned"):
        review_handoff(item, candidate(), wrong_person)
    http_item = replace(item, application_url="http://jobs.lever.co/private/apply")
    assert not review_handoff(http_item, candidate(), profile())["ready"]


def test_browser_api_requires_explicit_confirmation_and_saved_revision():
    service = SmartployService()
    service.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    client = TestClient(create_app(service))
    created = client.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import",
            "source_mode": "manual",
            "raw_text": "Data analyst in Helsinki",
            "source_url": APPLICATION_URL,
            "payload": {
                "company": "Upright Project",
                "role_title": "Junior Data Analyst",
                "description": "Python and SQL dashboards",
                "application_url": APPLICATION_URL
            }
        }
    })
    assert created.status_code == 200, created.text
    key = created.json()["candidate"]["canonical_key"]
    for fact in profile().approved_facts:
        assert client.post("/api/v1/profile/facts", json={
            "fact_type": fact.fact_type, "value": fact.value, "approved": True,
        }).status_code == 201
    starter = client.post("/api/v1/jobs/" + key + "/application-workspace")
    assert starter.status_code == 200, starter.text
    w = starter.json()["workspace"]
    wid = w["workspace_id"]
    changed = client.put("/api/v1/application-workspaces/" + wid, json={
        "expected_revision": w["revision"],
        "cv_text": "Test Candidate\nPython analyst",
        "cover_letter_text": "Dear Hiring Team,\nI am applying for this role. My approved Python skill is relevant.\n\nKind regards,\nTest Candidate"
    })
    assert changed.status_code == 200, changed.text
    w = changed.json()["workspace"]
    read = client.get("/api/v1/application-workspaces/" + wid + "/handoff-readiness")
    assert read.status_code == 200
    assert read.json()["ready"] is True
    target = "/api/v1/application-workspaces/" + wid + "/browser-packet"
    assert client.post(target, json={
        "expected_revision": w["revision"], "confirm_private_data_transfer": False
    }).status_code == 422
    assert client.post(target, json={
        "expected_revision": w["revision"] - 1, "confirm_private_data_transfer": True
    }).status_code == 409
    reply = client.post(target, json={
        "expected_revision": w["revision"], "confirm_private_data_transfer": True
    })
    assert reply.status_code == 200, reply.text
    assert reply.headers["cache-control"] == "private, no-store"
    assert reply.json()["external_actions_performed"] is False
    assert reply.json()["packet"]["fields"]["email"] == "test.candidate@example.com"
    assert client.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    assert client.delete("/api/v1/application-workspaces/" + wid).status_code == 200
    assert client.post(target, json={
        "expected_revision": w["revision"], "confirm_private_data_transfer": True
    }).status_code == 404


def test_api_missing_contact_remains_blocked():
    service = SmartployService()
    service.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    client = TestClient(create_app(service))
    created = client.post("/api/v1/jobs/ingest", json={
        "observation": {"source_id": "manual-import", "source_mode": "manual",
        "raw_text": "Analyst", "payload": {"company": "Example Oy", "role_title": "Analyst",
            "description": "SQL", "application_url": APPLICATION_URL}}
    })
    key = created.json()["candidate"]["canonical_key"]
    client.post("/api/v1/profile/facts", json={
        "fact_type": "skill", "value": "SQL", "approved": True
    })
    kit = client.post("/api/v1/jobs/" + key + "/application-workspace").json()["workspace"]
    endpoint = "/api/v1/application-workspaces/" + kit["workspace_id"]
    client.put(endpoint, json={
        "expected_revision": 1, "cv_text": "Approved SQL",
        "cover_letter_text": "Dear Hiring Team,\nI am interested in this position and have reviewed this message."
    })
    readiness = client.get(endpoint + "/handoff-readiness").json()
    assert readiness["ready"] is False
    assert any("full-name" in x for x in readiness["blockers"])
    assert any("email" in x for x in readiness["blockers"])
    res = client.post(endpoint + "/browser-packet", json={
        "expected_revision": 2, "confirm_private_data_transfer": True
    })
    assert res.status_code == 409

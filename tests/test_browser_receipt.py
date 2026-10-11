"""Browser-observed employer receipts stay private and never prove submission."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os

from fastapi.testclient import TestClient
import pytest

from smartploy.api import create_app
from smartploy.application_workspace import new_workspace
from smartploy.browser_receipt import ReceiptError, validate_browser_receipt
from smartploy.browser_receipt_storage import (
    MemoryBrowserReceiptRepository, PostgresBrowserReceiptRepository, ReceiptConflict,
)
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


JOB = "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply"
TIME = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)


def job():
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual", source_url=JOB,
            raw_text="Data analyst with SQL Python at Upright",
            observed_at="2026-10-11T07:00:00+00:00",
            payload={
                "company": "Upright Project", "role_title": "Data Analyst",
                "description": "SQL and Python", "application_url": JOB
            },
        ),
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    )
    assert result.candidate
    return result.candidate


def kit(pid="p1"):
    profile = CandidateProfile(pid, (
        ProfileFact("identity", "Test Candidate", "user-entered", approved=True).normalized(),
    ))
    draft = new_workspace(job(), profile)
    return replace(
        draft, cover_letter_text="Dear Hiring Team,\nI am interested in your analyst role. "
        "My relevant experience is documented in my reviewed CV.\nRegards,\nTest Candidate",
    )


def import_value(w, *, time=TIME):
    return {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": w.workspace_id,
        "document_revision": w.revision,
        "document_sha256": sha256((w.cv_text + "\0" + w.cover_letter_text).encode("utf-8")).hexdigest(),
        "application_url": w.application_url,
        "confirmation_page_url": JOB + "?token=should-not-store#private",
        "reference": "RECEIPT-123456",
        "confirmation_page_sha256": "f" * 64,
        "observed_at": time.isoformat(),
        "confirmed_visible": True,
    }


def test_accept_recent_receipt_but_never_mark_verified():
    w = kit()
    evidence = validate_browser_receipt(w, import_value(w), now=TIME + timedelta(minutes=2))
    payload = evidence.to_dict()
    assert payload["status"] == "browser_observed_unverified"
    assert payload["reference"] == "RECEIPT-123456"
    assert payload["confirmation_page_url"] == JOB
    assert "token=" not in payload["confirmation_page_url"]
    assert payload["independently_verified_by_employer"] is False
    assert payload["actually_submitted_count_changed"] is False
    assert len(payload["evidence_digest"]) == 64


@pytest.mark.parametrize("key,value", [
    ("schema", "unsupported"),
    ("workspace_id", "kit-" + "b" * 30),
    ("document_revision", 99),
    ("document_revision", True),
    ("document_sha256", "a" * 64),
    ("application_url", "https://jobs.lever.co/different/employer/apply"),
    ("confirmation_page_url", "https://evil.example.com/confirmation"),
    ("confirmation_page_url", "http://jobs.lever.co/uprightproject/confirmation"),
    ("confirmation_page_url", "https://jobs.lever.co/another-company/confirmation"),
    ("reference", "invalid reference here"),
    ("confirmation_page_sha256", "x"),
    ("confirmed_visible", False),
])
def test_invalid_employer_receipt_refused(key, value):
    w = kit()
    data = import_value(w)
    data[key] = value
    with pytest.raises(ReceiptError):
        validate_browser_receipt(w, data, now=TIME + timedelta(minutes=2))


def test_stale_future_or_untimed_observation_refused():
    w = kit()
    for stamp in [
        TIME - timedelta(hours=2),
        TIME + timedelta(hours=2),
    ]:
        with pytest.raises(ReceiptError):
            validate_browser_receipt(w, import_value(w, time=stamp), now=TIME)
    row = import_value(w)
    row["observed_at"] = "2026-10-11T09:00:00"  # naive timezone
    with pytest.raises(ReceiptError):
        validate_browser_receipt(w, row, now=TIME)


def test_receipt_must_match_owned_saved_revision_and_current_draft():
    w = kit()
    with pytest.raises(ReceiptError):
        validate_browser_receipt(
            replace(w, status="self_reported_applied"), import_value(w), now=TIME
        )
    changed = replace(w, cv_text=w.cv_text + "\nAdded later")
    with pytest.raises(ReceiptError, match="digest"):
        validate_browser_receipt(changed, import_value(w), now=TIME)


def test_memory_receipt_single_record_conflict_and_ownership():
    repo = MemoryBrowserReceiptRepository()
    w = kit("person-a")
    a = validate_browser_receipt(w, import_value(w), now=TIME)
    assert repo.record(a) == a
    assert repo.record(a) == a
    assert repo.get("person-b", w.workspace_id) is None
    alternative = replace(a, reference="RECEIPT-OTHER", digest="a" * 64)
    with pytest.raises(ReceiptConflict):
        repo.record(alternative)
    assert repo.delete("person-b", w.workspace_id) is False
    assert repo.delete("person-a", w.workspace_id) is True


def test_authenticated_api_receipt_does_not_increment_submitted_count(monkeypatch):
    svc = SmartployService()
    svc.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    api = TestClient(create_app(svc))
    created = api.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "source_url": JOB, "raw_text": "Analyst job",
            "payload": {"company": "Upright Project", "role_title": "Analyst",
                        "description": "SQL", "application_url": JOB}
        }
    })
    assert created.status_code == 200
    key = created.json()["candidate"]["canonical_key"]
    assert api.post("/api/v1/profile/facts", json={
        "fact_type": "identity", "value": "Test Candidate", "approved": True
    }).status_code == 201
    starting = api.post("/api/v1/jobs/" + key + "/application-workspace")
    assert starting.status_code == 200
    w = starting.json()["workspace"]
    assert api.get(f"/api/v1/application-workspaces/{w['workspace_id']}/browser-receipt").json()["present"] is False

    stamp = datetime.now(timezone.utc)
    raw = {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": w["workspace_id"],
        "document_revision": w["revision"],
        "document_sha256": sha256((w["cv_text"] + "\0" + w["cover_letter_text"]).encode()).hexdigest(),
        "application_url": w["application_url"],
        "confirmation_page_url": JOB + "?tracking=hidden",
        "reference": "TEST-RECEIPT-5678",
        "confirmation_page_sha256": "c" * 64,
        "observed_at": stamp.isoformat(),
        "confirmed_visible": True,
    }
    endpoint = f"/api/v1/application-workspaces/{w['workspace_id']}/browser-receipt"
    assert api.post(endpoint, json={"confirm_user_observed": False, "receipt": raw}).status_code == 422
    response = api.post(endpoint, json={"confirm_user_observed": True, "receipt": raw})
    assert response.status_code == 200, response.text
    assert response.json()["receipt"]["status"] == "browser_observed_unverified"
    assert response.json()["external_confirmation_verified"] is False
    assert "tracking=hidden" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert api.post(endpoint, json={"confirm_user_observed": True, "receipt": raw}).status_code == 200
    changed = dict(raw, reference="DIFFERENT-REFERENCE")
    assert api.post(endpoint, json={"confirm_user_observed": True, "receipt": changed}).status_code == 409
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    frozen = api.put(f"/api/v1/application-workspaces/{w['workspace_id']}", json={
        "expected_revision": w["revision"],
        "cv_text": "Altered after submission", "cover_letter_text": "Altered text",
    })
    assert frozen.status_code == 409
    assert api.get(
        f"/api/v1/application-workspaces/{w['workspace_id']}/handoff-readiness"
    ).json()["ready"] is False
    assert api.post(
        f"/api/v1/application-workspaces/{w['workspace_id']}/browser-packet",
        json={"expected_revision": w["revision"], "confirm_private_data_transfer": True},
    ).status_code == 409
    assert api.post(
        f"/api/v1/application-workspaces/{w['workspace_id']}/ai-suggestions",
        json={"expected_revision": w["revision"], "acknowledge_local_ai_processing": True},
    ).status_code == 409
    assert api.delete(f"/api/v1/application-workspaces/{w['workspace_id']}").status_code == 200
    assert api.get(endpoint).status_code == 404


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="requires test PostgreSQL")
def test_postgres_ledger_persistence_and_tenant_separation():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    from smartploy.application_workspace_storage import PostgresWorkspaceRepository

    workspaces = PostgresWorkspaceRepository(dsn)
    w = kit("browser-receipt-persist-test")
    workspaces.delete(w.profile_id, w.workspace_id)
    store = PostgresBrowserReceiptRepository(dsn)
    try:
        record, created = workspaces.create_or_get(w)
        assert created is True
        proof = validate_browser_receipt(record, import_value(record), now=TIME)
        saved = store.record(proof)
        assert saved.digest == proof.digest
        assert store.get("some-other-tenant", record.workspace_id) is None
        assert PostgresBrowserReceiptRepository(dsn).get(w.profile_id, w.workspace_id) == saved
        assert store.record(proof) == saved
    finally:
        workspaces.delete(w.profile_id, w.workspace_id)
    assert store.get(w.profile_id, w.workspace_id) is None

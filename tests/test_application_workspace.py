"""First usable, owner-reviewed application document workflows."""
from __future__ import annotations

from io import BytesIO
import os

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from smartploy.api import create_app
from smartploy.application_workspace import (
    WorkspaceError, WorkspaceRevisionConflict, new_workspace, render_document,
)
from smartploy.application_workspace_storage import MemoryWorkspaceRepository, PostgresWorkspaceRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


def example_candidate():
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url="https://careers.example.fi/jobs/analyst",
            raw_text="Data Analyst in Helsinki. Python, SQL and dashboards.",
            payload={
                "company": "Example Oy",
                "role_title": "Junior Data Analyst",
                "description": "Python SQL analytics",
                "application_url": "https://careers.example.fi/jobs/analyst",
                "location": "Helsinki",
            },
            observed_at="2026-10-11T04:00:00+00:00",
        ),
        SourcePolicy(
            "manual-import", "Manual import", "manual", ("manual",),
        ),
    )
    assert result.candidate is not None
    return result.candidate


def example_profile(name="Candidate Example", profile_id="profile-a"):
    return CandidateProfile(
        profile_id=profile_id,
        facts=(
            ProfileFact("identity", name, "user-entered", approved=True).normalized(),
            ProfileFact("skill", "Python", "user-entered", approved=True).normalized(),
            ProfileFact("language", "Finnish", "user-entered", approved=False).normalized(),
        ),
    )


def test_workspace_draft_uses_only_user_facts_and_is_idempotent():
    person = example_profile()
    job = example_candidate()
    kit = new_workspace(job, person)
    again = new_workspace(job, person)
    assert kit.workspace_id == again.workspace_id
    assert kit.company == "Example Oy"
    assert "Candidate Example" in kit.cv_text
    assert "Python" in kit.cv_text
    assert "Finnish" not in kit.cv_text
    assert "[Explain why you are interested" in kit.cover_letter_text
    assert kit.to_dict()["authority"]["may_submit_to_employer"] is False
    assert kit.status == "draft"


def test_original_cv_is_used_verbatim_when_user_uploaded_it():
    cv = "Candidate Example\n\nExperience: Actual internship\nSkills: Python"
    kit = new_workspace(example_candidate(), example_profile(), cv, source_cv_sha256="a" * 64)
    assert kit.cv_text == cv
    assert kit.source_cv_sha256 == "a" * 64
    assert "Actual internship" in kit.cv_text


def test_empty_or_overlong_cv_cannot_be_silently_exported():
    with pytest.raises(WorkspaceError, match="Upload a CV or approve"):
        new_workspace(example_candidate(), CandidateProfile("empty"))
    with pytest.raises(WorkspaceError, match="shorter CV"):
        new_workspace(example_candidate(), example_profile(), "a" * 30001)


def test_memory_isolation_revision_protection_and_no_external_submission():
    repo = MemoryWorkspaceRepository()
    job = example_candidate()
    alice = new_workspace(job, example_profile(profile_id="profile-alice"))
    bob = new_workspace(job, example_profile(profile_id="profile-bob"))
    assert repo.create_or_get(alice)[1] is True
    assert repo.create_or_get(alice)[1] is False
    assert repo.create_or_get(bob)[1] is True
    assert repo.get("profile-bob", alice.workspace_id) is None
    assert len(repo.list("profile-alice")) == 1
    updated = repo.edit("profile-alice", alice.workspace_id, expected_revision=1,
                        cv_text="Candidate Example\nSkills: Python",
                        cover_letter_text="Dear team,\nI am applying to Example Oy.")
    assert updated.revision == 2
    with pytest.raises(WorkspaceRevisionConflict):
        repo.edit("profile-alice", alice.workspace_id, expected_revision=1,
                  cv_text="stale", cover_letter_text="stale")
    applied = repo.report_applied(
        "profile-alice", alice.workspace_id, expected_revision=2, reference="Confirmation seen by user"
    )
    assert applied.status == "self_reported_applied"
    assert applied.to_dict()["authority"]["has_external_submission_proof"] is False
    assert repo.report_applied("profile-alice", alice.workspace_id, expected_revision=2, reference="") == applied
    with pytest.raises(WorkspaceError):
        repo.edit("profile-alice", alice.workspace_id, expected_revision=3,
                  cv_text="later edit", cover_letter_text="later edit")
    assert repo.delete("profile-bob", alice.workspace_id) is False
    assert repo.delete("profile-alice", alice.workspace_id) is True


def test_real_pdf_and_docx_outputs_only_user_reviewed_text():
    kit = new_workspace(example_candidate(), example_profile())
    for kind, marker in (("cv", "Candidate Example"), ("letter", "Junior Data Analyst")):
        pdf, mime, filename = render_document(kit, kind=kind, file_format="pdf")
        assert pdf.startswith(b"%PDF-")
        assert mime == "application/pdf" and filename.endswith(".pdf")
        content = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
        assert marker in content
        assert "Finnish" not in content  # unapproved language must never be fabricated
        assert b"/JavaScript" not in pdf
        docx, docx_mime, name = render_document(kit, kind=kind, file_format="docx")
        assert docx.startswith(b"PK")
        assert "wordprocessingml" in docx_mime
        assert name.endswith(".docx")
        paragraphs = "\n".join(p.text for p in Document(BytesIO(docx)).paragraphs)
        assert marker in paragraphs
        assert "Finnish" not in paragraphs
    with pytest.raises(WorkspaceError):
        render_document(kit, kind="unknown", file_format="pdf")


def test_api_application_documents_review_and_download_does_not_fake_submission():
    service = SmartployService()
    service.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    api = TestClient(create_app(service))
    record = api.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "raw_text": "Python, SQL and dashboards",
            "payload": {
                "company": "Example Oy", "role_title": "Data Analyst",
                "description": "Python and SQL",
            },
        }
    }).json()
    key = record["candidate"]["canonical_key"]
    not_ready = api.post(f"/api/v1/jobs/{key}/application-workspace")
    assert not_ready.status_code == 409
    assert api.post("/api/v1/profile/facts", json={
        "fact_type": "skill", "value": "SQL", "approved": True
    }).status_code == 201
    created = api.post(f"/api/v1/jobs/{key}/application-workspace")
    assert created.status_code == 200, created.text
    assert created.json()["created"] is True
    kit = created.json()["workspace"]
    kid = kit["workspace_id"]
    assert api.post(f"/api/v1/jobs/{key}/application-workspace").json()["created"] is False

    listing = api.get("/api/v1/application-workspaces")
    assert listing.json()["count"] == 1
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    assert api.post(f"/api/v1/application-workspaces/{kid}/report-applied", json={
        "confirmed_external_application": False, "expected_revision": 1
    }).status_code == 422
    changed = api.put(f"/api/v1/application-workspaces/{kid}", json={
        "expected_revision": 1, "cv_text": "Approved SQL and data analytics",
        "cover_letter_text": "I have SQL skills and want to join your team."
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["workspace"]["revision"] == 2
    assert api.put(f"/api/v1/application-workspaces/{kid}", json={
        "expected_revision": 1, "cv_text": "old", "cover_letter_text": "old"
    }).status_code == 409
    for kind in ("cv", "letter"):
        for fmt in ("docx", "pdf"):
            download = api.get(f"/api/v1/application-workspaces/{kid}/download/{kind}/{fmt}")
            assert download.status_code == 200, download.text
            assert download.headers["cache-control"] == "private, no-store"
            assert download.headers["x-content-type-options"] == "nosniff"
            assert download.headers["content-disposition"].startswith("attachment;")
            assert len(download.content) > 200
    applied = api.post(f"/api/v1/application-workspaces/{kid}/report-applied", json={
        "confirmed_external_application": True, "expected_revision": 2,
        "reference": "Applicant-entered reference"
    })
    assert applied.status_code == 200
    assert applied.json()["workspace"]["status"] == "self_reported_applied"
    assert applied.json()["external_confirmation_verified"] is False
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    assert api.delete(f"/api/v1/application-workspaces/{kid}").status_code == 200
    assert api.get(f"/api/v1/application-workspaces/{kid}").status_code == 404


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="requires PostgreSQL integration database")
def test_postgres_application_workspaces_persist_and_are_tenant_scoped():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    repo = PostgresWorkspaceRepository(dsn)
    job = example_candidate()
    one = new_workspace(job, example_profile(profile_id="test-application-user-a"))
    two = new_workspace(job, example_profile(profile_id="test-application-user-b"))
    repo.delete(one.profile_id, one.workspace_id)
    repo.delete(two.profile_id, two.workspace_id)
    try:
        assert repo.create_or_get(one)[1] is True
        assert repo.create_or_get(two)[1] is True
        assert repo.get("test-application-user-b", one.workspace_id) is None
        assert repo.get("test-application-user-a", one.workspace_id) is not None
        result = repo.edit(one.profile_id, one.workspace_id, expected_revision=1,
                           cv_text="Approved name and Python skill",
                           cover_letter_text="I am applying to Example Oy.")
        assert result.revision == 2
        assert PostgresWorkspaceRepository(dsn).get(one.profile_id, one.workspace_id).cv_text.startswith("Approved")
        with pytest.raises(WorkspaceRevisionConflict):
            repo.edit(one.profile_id, one.workspace_id, expected_revision=1,
                      cv_text="old", cover_letter_text="old")
        assert repo.report_applied(one.profile_id, one.workspace_id,
                                   expected_revision=2, reference="User claims applied").status == "self_reported_applied"
    finally:
        repo.delete(one.profile_id, one.workspace_id)
        repo.delete(two.profile_id, two.workspace_id)

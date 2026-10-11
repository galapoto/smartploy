"""Private CV import, tenant isolation and explicit career-evidence approvals."""
from __future__ import annotations

import base64
from io import BytesIO
import os
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.cv_import import CVImportError, parse_cv
from smartploy.cv_storage import MemoryCVRepository, PostgresCVRepository
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


def docx(text: str = "I am a data analyst with Python and Finnish experience.") -> bytes:
    data = BytesIO()
    with ZipFile(data, "w") as zip_file:
        zip_file.writestr("[Content_Types].xml", "<Types />")
        zip_file.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>',
        )
    return data.getvalue()


def payload(data: bytes, filename: str = "My CV.docx") -> dict:
    return {"filename": filename, "content_base64": base64.b64encode(data).decode("ascii")}


def test_text_only_cv_upload_is_private_and_deletable():
    app = TestClient(create_app(SmartployService()))
    assert app.get("/api/v1/profile/cv").json() == {"present": False}
    content = docx()
    uploaded = app.post("/api/v1/profile/cv", json=payload(content))
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["present"] is True
    assert uploaded.json()["filename"] == "My CV.docx"
    assert "Python" in uploaded.json()["text_preview"]
    downloaded = app.get("/api/v1/profile/cv/download")
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in downloaded.headers["content-disposition"]
    assert app.get("/api/v1/profile/status").json()["approved_fact_count"] == 0
    assert app.delete("/api/v1/profile/cv").json() == {"deleted": True}
    assert app.get("/api/v1/profile/cv").json()["present"] is False


def test_cv_rejects_untrusted_data_and_zip_bombs():
    with pytest.raises(CVImportError):
        parse_cv("../outside.docx", payload(docx())["content_base64"])
    with pytest.raises(CVImportError):
        parse_cv("malware.docx", base64.b64encode(b"not zip").decode())
    with pytest.raises(CVImportError):
        parse_cv("fake.pdf", payload(docx())["content_base64"])
    with pytest.raises(CVImportError):
        parse_cv("big.docx", "x" * 7_000_001)
    bad = BytesIO()
    with ZipFile(bad, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "a" * (5 * 1024 * 1024 + 1))
    with pytest.raises(CVImportError):
        parse_cv("too-large.docx", base64.b64encode(bad.getvalue()).decode())


def test_profile_fact_approval_requires_user_action():
    api = TestClient(create_app(SmartployService()))
    created = api.post("/api/v1/profile/facts", json={"fact_type": "skill", "value": "Python"})
    assert created.status_code == 201
    key = created.json()["fact"]["fact_id"]
    assert created.json()["fact"]["approved"] is False
    assert api.get("/api/v1/profile/status").json()["approved_fact_count"] == 0
    approved = api.patch("/api/v1/profile/facts/" + key, json={"approved": True})
    assert approved.status_code == 200
    assert approved.json()["fact"]["approved"] is True
    assert api.get("/api/v1/profile/status").json()["approved_fact_count"] == 1
    removed = api.delete("/api/v1/profile/facts/" + key)
    assert removed.json() == {"deleted": True}
    assert api.get("/api/v1/profile/facts").json()["count"] == 0


def test_memory_cv_repository_cannot_mix_profiles():
    repository = MemoryCVRepository()
    source = docx()
    repository.put("profile-a", "a.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", source, "Person A experience")
    assert repository.get("profile-b") is None
    assert repository.delete("profile-b") is False
    assert repository.get("profile-a").text == "Person A experience"


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="requires PostgreSQL")
def test_postgres_cv_repository_enforces_profile_isolation():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    repository = PostgresCVRepository(dsn)
    data = docx()
    repository.put("cv-test-profile-a", "cv.docx",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                   data, "Person A CV data")
    try:
        assert repository.get("cv-test-profile-b") is None
        assert repository.delete("cv-test-profile-b") is False
        assert repository.get("cv-test-profile-a").content == data
    finally:
        repository.delete("cv-test-profile-a")

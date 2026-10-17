"""Private saved-job API and storage isolation.

Synthetic account principals use the same email and distinct stable subjects.
They are not proof of two real production logins or the Cloudflare edge.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.private_saved_jobs import (
    MemoryPrivateSavedJobRepository,
    PostgresPrivateSavedJobRepository,
    PrivateSavedJobError,
)
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


DATA = {
    "company": "Example Oy",
    "role_title": "Junior Data Analyst",
    "location": "Helsinki",
    "description": "Fictional Python and SQL job description.",
    "application_url": "https://jobs.example.invalid/analyst",
}


class SyntheticSameEmailVerifier:
    def verify(self, token: str) -> AccessPrincipal:
        if token not in {"account-a", "account-b"}:
            raise ValueError("Only approved synthetic principals")
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer="https://example.cloudflareaccess.com",
            subject="subject-" + token,
            audience="smartploy-fixture",
            email="same@example.invalid",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            key_id="synthetic",
        )


def private_api(monkeypatch) -> TestClient:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv(
        "SMARTPLOY_ACCESS_ISSUER", "https://example.cloudflareaccess.com"
    )
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-fixture")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "same@example.invalid")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    return TestClient(
        create_app(
            SmartployService(),
            access_verifier=SyntheticSameEmailVerifier(),
        )
    )


def headers(account: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": account}


def test_private_jobs_have_no_shared_ats_or_personalized_search_side_effect(monkeypatch):
    api = private_api(monkeypatch)
    a = headers("account-a")
    b = headers("account-b")

    assert api.get("/api/v1/private-jobs").status_code == 401
    assert api.post("/api/v1/private-jobs", json=DATA).status_code == 401
    assert api.delete("/api/v1/private-jobs/anything").status_code == 401

    created = api.post("/api/v1/private-jobs", headers=a, json=DATA)
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "private, no-store"
    item = created.json()["job"]
    assert created.json()["status"] == "saved_private"
    assert item["private"] is True
    assert item["external_actions_authorized"] is False
    assert item["employer_availability_verified"] is False
    assert item["role_title"] == "Junior Data Analyst"

    own = api.get("/api/v1/private-jobs", headers=a)
    assert own.status_code == 200
    assert own.headers["cache-control"] == "private, no-store"
    assert own.json()["count"] == 1
    assert own.json()["jobs"][0]["saved_job_id"] == item["saved_job_id"]

    others = api.get("/api/v1/private-jobs", headers=b)
    assert others.status_code == 200
    assert others.json()["jobs"] == []
    denied_delete = api.delete(
        "/api/v1/private-jobs/" + item["saved_job_id"], headers=b
    )
    assert denied_delete.status_code == 404

    # User-saved records never pollute the shared ATS catalog, job counts,
    # source policy or another person's search results.
    assert api.get("/api/v1/jobs", headers=a).json()["count"] == 0
    assert api.get("/api/v1/jobs", headers=b).json()["count"] == 0
    assert api.get("/api/v1/search-results", headers=b).json()["available_count"] == 0
    assert api.get("/api/v1/search-results", headers=a).json()["available_count"] == 0

    removed = api.delete(
        "/api/v1/private-jobs/" + item["saved_job_id"], headers=a
    )
    assert removed.status_code == 200
    assert removed.headers["cache-control"] == "private, no-store"
    assert api.get("/api/v1/private-jobs", headers=a).json()["count"] == 0
    assert api.delete(
        "/api/v1/private-jobs/" + item["saved_job_id"], headers=a
    ).status_code == 404


@pytest.mark.parametrize("change", [
    {"company": "  "},
    {"description": ""},
    {"application_url": "javascript:alert(1)"},
    {"application_url": "https://user:password@jobs.example.invalid"},
    {"application_url": "http://jobs.example.invalid:wrong/path"},
    {"application_url": "https://jobs.example.invalid/\nmalformed"},
    {"role_title": "X" * 161},
])
def test_private_jobs_validation_prevents_unsafe_or_blank_fields(monkeypatch, change):
    api = private_api(monkeypatch)
    response = api.post(
        "/api/v1/private-jobs", json={**DATA, **change}, headers=headers("account-a")
    )
    assert response.status_code == 422, response.text
    assert api.get(
        "/api/v1/private-jobs", headers=headers("account-a")
    ).json()["count"] == 0


def test_private_jobs_reject_extra_user_supplied_identity_and_invalid_limits(monkeypatch):
    api = private_api(monkeypatch)
    a = headers("account-a")
    assert api.post(
        "/api/v1/private-jobs",
        headers=a,
        json={**DATA, "profile_id": "profile-account-b"},
    ).status_code == 422
    for value in [0, -1, 101]:
        assert api.get(
            f"/api/v1/private-jobs?limit={value}", headers=a
        ).status_code == 422


def test_memory_repository_scopes_list_and_delete_by_owner():
    repo = MemoryPrivateSavedJobRepository()
    one = repo.save("profile-a", DATA)
    assert repo.list("profile-a") == [one]
    assert repo.list("profile-b") == []
    assert repo.delete("profile-b", one.saved_job_id) is False
    assert repo.list("profile-a") == [one]
    assert repo.delete("profile-a", one.saved_job_id) is True
    with pytest.raises(PrivateSavedJobError, match="identity"):
        repo.save("", DATA)


def test_postgres_private_jobs_survive_reinstantiation_and_isolate_profiles():
    dsn = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("Requires SMARTPLOY_TEST_DATABASE_URL")
    PostgresJobRepository(dsn).migrate()
    repo = PostgresPrivateSavedJobRepository(dsn)
    profile_a = "private-job-fixture-" + uuid4().hex
    profile_b = "private-job-fixture-" + uuid4().hex
    created = repo.save(profile_a, DATA)
    try:
        reloaded = PostgresPrivateSavedJobRepository(dsn)
        assert reloaded.list(profile_a) == [created]
        assert reloaded.list(profile_b) == []
        assert reloaded.delete(profile_b, created.saved_job_id) is False
        assert reloaded.list(profile_a) == [created]
    finally:
        repo.delete(profile_a, created.saved_job_id)
    assert repo.list(profile_a) == []

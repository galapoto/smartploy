"""Synthetic regression checks for the bounded ObumAI status-refresh queue.

No job submissions, identity provider, employer actions or network requests.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

from smartploy.domain import canonical_json
from smartploy.obumai import ObumAIError
from smartploy.preparation_storage import MemoryPreparationRepository
from smartploy.preparations import ApplicationPreparation, PREPARATION_CONTRACT
import smartploy.worker_runtime as worker_runtime


def _hash(value: dict) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _package(number: str | int, *, status: str, profile: str = "profile-a",
             remote_id: str = "remote-fixture", updated: str = "2026-10-17T10:00:00+00:00",
             requested: str = "2026-10-17T09:00:00+00:00") -> ApplicationPreparation:
    job_snapshot = {"job": str(number)}
    evidence_snapshot = {"facts": []}
    return ApplicationPreparation(
        package_id=f"synthetic-package-{number}",
        canonical_key=f"synthetic-job-{number}",
        profile_id=profile,
        preparation_contract=PREPARATION_CONTRACT,
        job_snapshot_sha256=_hash(job_snapshot),
        evidence_sha256=_hash(evidence_snapshot),
        job_snapshot=job_snapshot,
        evidence_snapshot=evidence_snapshot,
        score_snapshot={},
        status=status,
        obum_job_id=remote_id,
        requested_at=requested,
        updated_at=updated,
    )


def test_refresh_candidates_filter_before_limit_and_rotate_after_update():
    repo = MemoryPreparationRepository()
    for index in range(75):
        repo.create_or_get(_package(index, status="completed"))
    old = _package("old", status="queued", updated="2026-10-14T10:00:00+00:00",
                   requested="2026-10-14T09:00:00+00:00")
    next_job = _package("next", status="blocked", updated="2026-10-15T10:00:00+00:00",
                        requested="2026-10-15T09:00:00+00:00")
    no_remote_id = _package("missing-id", status="running", remote_id="",
                            updated="2026-10-13T10:00:00+00:00",
                            requested="2026-10-13T09:00:00+00:00")
    for item in (old, next_job, no_remote_id):
        repo.create_or_get(item)

    assert all(item.status == "completed" for item in repo.list(limit=10))
    assert [item.package_id for item in repo.list_refresh_candidates(limit=1)] == [
        old.package_id
    ]
    assert [item.package_id for item in repo.list_refresh_candidates(limit=2)] == [
        old.package_id, next_job.package_id
    ]

    repo.save(replace(old, status="running", updated_at="2026-10-17T12:00:00+00:00"))
    assert [item.package_id for item in repo.list_refresh_candidates(limit=2)] == [
        next_job.package_id, old.package_id
    ]


def test_transient_lookup_failure_rotates_even_if_remote_state_does_not_change():
    repo = MemoryPreparationRepository()
    first = _package("failed-first", status="queued",
                     updated="2026-10-14T10:00:00+00:00")
    second = _package("failed-second", status="running",
                      updated="2026-10-15T10:00:00+00:00")
    repo.create_or_get(first)
    repo.create_or_get(second)
    assert repo.list_refresh_candidates(limit=1)[0].package_id == first.package_id
    assert repo.defer_failed_refresh(first.package_id, "wrong-remote") is False
    assert repo.list_refresh_candidates(limit=1)[0].package_id == first.package_id

    assert repo.defer_failed_refresh(first.package_id, first.obum_job_id)
    assert repo.list_refresh_candidates(limit=1)[0].package_id == second.package_id
    assert repo.get(first.package_id).status == "queued"
    assert repo.defer_failed_refresh(second.package_id, second.obum_job_id)
    assert repo.list_refresh_candidates(limit=1)[0].package_id == first.package_id
    assert repo.get(second.package_id).status == "running"


def test_refresh_candidates_respect_profile_scope():
    repo = MemoryPreparationRepository(profile_id="profile-a")
    current = _package("owner", status="queued")
    repo.create_or_get(current)
    assert [item.package_id for item in repo.list_refresh_candidates()] == [
        current.package_id
    ]
    import pytest
    with pytest.raises(ValueError, match="different profile"):
        repo.create_or_get(_package("other", status="queued", profile="profile-b"))


def test_worker_refresh_reads_only_refresh_candidates_and_continues_after_errors(monkeypatch):
    for key in (
        "KUNTAREKRY_FEED_URL", "JOBMARKET_FINLAND_API_ENABLED",
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE",
        "SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_WORKER_REFRESH_CADENCE_SECONDS", "60")
    seen: list[str] = []
    deferred: list[tuple[str, str]] = []

    class FakeRepository:
        def __init__(self, dsn: str, profile_id: str = ""):
            assert dsn == "postgresql://synthetic"
            self.profile_id = profile_id

        def list(self, *, limit: int):
            raise AssertionError("Worker must not scan newest completed history")

        def list_refresh_candidates(self, *, limit: int):
            assert limit == 50
            return [
                SimpleNamespace(package_id="stale-removed", status="queued",
                                profile_id="profile-a", obum_job_id="remote-old"),
                SimpleNamespace(package_id="bad-remote", status="running",
                                profile_id="profile-b", obum_job_id="remote-failed"),
                SimpleNamespace(package_id="valid-remote", status="blocked",
                                profile_id="profile-c", obum_job_id="remote-live"),
            ]

        def defer_failed_refresh(self, package_id: str, obum_job_id: str):
            deferred.append((package_id, obum_job_id))
            return True

    class FakeService:
        def __init__(self, dsn: str, profile_id: str):
            self.profile_id = profile_id
            self.preparation_repository = FakeRepository(dsn, profile_id=profile_id)

        def refresh_preparation(self, package_id: str):
            expected = {
                "stale-removed": "profile-a",
                "bad-remote": "profile-b",
                "valid-remote": "profile-c",
            }
            assert self.profile_id == expected[package_id]
            seen.append(package_id)
            if package_id == "stale-removed":
                raise KeyError(package_id)
            if package_id == "bad-remote":
                raise ObumAIError("Synthetic remote unavailable")
            return SimpleNamespace(status="running")

    monkeypatch.setattr(worker_runtime, "PostgresPreparationRepository", FakeRepository)
    monkeypatch.setattr(
        worker_runtime, "_scoped_application_service",
        lambda dsn, client, profile_id: FakeService(dsn, profile_id),
    )
    specs = worker_runtime.build_worker_task_specs("postgresql://synthetic")
    assert [spec.task_id for spec in specs] == ["application:refresh-preparations"]
    result = specs[0].runner()
    assert seen == ["stale-removed", "bad-remote", "valid-remote"]
    assert result.status == "degraded"
    assert result.details["updated_count"] == 1
    assert result.details["failure_count"] == 2
    assert deferred == [
        ("stale-removed", "remote-old"),
        ("bad-remote", "remote-failed"),
    ]
    assert result.details["external_actions_authorized"] is False

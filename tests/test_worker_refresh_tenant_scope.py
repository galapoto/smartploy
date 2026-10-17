"""Background status refresh must never write an unrelated user's application.

All remote IDs and accounts in these tests are synthetic; HTTP is mocked.
"""
from types import SimpleNamespace
import pytest

import smartploy.worker_runtime as runtime
from smartploy.obumai import ObumAIError


def _refresh(monkeypatch, *, failure=False):
    for key in (
        "KUNTAREKRY_FEED_URL", "JOBMARKET_FINLAND_API_ENABLED",
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE",
        "SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_PROFILE_ID", "legacy-unrelated-default")
    fixtures = (
        SimpleNamespace(
            package_id="package-a", profile_id="profile-account-a",
            obum_job_id="remote-a", status="running",
        ),
        SimpleNamespace(
            package_id="package-b", profile_id="profile-account-b",
            obum_job_id="remote-b", status="queued",
        ),
    )
    calls = []
    clients = []
    repository_instances = []

    class FakeClient:
        def __init__(self, settings):
            self.closed = False
            clients.append(self)

        def close(self):
            self.closed = True

    class Scoped:
        def __init__(self, dsn, profile_id=""):
            self.profile_id = profile_id
            repository_instances.append((type(self).__name__, profile_id))

        def list_refresh_candidates(self, *, limit):
            assert not self.profile_id
            assert limit == 50
            return fixtures

        def defer_failed_refresh(self, package_id, job_id):
            calls.append(("defer", self.profile_id, package_id, job_id))
            assert self.profile_id == "profile-account-a"

    class Prep(Scoped):
        pass
    class Application(Scoped):
        pass
    class Profile(Scoped):
        pass

    class FakeService:
        def __init__(self, *, repository, profile_repository,
                     preparation_repository, application_repository, obumai):
            scope = preparation_repository.profile_id
            assert scope == profile_repository.profile_id == application_repository.profile_id
            assert scope != "legacy-unrelated-default"
            assert obumai in clients
            self.scope = scope
            self.preparation_repository = preparation_repository

        def refresh_preparation(self, package_id):
            expected = "profile-account-a" if package_id == "package-a" else "profile-account-b"
            assert self.scope == expected
            calls.append(("refresh", self.scope, package_id))
            if failure and package_id == "package-a":
                raise ObumAIError("synthetic temporary remote error")
            return SimpleNamespace(status="running" if package_id == "package-a" else "completed")

    monkeypatch.setattr(runtime, "ObumAIClient", FakeClient)
    monkeypatch.setattr(runtime, "SmartployService", FakeService)
    monkeypatch.setattr(runtime, "PostgresPreparationRepository", Prep)
    monkeypatch.setattr(runtime, "PostgresApplicationRepository", Application)
    monkeypatch.setattr(runtime, "PostgresProfileRepository", Profile)
    monkeypatch.setattr(runtime, "PostgresJobRepository", lambda dsn: SimpleNamespace())
    specs = runtime.build_worker_task_specs("postgresql://fixture")
    assert {s.task_id for s in specs} == {"application:refresh-preparations"}
    return next(x for x in specs if x.task_id == "application:refresh-preparations"), calls, clients, repository_instances


def test_refresh_scopes_both_account_repositories_without_legacy_profile(monkeypatch):
    worker, calls, clients, repos = _refresh(monkeypatch)
    result = worker.runner()
    assert result.status == "healthy"
    assert result.details["updated_count"] == 2
    assert result.details["failure_count"] == 0
    assert calls == [
        ("refresh", "profile-account-a", "package-a"),
        ("refresh", "profile-account-b", "package-b"),
    ]
    assert all(scope != "legacy-unrelated-default" for name, scope in repos)
    assert len(clients) == 1 and clients[0].closed is True


def test_one_failed_refresh_defers_only_own_profile_and_continues(monkeypatch):
    worker, calls, clients, _ = _refresh(monkeypatch, failure=True)
    result = worker.runner()
    assert result.status == "degraded"
    assert result.details["failure_count"] == 1
    assert result.details["updated_count"] == 1
    assert calls == [
        ("refresh", "profile-account-a", "package-a"),
        ("defer", "profile-account-a", "package-a", "remote-a"),
        ("refresh", "profile-account-b", "package-b"),
    ]
    assert clients[0].closed is True


def test_missing_owner_fails_closed_and_still_closes_client(monkeypatch):
    worker, calls, clients, _ = _refresh(monkeypatch)
    class Orphan:
        def __init__(self, dsn, profile_id=""):
            self.profile_id = profile_id
        def list_refresh_candidates(self, *, limit):
            return [SimpleNamespace(
                package_id="orphan", obum_job_id="remote",
                profile_id="", status="running",
            )]
    monkeypatch.setattr(runtime, "PostgresPreparationRepository", Orphan)
    with pytest.raises(ValueError, match="explicit preparation owner"):
        worker.runner()
    assert calls == []
    assert clients[0].closed is True

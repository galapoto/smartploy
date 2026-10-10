"""Regression coverage for the SmartPloy worker's dedicated Docker healthcheck."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from smartploy import worker_health
from smartploy.storage import PostgresJobRepository


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/personal/docker-compose.yml"
SCRIPTS = ROOT / "deploy/personal/scripts"


class _Cursor:
    def __init__(self, exists: bool):
        self.exists = exists
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql):
        self.statement = sql

    def fetchone(self):
        return (self.exists,)


class _Connection:
    def __init__(self, exists: bool):
        self.cursor_value = _Cursor(exists)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return self.cursor_value


def test_worker_probe_requires_scheduling_schema_and_bounded_connection(monkeypatch):
    observed = {}

    def fake_connect(dsn, *, connect_timeout):
        observed.update(dsn=dsn, connect_timeout=connect_timeout)
        return _Connection(True)

    monkeypatch.setattr(worker_health, "connect", fake_connect)
    assert worker_health.worker_storage_ready("postgresql://example") is True
    assert observed == {"dsn": "postgresql://example", "connect_timeout": 3}


def test_worker_probe_rejects_missing_or_unmigrated_database(monkeypatch):
    assert worker_health.worker_storage_ready("") is False
    monkeypatch.setattr(worker_health, "connect", lambda *args, **kwargs: _Connection(False))
    assert worker_health.worker_storage_ready("postgresql://example") is False


def test_worker_health_failure_never_echoes_database_credentials(monkeypatch, capsys):
    password = "should-not-appear-in-docker-health-logs"

    def failed_connection(*args, **kwargs):
        raise RuntimeError(password)

    monkeypatch.setattr(worker_health, "connect", failed_connection)
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", "postgresql://user:" + password + "@db/test")
    assert worker_health.main() == 1
    output = capsys.readouterr()
    combined = output.out + output.err
    assert password not in combined


def test_health_command_success_is_silent(monkeypatch, capsys):
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", "postgresql://placeholder")
    monkeypatch.setattr(worker_health, "worker_storage_ready", lambda dsn: True)
    assert worker_health.main() == 0
    assert not capsys.readouterr().out


def test_worker_owns_its_healthcheck_not_api_image_http_probe():
    source = COMPOSE.read_text(encoding="utf-8")
    worker = source.split("\n  worker:\n", 1)[1].split("\n  web:\n", 1)[0]
    assert "scripts/source_worker.py" in worker
    assert "smartploy.worker_health" in worker
    assert "healthcheck:" in worker
    assert "127.0.0.1:8090/healthz" not in worker
    assert "127.0.0.1:" not in worker
    assert "ports:" not in worker
    api = source.split("\n  api:\n", 1)[1].split("\n  worker:\n", 1)[0]
    assert "127.0.0.1:8090/healthz" in api


def test_deploy_restore_release_gates_check_all_container_health():
    gate = (SCRIPTS / "assert-healthy-stack.sh").read_text(encoding="utf-8")
    for service in ("postgres", "api", "worker", "web"):
        assert service in gate
    assert "docker inspect --format" in gate
    assert ".State.Running" in gate
    assert ".State.Health.Status" in gate
    assert "docker compose down" not in gate
    assert "docker compose up" not in gate

    for filename in ("deploy.sh", "restore.sh", "release-evidence.sh"):
        script = (SCRIPTS / filename).read_text(encoding="utf-8")
        assert 'bash "${SCRIPT_DIR}/assert-healthy-stack.sh"' in script

    release = (SCRIPTS / "release-evidence.sh").read_text(encoding="utf-8")
    assert "stack_healthy=true" in release


@pytest.mark.skipif(
    not os.getenv("SMARTPLOY_TEST_DATABASE_URL"),
    reason="requires PostgreSQL integration test connection",
)
def test_worker_probe_accepts_real_migrated_database():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    assert worker_health.worker_storage_ready(dsn) is True

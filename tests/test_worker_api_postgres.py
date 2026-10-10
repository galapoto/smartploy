import json
import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from psycopg import connect

from smartploy.api import create_app
from smartploy.storage import PostgresJobRepository
from smartploy.worker_schedule import (
    PostgresWorkerTaskRepository,
    WorkerTaskResult,
    WorkerTaskSpec,
)


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def scheduler(monkeypatch):
    PostgresJobRepository(DSN).migrate()
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE smartploy_worker_tasks")
        conn.commit()
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", DSN)
    return PostgresWorkerTaskRepository(DSN)


def test_worker_api_projects_running_task_without_lease_owner(scheduler):
    now = datetime.now(timezone.utc)
    scheduler.register(
        WorkerTaskSpec(
            task_id="source:fixture",
            task_kind="source",
            cadence_seconds=300,
            runner=lambda: WorkerTaskResult("healthy"),
            metadata={
                "provider": "fixture",
                "tenant": "example",
                "api_key": "must-not-leak",
                "nested": {"authorization": "must-not-leak-either", "safe": "yes"},
            },
        ),
        now=now,
    )
    scheduler.claim_due(
        owner="internal-hostname:1234",
        lease_seconds=900,
        limit=1,
        now=now,
    )

    api = TestClient(create_app())
    response = api.get("/api/v1/worker/tasks")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["ready"] is True
    assert body["count"] == 1

    task = body["tasks"][0]
    assert task["task_id"] == "source:fixture"
    assert task["lease_active"] is True
    assert task["lease_until"]
    assert task["metadata"]["provider"] == "fixture"
    assert task["metadata"]["nested"]["safe"] == "yes"
    serialized = json.dumps(body)
    assert "lease_owner" not in serialized
    assert "internal-hostname" not in serialized
    assert "must-not-leak" not in serialized
    assert "authorization" not in serialized
    assert "api_key" not in serialized

    dashboard = api.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["worker"]["tasks"][0]["lease_active"] is True

    health = api.get("/healthz")
    assert health.status_code == 200
    assert health.json()["worker"] == {
        "configured": True,
        "ready": True,
        "count": 1,
        "error": "",
    }

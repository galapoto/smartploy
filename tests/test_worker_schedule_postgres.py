import os
from datetime import datetime, timedelta, timezone

import pytest
from psycopg import connect

from smartploy.storage import PostgresJobRepository
from smartploy.worker_schedule import (
    ContinuousWorker,
    PostgresWorkerTaskRepository,
    WorkerTaskResult,
    WorkerTaskSpec,
)


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def repository():
    PostgresJobRepository(DSN).migrate()
    repo = PostgresWorkerTaskRepository(DSN)
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE smartploy_worker_tasks")
        conn.commit()
    return repo


def moment(hour=10, minute=0, second=0):
    return datetime(2026, 10, 10, hour, minute, second, tzinfo=timezone.utc)


def spec(task_id="source:test", cadence=60, runner=None):
    return WorkerTaskSpec(
        task_id=task_id,
        task_kind="source",
        cadence_seconds=cadence,
        runner=runner or (lambda: WorkerTaskResult("healthy", {"ok": True})),
        metadata={"source_id": task_id},
    )


def test_nonexpired_lease_is_exclusive_and_expired_lease_is_reclaimable(repository):
    now = moment()
    repository.register(spec(), now=now)

    first = repository.claim_due(owner="worker-a", lease_seconds=60, limit=1, now=now)
    assert [item.task_id for item in first] == ["source:test"]

    blocked = repository.claim_due(
        owner="worker-b",
        lease_seconds=60,
        limit=1,
        now=now + timedelta(seconds=59),
    )
    assert blocked == []

    reclaimed = repository.claim_due(
        owner="worker-b",
        lease_seconds=60,
        limit=1,
        now=now + timedelta(seconds=61),
    )
    assert [item.task_id for item in reclaimed] == ["source:test"]
    assert reclaimed[0].lease_owner == "worker-b"

    with pytest.raises(RuntimeError, match="not owned"):
        repository.complete(
            "source:test",
            owner="worker-a",
            status="healthy",
            max_backoff_seconds=3600,
            now=now + timedelta(seconds=62),
        )


def test_success_uses_normal_cadence_and_failure_uses_bounded_exponential_backoff(repository):
    now = moment()
    repository.register(spec(cadence=10), now=now)
    repository.claim_due(owner="worker-a", lease_seconds=60, limit=1, now=now)

    success = repository.complete(
        "source:test",
        owner="worker-a",
        status="healthy",
        max_backoff_seconds=25,
        now=now,
    )
    assert success.consecutive_failures == 0
    assert success.next_run_at == now + timedelta(seconds=10)

    repository.claim_due(
        owner="worker-a",
        lease_seconds=60,
        limit=1,
        now=now + timedelta(seconds=10),
    )
    failed_once = repository.complete(
        "source:test",
        owner="worker-a",
        status="failed",
        error="network",
        max_backoff_seconds=25,
        now=now + timedelta(seconds=10),
    )
    assert failed_once.consecutive_failures == 1
    assert failed_once.next_run_at == now + timedelta(seconds=30)

    repository.claim_due(
        owner="worker-a",
        lease_seconds=60,
        limit=1,
        now=now + timedelta(seconds=30),
    )
    failed_twice = repository.complete(
        "source:test",
        owner="worker-a",
        status="failed",
        error="network",
        max_backoff_seconds=25,
        now=now + timedelta(seconds=30),
    )
    assert failed_twice.consecutive_failures == 2
    assert failed_twice.next_run_at == now + timedelta(seconds=55)


def test_disable_absent_tasks_prevents_future_claims(repository):
    now = moment()
    repository.register(spec("source:a"), now=now)
    repository.register(spec("source:b"), now=now)
    assert repository.disable_absent({"source:a"}) == 1

    claimed = repository.claim_due(owner="worker", lease_seconds=60, limit=10, now=now)
    assert [item.task_id for item in claimed] == ["source:a"]
    assert repository.get("source:b").enabled is False


def test_worker_continues_after_one_task_failure(repository):
    now = moment()
    calls = []

    def failing():
        calls.append("fail")
        raise RuntimeError("fixture failure")

    def healthy():
        calls.append("healthy")
        return WorkerTaskResult("healthy", {"count": 1})

    worker = ContinuousWorker(
        repository,
        [
            spec("source:a", runner=failing),
            spec("source:b", runner=healthy),
        ],
        owner="worker-a",
        lease_seconds=60,
        max_backoff_seconds=3600,
        claim_limit=10,
    )
    cycle = worker.run_once(now=now)
    assert cycle.claimed == 2
    assert cycle.completed == 2
    assert cycle.failed == 1
    assert sorted(calls) == ["fail", "healthy"]
    assert repository.get("source:a").last_status == "failed"
    assert repository.get("source:b").last_status == "healthy"


def test_registration_updates_config_without_resetting_existing_next_run(repository):
    now = moment()
    repository.register(spec(cadence=60), now=now)
    repository.claim_due(owner="worker", lease_seconds=60, limit=1, now=now)
    completed = repository.complete(
        "source:test",
        owner="worker",
        status="healthy",
        max_backoff_seconds=3600,
        now=now,
    )
    assert completed.next_run_at == now + timedelta(seconds=60)

    updated_spec = WorkerTaskSpec(
        task_id="source:test",
        task_kind="source",
        cadence_seconds=120,
        runner=lambda: WorkerTaskResult("healthy"),
        metadata={"source_id": "source:test", "version": 2},
    )
    updated = repository.register(updated_spec, now=now + timedelta(seconds=5))
    assert updated.cadence_seconds == 120
    assert updated.next_run_at == now + timedelta(seconds=60)

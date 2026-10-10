"""Persistent Smartploy worker scheduling and PostgreSQL leases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb


VALID_RESULTS = {"healthy", "degraded", "failed"}


def utc_datetime() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _aware(value: datetime | None) -> datetime:
    item = value or utc_datetime()
    if item.tzinfo is None:
        item = item.replace(tzinfo=timezone.utc)
    return item.astimezone(timezone.utc).replace(microsecond=0)


@dataclass(frozen=True)
class WorkerTask:
    task_id: str
    task_kind: str
    enabled: bool
    cadence_seconds: int
    next_run_at: datetime
    lease_owner: str = ""
    lease_until: datetime | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_status: str = "never"
    consecutive_failures: int = 0
    last_error: str = ""
    metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime | None) -> str:
            return value.isoformat() if value else ""

        return {
            "task_id": self.task_id,
            "task_kind": self.task_kind,
            "enabled": self.enabled,
            "cadence_seconds": self.cadence_seconds,
            "next_run_at": iso(self.next_run_at),
            "lease_owner": self.lease_owner,
            "lease_until": iso(self.lease_until),
            "last_started_at": iso(self.last_started_at),
            "last_completed_at": iso(self.last_completed_at),
            "last_status": self.last_status,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class WorkerTaskResult:
    status: str
    details: Mapping[str, Any] | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if self.status not in VALID_RESULTS:
            raise ValueError("worker task result must be healthy, degraded or failed")


TaskRunner = Callable[[], WorkerTaskResult]


@dataclass(frozen=True)
class WorkerTaskSpec:
    task_id: str
    task_kind: str
    cadence_seconds: int
    runner: TaskRunner
    metadata: Mapping[str, Any] | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        task_id = str(self.task_id or "").strip()
        task_kind = str(self.task_kind or "").strip()
        if not task_id or len(task_id) > 200:
            raise ValueError("worker task_id is required and must be <= 200 characters")
        if not task_kind or len(task_kind) > 100:
            raise ValueError("worker task_kind is required and must be <= 100 characters")
        if int(self.cadence_seconds) <= 0:
            raise ValueError("worker cadence must be positive")


@dataclass(frozen=True)
class WorkerCycle:
    claimed: int
    completed: int
    failed: int
    tasks: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claimed": self.claimed,
            "completed": self.completed,
            "failed": self.failed,
            "tasks": list(self.tasks),
        }


class WorkerTaskRepository(Protocol):
    def register(self, spec: WorkerTaskSpec, *, now: datetime | None = None) -> WorkerTask: ...
    def disable_absent(self, task_ids: set[str]) -> int: ...
    def claim_due(
        self,
        *,
        owner: str,
        lease_seconds: int,
        limit: int,
        now: datetime | None = None,
    ) -> list[WorkerTask]: ...
    def complete(
        self,
        task_id: str,
        *,
        owner: str,
        status: str,
        error: str = "",
        details: Mapping[str, Any] | None = None,
        max_backoff_seconds: int,
        now: datetime | None = None,
    ) -> WorkerTask: ...
    def get(self, task_id: str) -> WorkerTask | None: ...
    def list(self) -> list[WorkerTask]: ...


class PostgresWorkerTaskRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required for worker scheduling")

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> WorkerTask:
        return WorkerTask(
            task_id=str(row[0]),
            task_kind=str(row[1]),
            enabled=bool(row[2]),
            cadence_seconds=int(row[3]),
            next_run_at=row[4],
            lease_owner=str(row[5] or ""),
            lease_until=row[6],
            last_started_at=row[7],
            last_completed_at=row[8],
            last_status=str(row[9] or "never"),
            consecutive_failures=int(row[10] or 0),
            last_error=str(row[11] or ""),
            metadata=dict(row[12] or {}),
        )

    @staticmethod
    def _select_columns() -> str:
        return (
            "task_id, task_kind, enabled, cadence_seconds, next_run_at, "
            "lease_owner, lease_until, last_started_at, last_completed_at, "
            "last_status, consecutive_failures, last_error, metadata"
        )

    def register(self, spec: WorkerTaskSpec, *, now: datetime | None = None) -> WorkerTask:
        timestamp = _aware(now)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO smartploy_worker_tasks (
                        task_id, task_kind, enabled, cadence_seconds, next_run_at,
                        metadata, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (task_id) DO UPDATE SET
                        task_kind = EXCLUDED.task_kind,
                        enabled = EXCLUDED.enabled,
                        cadence_seconds = EXCLUDED.cadence_seconds,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    RETURNING {self._select_columns()}
                    """,
                    (
                        spec.task_id,
                        spec.task_kind,
                        spec.enabled,
                        int(spec.cadence_seconds),
                        timestamp,
                        Jsonb(dict(spec.metadata or {})),
                        timestamp,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return self._from_row(row)

    def disable_absent(self, task_ids: set[str]) -> int:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if task_ids:
                    cur.execute(
                        """
                        UPDATE smartploy_worker_tasks
                        SET enabled = false,
                            lease_owner = '',
                            lease_until = NULL,
                            updated_at = now()
                        WHERE enabled = true
                          AND NOT (task_id = ANY(%s))
                        """,
                        (list(sorted(task_ids)),),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE smartploy_worker_tasks
                        SET enabled = false,
                            lease_owner = '',
                            lease_until = NULL,
                            updated_at = now()
                        WHERE enabled = true
                        """
                    )
                count = cur.rowcount
            conn.commit()
        return int(count or 0)

    def claim_due(
        self,
        *,
        owner: str,
        lease_seconds: int,
        limit: int,
        now: datetime | None = None,
    ) -> list[WorkerTask]:
        owner = str(owner or "").strip()
        if not owner or len(owner) > 200:
            raise ValueError("worker owner is required and must be <= 200 characters")
        if lease_seconds <= 0 or limit <= 0:
            raise ValueError("lease_seconds and limit must be positive")
        timestamp = _aware(now)
        lease_until = timestamp + timedelta(seconds=int(lease_seconds))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH due AS (
                        SELECT task_id
                        FROM smartploy_worker_tasks
                        WHERE enabled = true
                          AND next_run_at <= %s
                          AND (lease_until IS NULL OR lease_until <= %s)
                        ORDER BY next_run_at, task_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE smartploy_worker_tasks AS task
                    SET lease_owner = %s,
                        lease_until = %s,
                        last_started_at = %s,
                        updated_at = %s
                    FROM due
                    WHERE task.task_id = due.task_id
                    RETURNING {self._select_columns()}
                    """,
                    (
                        timestamp,
                        timestamp,
                        int(limit),
                        owner,
                        lease_until,
                        timestamp,
                        timestamp,
                    ),
                )
                rows = cur.fetchall()
            conn.commit()
        return [self._from_row(row) for row in rows]

    def complete(
        self,
        task_id: str,
        *,
        owner: str,
        status: str,
        error: str = "",
        details: Mapping[str, Any] | None = None,
        max_backoff_seconds: int,
        now: datetime | None = None,
    ) -> WorkerTask:
        if status not in VALID_RESULTS:
            raise ValueError("invalid worker completion status")
        if max_backoff_seconds <= 0:
            raise ValueError("max_backoff_seconds must be positive")
        timestamp = _aware(now)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {self._select_columns()}
                    FROM smartploy_worker_tasks
                    WHERE task_id = %s
                    FOR UPDATE
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(task_id)
                current = self._from_row(row)
                if current.lease_owner != owner:
                    raise RuntimeError("worker task lease is not owned by this worker")

                failures = current.consecutive_failures + 1 if status == "failed" else 0
                if status == "failed":
                    exponent = min(failures, 10)
                    delay = min(
                        int(max_backoff_seconds),
                        int(current.cadence_seconds) * (2 ** exponent),
                    )
                else:
                    delay = int(current.cadence_seconds)
                next_run = timestamp + timedelta(seconds=max(1, delay))
                metadata = {
                    **dict(current.metadata or {}),
                    "last_result": dict(details or {}),
                }
                cur.execute(
                    f"""
                    UPDATE smartploy_worker_tasks
                    SET next_run_at = %s,
                        lease_owner = '',
                        lease_until = NULL,
                        last_completed_at = %s,
                        last_status = %s,
                        consecutive_failures = %s,
                        last_error = %s,
                        metadata = %s,
                        updated_at = %s
                    WHERE task_id = %s
                    RETURNING {self._select_columns()}
                    """,
                    (
                        next_run,
                        timestamp,
                        status,
                        failures,
                        str(error or "")[:2000],
                        Jsonb(metadata),
                        timestamp,
                        task_id,
                    ),
                )
                updated = cur.fetchone()
            conn.commit()
        return self._from_row(updated)

    def get(self, task_id: str) -> WorkerTask | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {self._select_columns()}
                    FROM smartploy_worker_tasks
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[WorkerTask]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {self._select_columns()}
                    FROM smartploy_worker_tasks
                    ORDER BY task_id
                    """
                )
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]


class ContinuousWorker:
    def __init__(
        self,
        repository: WorkerTaskRepository,
        specs: list[WorkerTaskSpec],
        *,
        owner: str,
        lease_seconds: int = 300,
        max_backoff_seconds: int = 3600,
        claim_limit: int = 8,
    ) -> None:
        self.repository = repository
        self.specs = {spec.task_id: spec for spec in specs}
        self.owner = str(owner or "").strip()
        self.lease_seconds = int(lease_seconds)
        self.max_backoff_seconds = int(max_backoff_seconds)
        self.claim_limit = int(claim_limit)
        if not self.owner:
            raise ValueError("worker owner is required")

    def synchronize(self, *, now: datetime | None = None) -> None:
        active = set(self.specs)
        for spec in self.specs.values():
            self.repository.register(spec, now=now)
        self.repository.disable_absent(active)

    def run_once(self, *, now: datetime | None = None) -> WorkerCycle:
        timestamp = _aware(now)
        self.synchronize(now=timestamp)
        claimed = self.repository.claim_due(
            owner=self.owner,
            lease_seconds=self.lease_seconds,
            limit=self.claim_limit,
            now=timestamp,
        )
        results: list[dict[str, Any]] = []
        failed = 0

        for task in claimed:
            spec = self.specs.get(task.task_id)
            if spec is None:
                result = WorkerTaskResult(
                    status="failed",
                    error="worker task has no registered runner",
                )
            else:
                try:
                    result = spec.runner()
                except Exception as exc:
                    result = WorkerTaskResult(
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}"[:2000],
                    )
            completed = self.repository.complete(
                task.task_id,
                owner=self.owner,
                status=result.status,
                error=result.error,
                details=result.details,
                max_backoff_seconds=self.max_backoff_seconds,
                now=timestamp,
            )
            if result.status == "failed":
                failed += 1
            results.append(
                {
                    "task_id": task.task_id,
                    "status": result.status,
                    "error": result.error,
                    "next_run_at": completed.next_run_at.isoformat(),
                    "details": dict(result.details or {}),
                }
            )

        return WorkerCycle(
            claimed=len(claimed),
            completed=len(results),
            failed=failed,
            tasks=tuple(results),
        )

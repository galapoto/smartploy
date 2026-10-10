"""Storage boundaries for Smartploy job intelligence.

Smartploy owns its persistence. ObumAI storage is never imported or queried.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .domain import JobCandidate, JobRecord, SourceObservation, merge_candidates, utc_now_iso


@dataclass(frozen=True)
class SourceHealth:
    source_id: str
    status: str = "unknown"
    parser_version: str = ""
    last_attempt_at: str = ""
    last_success_at: str = ""
    last_failure_at: str = ""
    last_item_count: int = 0
    consecutive_failures: int = 0
    last_error: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "parser_version": self.parser_version,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_item_count": self.last_item_count,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "metadata": dict(self.metadata or {}),
        }


def apply_migrations(dsn: str) -> None:
    """Apply all numbered Smartploy SQL migrations in lexical order."""

    directory = Path(__file__).resolve().parent.parent / "migrations"
    paths = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not paths:
        raise RuntimeError("no Smartploy migrations found")
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            for path in paths:
                sql = path.read_text(encoding="utf-8")
                statements = [item.strip() for item in sql.split(";") if item.strip()]
                for statement in statements:
                    cur.execute(statement)
        conn.commit()


class JobRepository(Protocol):
    def upsert(self, candidate: JobCandidate, observation: SourceObservation | None = None) -> JobCandidate: ...
    def get(self, canonical_key: str) -> JobCandidate | None: ...
    def values(self) -> list[JobCandidate]: ...
    def mark_closed(self, canonical_key: str, *, closed_at: str | None = None) -> JobCandidate: ...
    def storage_status(self) -> dict[str, Any]: ...
    def record_source_attempt(
        self,
        source_id: str,
        *,
        status: str,
        item_count: int,
        parser_version: str,
        attempted_at: str | None = None,
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SourceHealth: ...
    def get_source_health(self, source_id: str) -> SourceHealth | None: ...
    def list_source_health(self) -> list[SourceHealth]: ...


def _candidate_from_dict(value: dict[str, Any]) -> JobCandidate:
    job_data = dict(value["job"])
    for field in ("requirements", "nice_to_have", "required_documents", "questions"):
        job_data[field] = tuple(job_data.get(field) or ())
    job = JobRecord(**job_data)
    return JobCandidate(
        job=job,
        canonical_url=str(value.get("canonical_url") or ""),
        canonical_key=str(value["canonical_key"]),
        description_fingerprint=str(value.get("description_fingerprint") or ""),
        source_ids=tuple(value.get("source_ids") or ()),
        source_observation_ids=tuple(value.get("source_observation_ids") or ()),
        source_raw_sha256=tuple(value.get("source_raw_sha256") or ()),
        first_seen_at=str(value.get("first_seen_at") or ""),
        last_seen_at=str(value.get("last_seen_at") or ""),
        posted_at=str(value.get("posted_at") or ""),
        last_verified_at=str(value.get("last_verified_at") or ""),
        closed_at=str(value.get("closed_at") or ""),
        source_current=bool(value.get("source_current", True)),
        duplicate_count=int(value.get("duplicate_count") or 1),
        metadata=dict(value.get("metadata") or {}),
    )


class MemoryJobRepository:
    mode = "memory"

    def __init__(self) -> None:
        self._items: dict[str, JobCandidate] = {}
        self._observations: dict[str, dict[str, Any]] = {}
        self._source_health: dict[str, SourceHealth] = {}

    def upsert(self, candidate: JobCandidate, observation: SourceObservation | None = None) -> JobCandidate:
        current = self._items.get(candidate.canonical_key)
        stored = merge_candidates(current, candidate) if current is not None else candidate
        self._items[stored.canonical_key] = stored
        if observation is not None:
            obs = observation.normalized()
            self._observations.setdefault(
                obs.observation_id,
                {
                    "observation_id": obs.observation_id,
                    "canonical_key": stored.canonical_key,
                    "source_id": obs.source_id,
                    "source_url": obs.source_url,
                    "raw_sha256": obs.raw_sha256,
                    "observed_at": obs.observed_at,
                    "payload": dict(obs.payload),
                },
            )
        return stored

    def get(self, canonical_key: str) -> JobCandidate | None:
        return self._items.get(canonical_key)

    def values(self) -> list[JobCandidate]:
        return sorted(
            self._items.values(),
            key=lambda item: (item.last_seen_at, item.canonical_key),
            reverse=True,
        )

    def mark_closed(self, canonical_key: str, *, closed_at: str | None = None) -> JobCandidate:
        current = self._items[canonical_key]
        timestamp = closed_at or utc_now_iso()
        updated = replace(
            current,
            source_current=False,
            closed_at=timestamp,
            last_verified_at=timestamp,
        )
        self._items[canonical_key] = updated
        return updated

    def storage_status(self) -> dict[str, Any]:
        return {"mode": self.mode, "ready": True}

    def record_source_attempt(
        self,
        source_id: str,
        *,
        status: str,
        item_count: int,
        parser_version: str,
        attempted_at: str | None = None,
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SourceHealth:
        if status not in {"healthy", "degraded", "failed", "disabled", "unknown"}:
            raise ValueError("invalid source health status")
        timestamp = attempted_at or utc_now_iso()
        previous = self._source_health.get(source_id)
        failures = (previous.consecutive_failures if previous else 0) + 1 if status == "failed" else 0
        last_success = previous.last_success_at if previous else ""
        last_failure = previous.last_failure_at if previous else ""
        if status in {"healthy", "degraded"}:
            last_success = timestamp
        if status == "failed":
            last_failure = timestamp
        value = SourceHealth(
            source_id=source_id,
            status=status,
            parser_version=parser_version,
            last_attempt_at=timestamp,
            last_success_at=last_success,
            last_failure_at=last_failure,
            last_item_count=max(0, int(item_count)),
            consecutive_failures=failures,
            last_error=str(error or "")[:2000],
            metadata=dict(metadata or {}),
        )
        self._source_health[source_id] = value
        return value

    def get_source_health(self, source_id: str) -> SourceHealth | None:
        return self._source_health.get(source_id)

    def list_source_health(self) -> list[SourceHealth]:
        return sorted(self._source_health.values(), key=lambda item: item.source_id)


class PostgresJobRepository:
    mode = "postgres"

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def migrate(self) -> None:
        apply_migrations(self.dsn)

    def storage_status(self) -> dict[str, Any]:
        try:
            with connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            to_regclass('public.smartploy_jobs') IS NOT NULL
                            AND to_regclass('public.smartploy_profile_facts') IS NOT NULL
                        """
                    )
                    ready = bool(cur.fetchone()[0])
            return {"mode": self.mode, "ready": ready}
        except Exception as exc:
            return {"mode": self.mode, "ready": False, "error": type(exc).__name__}

    def upsert(self, candidate: JobCandidate, observation: SourceObservation | None = None) -> JobCandidate:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT candidate FROM smartploy_jobs WHERE canonical_key = %s FOR UPDATE",
                    (candidate.canonical_key,),
                )
                row = cur.fetchone()
                stored = merge_candidates(_candidate_from_dict(row[0]), candidate) if row else candidate
                cur.execute(
                    """
                    INSERT INTO smartploy_jobs (
                        canonical_key, job_id, company, role_title, canonical_url, candidate,
                        first_seen_at, last_seen_at, posted_at, last_verified_at, closed_at,
                        source_current, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s::timestamptz, %s::timestamptz, NULLIF(%s, '')::timestamptz,
                        NULLIF(%s, '')::timestamptz, NULLIF(%s, '')::timestamptz,
                        %s, now()
                    )
                    ON CONFLICT (canonical_key) DO UPDATE SET
                        job_id = EXCLUDED.job_id,
                        company = EXCLUDED.company,
                        role_title = EXCLUDED.role_title,
                        canonical_url = EXCLUDED.canonical_url,
                        candidate = EXCLUDED.candidate,
                        first_seen_at = LEAST(smartploy_jobs.first_seen_at, EXCLUDED.first_seen_at),
                        last_seen_at = GREATEST(smartploy_jobs.last_seen_at, EXCLUDED.last_seen_at),
                        posted_at = COALESCE(
                            LEAST(smartploy_jobs.posted_at, EXCLUDED.posted_at),
                            smartploy_jobs.posted_at,
                            EXCLUDED.posted_at
                        ),
                        last_verified_at = COALESCE(
                            GREATEST(smartploy_jobs.last_verified_at, EXCLUDED.last_verified_at),
                            smartploy_jobs.last_verified_at,
                            EXCLUDED.last_verified_at
                        ),
                        closed_at = EXCLUDED.closed_at,
                        source_current = EXCLUDED.source_current,
                        updated_at = now()
                    """,
                    (
                        stored.canonical_key,
                        stored.job.job_id,
                        stored.job.company,
                        stored.job.role_title,
                        stored.canonical_url,
                        Jsonb(stored.to_dict()),
                        stored.first_seen_at,
                        stored.last_seen_at,
                        stored.posted_at,
                        stored.last_verified_at,
                        stored.closed_at,
                        stored.source_current,
                    ),
                )
                if observation is not None:
                    obs = observation.normalized()
                    cur.execute(
                        """
                        INSERT INTO smartploy_source_observations (
                            observation_id, canonical_key, source_id, source_mode, source_url,
                            source_external_id, raw_sha256, observed_at, posted_at, raw_text, payload
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s::timestamptz, NULLIF(%s, '')::timestamptz, %s, %s
                        )
                        ON CONFLICT (observation_id) DO NOTHING
                        """,
                        (
                            obs.observation_id,
                            stored.canonical_key,
                            obs.source_id,
                            obs.source_mode,
                            obs.source_url,
                            obs.source_external_id,
                            obs.raw_sha256,
                            obs.observed_at,
                            obs.posted_at,
                            obs.raw_text,
                            Jsonb(dict(obs.payload)),
                        ),
                    )
            conn.commit()
        return stored

    def get(self, canonical_key: str) -> JobCandidate | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT candidate FROM smartploy_jobs WHERE canonical_key = %s", (canonical_key,))
                row = cur.fetchone()
        return _candidate_from_dict(row[0]) if row else None

    def values(self) -> list[JobCandidate]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT candidate FROM smartploy_jobs ORDER BY last_seen_at DESC, canonical_key")
                rows = cur.fetchall()
        return [_candidate_from_dict(row[0]) for row in rows]

    def mark_closed(self, canonical_key: str, *, closed_at: str | None = None) -> JobCandidate:
        current = self.get(canonical_key)
        if current is None:
            raise KeyError(canonical_key)
        timestamp = closed_at or utc_now_iso()
        updated = replace(
            current,
            source_current=False,
            closed_at=timestamp,
            last_verified_at=timestamp,
        )
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_jobs
                    SET candidate = %s, source_current = false,
                        closed_at = %s::timestamptz, last_verified_at = %s::timestamptz,
                        updated_at = now()
                    WHERE canonical_key = %s
                    """,
                    (Jsonb(updated.to_dict()), timestamp, timestamp, canonical_key),
                )
            conn.commit()
        return updated

    def record_source_attempt(
        self,
        source_id: str,
        *,
        status: str,
        item_count: int,
        parser_version: str,
        attempted_at: str | None = None,
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SourceHealth:
        if status not in {"healthy", "degraded", "failed", "disabled", "unknown"}:
            raise ValueError("invalid source health status")
        timestamp = attempted_at or utc_now_iso()
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT consecutive_failures, last_success_at, last_failure_at "
                    "FROM smartploy_source_health WHERE source_id = %s FOR UPDATE",
                    (source_id,),
                )
                row = cur.fetchone()
                previous_failures = int(row[0]) if row else 0
                last_success = row[1].isoformat() if row and row[1] else ""
                last_failure = row[2].isoformat() if row and row[2] else ""
                failures = previous_failures + 1 if status == "failed" else 0
                if status in {"healthy", "degraded"}:
                    last_success = timestamp
                if status == "failed":
                    last_failure = timestamp
                cur.execute(
                    """
                    INSERT INTO smartploy_source_health (
                        source_id, status, parser_version, last_attempt_at, last_success_at,
                        last_failure_at, last_item_count, consecutive_failures, last_error,
                        metadata, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s::timestamptz, NULLIF(%s, '')::timestamptz,
                        NULLIF(%s, '')::timestamptz, %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (source_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        parser_version = EXCLUDED.parser_version,
                        last_attempt_at = EXCLUDED.last_attempt_at,
                        last_success_at = EXCLUDED.last_success_at,
                        last_failure_at = EXCLUDED.last_failure_at,
                        last_item_count = EXCLUDED.last_item_count,
                        consecutive_failures = EXCLUDED.consecutive_failures,
                        last_error = EXCLUDED.last_error,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    (
                        source_id,
                        status,
                        parser_version,
                        timestamp,
                        last_success,
                        last_failure,
                        max(0, int(item_count)),
                        failures,
                        str(error or "")[:2000],
                        Jsonb(dict(metadata or {})),
                    ),
                )
            conn.commit()
        return SourceHealth(
            source_id=source_id,
            status=status,
            parser_version=parser_version,
            last_attempt_at=timestamp,
            last_success_at=last_success,
            last_failure_at=last_failure,
            last_item_count=max(0, int(item_count)),
            consecutive_failures=failures,
            last_error=str(error or "")[:2000],
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _health_from_row(row: tuple[Any, ...]) -> SourceHealth:
        return SourceHealth(
            source_id=str(row[0]),
            status=str(row[1]),
            parser_version=str(row[2] or ""),
            last_attempt_at=row[3].isoformat() if row[3] else "",
            last_success_at=row[4].isoformat() if row[4] else "",
            last_failure_at=row[5].isoformat() if row[5] else "",
            last_item_count=int(row[6] or 0),
            consecutive_failures=int(row[7] or 0),
            last_error=str(row[8] or ""),
            metadata=dict(row[9] or {}),
        )

    def get_source_health(self, source_id: str) -> SourceHealth | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_id, status, parser_version, last_attempt_at, last_success_at,
                           last_failure_at, last_item_count, consecutive_failures, last_error, metadata
                    FROM smartploy_source_health
                    WHERE source_id = %s
                    """,
                    (source_id,),
                )
                row = cur.fetchone()
        return self._health_from_row(row) if row else None

    def list_source_health(self) -> list[SourceHealth]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_id, status, parser_version, last_attempt_at, last_success_at,
                           last_failure_at, last_item_count, consecutive_failures, last_error, metadata
                    FROM smartploy_source_health
                    ORDER BY source_id
                    """
                )
                rows = cur.fetchall()
        return [self._health_from_row(row) for row in rows]

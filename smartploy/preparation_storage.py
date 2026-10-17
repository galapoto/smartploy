"""Persistence for Smartploy application-draft packages."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .preparations import ApplicationPreparation
from .storage import apply_migrations


# Only submitted remote jobs with a job id can be polled for status. Keep this
# consistent with the SQL partial index and the worker's defensive check.
REFRESHABLE_PREPARATION_STATES = frozenset({"queued", "running", "blocked"})


class PreparationRepository(Protocol):
    def create_or_get(self, item: ApplicationPreparation) -> tuple[ApplicationPreparation, bool]: ...
    def save(self, item: ApplicationPreparation) -> ApplicationPreparation: ...
    def get(self, package_id: str) -> ApplicationPreparation | None: ...
    def get_by_obum_job_id(self, job_id: str) -> ApplicationPreparation | None: ...
    def list(self, *, limit: int = 100) -> list[ApplicationPreparation]: ...
    def list_refresh_candidates(self, *, limit: int = 100) -> list[ApplicationPreparation]: ...
    def defer_failed_refresh(self, package_id: str, obum_job_id: str) -> bool: ...


class MemoryPreparationRepository:
    def __init__(self, profile_id: str = "") -> None:
        self.profile_id = str(profile_id or "").strip()
        self._items: dict[str, ApplicationPreparation] = {}

    def _allowed(self, item: ApplicationPreparation) -> bool:
        return not self.profile_id or item.profile_id == self.profile_id

    def create_or_get(self, item: ApplicationPreparation) -> tuple[ApplicationPreparation, bool]:
        normalized = item.normalized()
        if self.profile_id and normalized.profile_id != self.profile_id:
            raise ValueError("preparation belongs to a different profile")
        existing = self._items.get(normalized.package_id)
        if existing is not None:
            if (
                existing.canonical_key != normalized.canonical_key
                or existing.profile_id != normalized.profile_id
                or existing.job_snapshot_sha256 != normalized.job_snapshot_sha256
                or existing.evidence_sha256 != normalized.evidence_sha256
            ):
                raise ValueError("preparation package ID conflicts with immutable identity")
            return existing, False
        self._items[normalized.package_id] = normalized
        return normalized, True

    def save(self, item: ApplicationPreparation) -> ApplicationPreparation:
        normalized = item.normalized()
        if self.profile_id and normalized.profile_id != self.profile_id:
            raise ValueError("preparation belongs to a different profile")
        existing = self._items.get(normalized.package_id)
        if existing is None:
            raise KeyError(normalized.package_id)
        if (
            existing.canonical_key != normalized.canonical_key
            or existing.profile_id != normalized.profile_id
            or existing.job_snapshot_sha256 != normalized.job_snapshot_sha256
            or existing.evidence_sha256 != normalized.evidence_sha256
        ):
            raise ValueError("immutable preparation identity cannot change")
        self._items[normalized.package_id] = normalized
        return normalized

    def get(self, package_id: str) -> ApplicationPreparation | None:
        item = self._items.get(package_id)
        return item if item is not None and self._allowed(item) else None

    def get_by_obum_job_id(self, job_id: str) -> ApplicationPreparation | None:
        value = str(job_id or "").strip()
        if not value:
            return None
        for item in self._items.values():
            if item.obum_job_id == value and self._allowed(item):
                return item
        return None

    def list(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        return sorted(
            (item for item in self._items.values() if self._allowed(item)),
            key=lambda item: (item.requested_at, item.package_id),
            reverse=True,
        )[:limit]

    def list_refresh_candidates(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        """Poll active remote jobs in least-recently-refreshed order.

        Filtering happens before the LIMIT, so a full history of completed
        preparations cannot starve a pending job.
        """
        bounded = max(1, min(int(limit), 500))
        return sorted(
            (
                item for item in self._items.values()
                if self._allowed(item)
                and item.status in REFRESHABLE_PREPARATION_STATES
                and item.obum_job_id
            ),
            key=lambda item: (item.updated_at, item.package_id),
        )[:bounded]

    def defer_failed_refresh(self, package_id: str, obum_job_id: str) -> bool:
        """Rotate a failed status lookup without modifying the remote job state.

        A package whose remote ID/status changed during the lookup is left
        untouched. Failed remote lookups must not monopolize the next batch.
        """
        current = self.get(package_id)
        if (
            current is None
            or current.status not in REFRESHABLE_PREPARATION_STATES
            or not obum_job_id
            or current.obum_job_id != obum_job_id
        ):
            return False
        previous = datetime.fromisoformat(current.updated_at)
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        attempted_at = max(
            datetime.now(timezone.utc), previous + timedelta(microseconds=1)
        )
        self._items[package_id] = replace(
            current, updated_at=attempted_at.isoformat()
        ).normalized()
        return True


class PostgresPreparationRepository:
    def __init__(self, dsn: str, profile_id: str = "") -> None:
        self.dsn = str(dsn or "").strip()
        self.profile_id = str(profile_id or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def _assert_profile(self, item: ApplicationPreparation) -> None:
        if self.profile_id and item.profile_id != self.profile_id:
            raise ValueError("preparation belongs to a different profile")

    def migrate(self) -> None:
        apply_migrations(self.dsn)

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> ApplicationPreparation:
        return ApplicationPreparation(
            package_id=str(row[0]),
            canonical_key=str(row[1]),
            profile_id=str(row[2]),
            preparation_contract=str(row[3]),
            job_snapshot_sha256=str(row[4]),
            evidence_sha256=str(row[5]),
            job_snapshot=dict(row[6] or {}),
            evidence_snapshot=dict(row[7] or {}),
            score_snapshot=dict(row[8] or {}),
            status=str(row[9]),
            obum_job_id=str(row[10] or ""),
            obum_client_request_id=str(row[11] or ""),
            requested_at=row[12].isoformat() if row[12] else "",
            updated_at=row[13].isoformat() if row[13] else "",
            completed_at=row[14].isoformat() if row[14] else "",
            result=dict(row[15] or {}),
            raw_output=str(row[16] or ""),
            error=str(row[17] or ""),
        ).normalized()

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT package_id, canonical_key, profile_id, preparation_contract,
                   job_snapshot_sha256, evidence_sha256, job_snapshot, evidence_snapshot,
                   score_snapshot, status, obum_job_id, obum_client_request_id,
                   requested_at, updated_at, completed_at, result, raw_output, error
            FROM smartploy_application_preparations
        """

    def create_or_get(self, item: ApplicationPreparation) -> tuple[ApplicationPreparation, bool]:
        value = item.normalized()
        self._assert_profile(value)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_application_preparations (
                        package_id, canonical_key, profile_id, preparation_contract,
                        job_snapshot_sha256, evidence_sha256, job_snapshot, evidence_snapshot,
                        score_snapshot, status, obum_job_id, obum_client_request_id, requested_at, updated_at,
                        completed_at, result, raw_output, error
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '', '',
                        %s::timestamptz, %s::timestamptz, NULL, %s, '', ''
                    )
                    ON CONFLICT (package_id) DO NOTHING
                    RETURNING package_id
                    """,
                    (
                        value.package_id,
                        value.canonical_key,
                        value.profile_id,
                        value.preparation_contract,
                        value.job_snapshot_sha256,
                        value.evidence_sha256,
                        Jsonb(value.job_snapshot),
                        Jsonb(value.evidence_snapshot),
                        Jsonb(value.score_snapshot),
                        value.status,
                        value.requested_at,
                        value.updated_at,
                        Jsonb(value.result),
                    ),
                )
                created = cur.fetchone() is not None
                cur.execute(self._select_sql() + " WHERE package_id = %s", (value.package_id,))
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("preparation create/read reconciliation failed")
        stored = self._from_row(row)
        if (
            stored.canonical_key != value.canonical_key
            or stored.profile_id != value.profile_id
            or stored.job_snapshot_sha256 != value.job_snapshot_sha256
            or stored.evidence_sha256 != value.evidence_sha256
        ):
            raise ValueError("preparation package ID conflicts with immutable identity")
        return stored, created

    def save(self, item: ApplicationPreparation) -> ApplicationPreparation:
        value = item.normalized()
        self._assert_profile(value)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_application_preparations
                    SET status = %s,
                        obum_job_id = %s,
                        obum_client_request_id = %s,
                        updated_at = %s::timestamptz,
                        completed_at = NULLIF(%s, '')::timestamptz,
                        result = %s,
                        raw_output = %s,
                        error = %s
                    WHERE package_id = %s
                      AND canonical_key = %s
                      AND profile_id = %s
                      AND job_snapshot_sha256 = %s
                      AND evidence_sha256 = %s
                    """,
                    (
                        value.status,
                        value.obum_job_id,
                        value.obum_client_request_id,
                        value.updated_at,
                        value.completed_at,
                        Jsonb(value.result),
                        value.raw_output,
                        value.error,
                        value.package_id,
                        value.canonical_key,
                        value.profile_id,
                        value.job_snapshot_sha256,
                        value.evidence_sha256,
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError("immutable preparation identity changed or package not found")
                cur.execute(self._select_sql() + " WHERE package_id = %s", (value.package_id,))
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise KeyError(value.package_id)
        return self._from_row(row)

    def get(self, package_id: str) -> ApplicationPreparation | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if self.profile_id:
                    cur.execute(
                        self._select_sql() + " WHERE package_id = %s AND profile_id = %s",
                        (package_id, self.profile_id),
                    )
                else:
                    cur.execute(self._select_sql() + " WHERE package_id = %s", (package_id,))
                row = cur.fetchone()
        return self._from_row(row) if row else None

    def get_by_obum_job_id(self, job_id: str) -> ApplicationPreparation | None:
        value = str(job_id or "").strip()
        if not value:
            return None
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if self.profile_id:
                    cur.execute(
                        self._select_sql()
                        + " WHERE obum_job_id = %s AND profile_id = %s ORDER BY requested_at DESC LIMIT 1",
                        (value, self.profile_id),
                    )
                else:
                    cur.execute(
                        self._select_sql()
                        + " WHERE obum_job_id = %s ORDER BY requested_at DESC LIMIT 1",
                        (value,),
                    )
                row = cur.fetchone()
        return self._from_row(row) if row else None

    def list(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if self.profile_id:
                    cur.execute(
                        self._select_sql()
                        + " WHERE profile_id = %s ORDER BY requested_at DESC, package_id DESC LIMIT %s",
                        (self.profile_id, bounded),
                    )
                else:
                    cur.execute(
                        self._select_sql() + " ORDER BY requested_at DESC, package_id DESC LIMIT %s",
                        (bounded,),
                    )
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]

    def list_refresh_candidates(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        """Select pollable jobs before limiting; rotate oldest updates first."""
        bounded = max(1, min(int(limit), 500))
        query = self._select_sql() + """
            WHERE status IN ('queued', 'running', 'blocked')
              AND obum_job_id <> ''
        """
        params: list[Any] = []
        if self.profile_id:
            query += " AND profile_id = %s"
            params.append(self.profile_id)
        query += " ORDER BY updated_at ASC, package_id ASC LIMIT %s"
        params.append(bounded)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]

    def defer_failed_refresh(self, package_id: str, obum_job_id: str) -> bool:
        """Move a failed in-flight lookup to the tail of the refresh queue.

        Conditional update prevents a stale retry from touching a newly
        replaced remote job or a completed/cancelled package.
        """
        query = """
            UPDATE smartploy_application_preparations
            SET updated_at = GREATEST(updated_at + INTERVAL '1 microsecond', now())
            WHERE package_id = %s
              AND obum_job_id = %s
              AND status IN ('queued', 'running', 'blocked')
        """
        params: list[Any] = [package_id, obum_job_id]
        if self.profile_id:
            query += " AND profile_id = %s"
            params.append(self.profile_id)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                changed = cur.rowcount == 1
        return changed


def with_runtime(
    item: ApplicationPreparation,
    *,
    status: str,
    obum_job_id: str | None = None,
    obum_client_request_id: str | None = None,
    result: dict[str, Any] | None = None,
    raw_output: str | None = None,
    error: str | None = None,
    completed_at: str | None = None,
    updated_at: str,
) -> ApplicationPreparation:
    return replace(
        item,
        status=status,
        obum_job_id=item.obum_job_id if obum_job_id is None else obum_job_id,
        obum_client_request_id=(
            item.obum_client_request_id if obum_client_request_id is None else obum_client_request_id
        ),
        result=item.result if result is None else result,
        raw_output=item.raw_output if raw_output is None else raw_output,
        error=item.error if error is None else error,
        completed_at=item.completed_at if completed_at is None else completed_at,
        updated_at=updated_at,
    ).normalized()

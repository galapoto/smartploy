"""Persistence for Smartploy application-draft packages."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .preparations import ApplicationPreparation
from .storage import apply_migrations


class PreparationRepository(Protocol):
    def create_or_get(self, item: ApplicationPreparation) -> tuple[ApplicationPreparation, bool]: ...
    def save(self, item: ApplicationPreparation) -> ApplicationPreparation: ...
    def get(self, package_id: str) -> ApplicationPreparation | None: ...
    def list(self, *, limit: int = 100) -> list[ApplicationPreparation]: ...


class MemoryPreparationRepository:
    def __init__(self) -> None:
        self._items: dict[str, ApplicationPreparation] = {}

    def create_or_get(self, item: ApplicationPreparation) -> tuple[ApplicationPreparation, bool]:
        normalized = item.normalized()
        existing = self._items.get(normalized.package_id)
        if existing is not None:
            return existing, False
        self._items[normalized.package_id] = normalized
        return normalized, True

    def save(self, item: ApplicationPreparation) -> ApplicationPreparation:
        normalized = item.normalized()
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
        return self._items.get(package_id)

    def list(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        return sorted(
            self._items.values(),
            key=lambda item: (item.requested_at, item.package_id),
            reverse=True,
        )[:limit]


class PostgresPreparationRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

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
        return self._from_row(row), created

    def save(self, item: ApplicationPreparation) -> ApplicationPreparation:
        value = item.normalized()
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
                cur.execute(self._select_sql() + " WHERE package_id = %s", (package_id,))
                row = cur.fetchone()
        return self._from_row(row) if row else None

    def list(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select_sql() + " ORDER BY requested_at DESC, package_id DESC LIMIT %s",
                    (bounded,),
                )
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]


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

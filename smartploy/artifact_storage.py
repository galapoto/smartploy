"""Persistence for immutable application document artifacts."""

from __future__ import annotations

from typing import Any, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .artifacts import ApplicationArtifact
from .storage import apply_migrations


class ArtifactRepository(Protocol):
    def create_or_get(self, item: ApplicationArtifact) -> tuple[ApplicationArtifact, bool]: ...
    def get(self, artifact_id: str) -> ApplicationArtifact | None: ...
    def list_for_package(self, package_id: str) -> list[ApplicationArtifact]: ...


class MemoryArtifactRepository:
    def __init__(self) -> None:
        self._items: dict[str, ApplicationArtifact] = {}

    def create_or_get(self, item: ApplicationArtifact) -> tuple[ApplicationArtifact, bool]:
        value = item.normalized()
        existing = self._items.get(value.artifact_id)
        if existing is not None:
            if existing.normalized() != value:
                raise ValueError("artifact ID conflicts with immutable content")
            return existing, False
        self._items[value.artifact_id] = value
        return value, True

    def get(self, artifact_id: str) -> ApplicationArtifact | None:
        return self._items.get(str(artifact_id or "").strip())

    def list_for_package(self, package_id: str) -> list[ApplicationArtifact]:
        key = str(package_id or "").strip()
        return sorted(
            (item for item in self._items.values() if item.package_id == key),
            key=lambda item: (item.artifact_type, item.created_at, item.artifact_id),
        )


class PostgresArtifactRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def migrate(self) -> None:
        apply_migrations(self.dsn)

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> ApplicationArtifact:
        return ApplicationArtifact(
            artifact_id=str(row[0]),
            package_id=str(row[1]),
            canonical_key=str(row[2]),
            artifact_type=str(row[3]),
            filename=str(row[4]),
            media_type=str(row[5]),
            content_sha256=str(row[6]),
            size_bytes=int(row[7]),
            content=bytes(row[8]),
            created_at=row[9].isoformat() if row[9] else "",
            metadata=dict(row[10] or {}),
        ).normalized()

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT artifact_id, package_id, canonical_key, artifact_type, filename,
                   media_type, content_sha256, size_bytes, content, created_at, metadata
            FROM smartploy_application_artifacts
        """

    def create_or_get(self, item: ApplicationArtifact) -> tuple[ApplicationArtifact, bool]:
        value = item.normalized()
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_application_artifacts (
                        artifact_id, package_id, canonical_key, artifact_type, filename,
                        media_type, content_sha256, size_bytes, content, created_at, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::timestamptz, %s
                    )
                    ON CONFLICT (artifact_id) DO NOTHING
                    RETURNING artifact_id
                    """,
                    (
                        value.artifact_id,
                        value.package_id,
                        value.canonical_key,
                        value.artifact_type,
                        value.filename,
                        value.media_type,
                        value.content_sha256,
                        value.size_bytes,
                        value.content,
                        value.created_at,
                        Jsonb(value.metadata),
                    ),
                )
                created = cur.fetchone() is not None
                cur.execute(self._select_sql() + " WHERE artifact_id = %s", (value.artifact_id,))
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("artifact create/read reconciliation failed")
        stored = self._from_row(row)
        if stored.normalized() != value:
            raise ValueError("artifact ID conflicts with immutable content")
        return stored, created

    def get(self, artifact_id: str) -> ApplicationArtifact | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(self._select_sql() + " WHERE artifact_id = %s", (artifact_id,))
                row = cur.fetchone()
        return self._from_row(row) if row else None

    def list_for_package(self, package_id: str) -> list[ApplicationArtifact]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select_sql()
                    + " WHERE package_id = %s ORDER BY artifact_type, created_at, artifact_id",
                    (package_id,),
                )
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]

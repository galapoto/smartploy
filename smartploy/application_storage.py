"""Storage for Smartploy application CRM records and append-only events."""

from __future__ import annotations

from typing import Any, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .applications import (
    ApplicationEvent,
    ApplicationRecord,
    apply_preparation_to_application,
    initial_application_for_preparation,
    preparation_event,
)
from .preparations import ApplicationPreparation
from .storage import apply_migrations


class ApplicationRepository(Protocol):
    def sync_preparation(self, preparation: ApplicationPreparation) -> ApplicationRecord: ...
    def get(self, application_id: str) -> ApplicationRecord | None: ...
    def list(self, *, limit: int = 100) -> list[ApplicationRecord]: ...
    def events(self, application_id: str, *, limit: int = 500) -> list[ApplicationEvent]: ...


class MemoryApplicationRepository:
    def __init__(self) -> None:
        self._items: dict[str, ApplicationRecord] = {}
        self._events: dict[str, ApplicationEvent] = {}

    def sync_preparation(self, preparation: ApplicationPreparation) -> ApplicationRecord:
        application_id = initial_application_for_preparation(preparation).application_id
        before = self._items.get(application_id)
        after = (
            initial_application_for_preparation(preparation)
            if before is None
            else apply_preparation_to_application(before, preparation)
        )
        event = preparation_event(before, after, preparation)
        self._items[application_id] = after
        self._events.setdefault(event.event_id, event)
        return after

    def get(self, application_id: str) -> ApplicationRecord | None:
        return self._items.get(application_id)

    def list(self, *, limit: int = 100) -> list[ApplicationRecord]:
        bounded = max(1, min(int(limit), 500))
        return sorted(
            self._items.values(),
            key=lambda item: (item.updated_at, item.application_id),
            reverse=True,
        )[:bounded]

    def events(self, application_id: str, *, limit: int = 500) -> list[ApplicationEvent]:
        bounded = max(1, min(int(limit), 2000))
        return sorted(
            (item for item in self._events.values() if item.application_id == application_id),
            key=lambda item: (item.occurred_at, item.event_id),
        )[:bounded]


class PostgresApplicationRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def migrate(self) -> None:
        apply_migrations(self.dsn)

    @staticmethod
    def _record_from_row(row: tuple[Any, ...]) -> ApplicationRecord:
        return ApplicationRecord(
            application_id=str(row[0]),
            canonical_key=str(row[1]),
            package_id=str(row[2] or ""),
            state=str(row[3]),
            created_at=row[4].isoformat() if row[4] else "",
            updated_at=row[5].isoformat() if row[5] else "",
            submitted_at=row[6].isoformat() if row[6] else "",
            external_confirmation_id=str(row[7] or ""),
            external_reference=str(row[8] or ""),
            metadata=dict(row[9] or {}),
        ).normalized()

    @staticmethod
    def _event_from_row(row: tuple[Any, ...]) -> ApplicationEvent:
        return ApplicationEvent(
            event_id=str(row[0]),
            application_id=str(row[1]),
            event_type=str(row[2]),
            from_state=str(row[3] or ""),
            to_state=str(row[4]),
            source_type=str(row[5]),
            source_id=str(row[6]),
            occurred_at=row[7].isoformat() if row[7] else "",
            metadata=dict(row[8] or {}),
        ).normalized()

    @staticmethod
    def _record_select() -> str:
        return """
            SELECT application_id, canonical_key, package_id, state, created_at, updated_at,
                   submitted_at, external_confirmation_id, external_reference, metadata
            FROM smartploy_applications
        """

    def sync_preparation(self, preparation: ApplicationPreparation) -> ApplicationRecord:
        proposed = initial_application_for_preparation(preparation)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._record_select() + " WHERE application_id = %s FOR UPDATE",
                    (proposed.application_id,),
                )
                row = cur.fetchone()
                before = self._record_from_row(row) if row else None
                after = proposed if before is None else apply_preparation_to_application(before, preparation)

                cur.execute(
                    """
                    INSERT INTO smartploy_applications (
                        application_id, canonical_key, package_id, state, created_at, updated_at,
                        submitted_at, external_confirmation_id, external_reference, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
                        NULLIF(%s, '')::timestamptz, %s, %s, %s
                    )
                    ON CONFLICT (application_id) DO UPDATE SET
                        package_id = EXCLUDED.package_id,
                        state = EXCLUDED.state,
                        updated_at = EXCLUDED.updated_at,
                        submitted_at = EXCLUDED.submitted_at,
                        external_confirmation_id = EXCLUDED.external_confirmation_id,
                        external_reference = EXCLUDED.external_reference,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        after.application_id,
                        after.canonical_key,
                        after.package_id,
                        after.state,
                        after.created_at,
                        after.updated_at,
                        after.submitted_at,
                        after.external_confirmation_id,
                        after.external_reference,
                        Jsonb(after.metadata),
                    ),
                )

                event = preparation_event(before, after, preparation)
                cur.execute(
                    """
                    INSERT INTO smartploy_application_events (
                        event_id, application_id, event_type, from_state, to_state,
                        source_type, source_id, occurred_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        event.event_id,
                        event.application_id,
                        event.event_type,
                        event.from_state,
                        event.to_state,
                        event.source_type,
                        event.source_id,
                        event.occurred_at,
                        Jsonb(event.metadata),
                    ),
                )
            conn.commit()
        return after

    def get(self, application_id: str) -> ApplicationRecord | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(self._record_select() + " WHERE application_id = %s", (application_id,))
                row = cur.fetchone()
        return self._record_from_row(row) if row else None

    def list(self, *, limit: int = 100) -> list[ApplicationRecord]:
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._record_select() + " ORDER BY updated_at DESC, application_id DESC LIMIT %s",
                    (bounded,),
                )
                rows = cur.fetchall()
        return [self._record_from_row(row) for row in rows]

    def events(self, application_id: str, *, limit: int = 500) -> list[ApplicationEvent]:
        bounded = max(1, min(int(limit), 2000))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, application_id, event_type, from_state, to_state,
                           source_type, source_id, occurred_at, metadata
                    FROM smartploy_application_events
                    WHERE application_id = %s
                    ORDER BY occurred_at, event_id
                    LIMIT %s
                    """,
                    (application_id, bounded),
                )
                rows = cur.fetchall()
        return [self._event_from_row(row) for row in rows]

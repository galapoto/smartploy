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


def _summary_payload(state_counts: dict[str, int], actually_submitted: int) -> dict[str, Any]:
    return {
        "total_records": sum(state_counts.values()),
        "state_counts": dict(sorted(state_counts.items())),
        "preparing": state_counts.get("preparing", 0),
        "awaiting_review": (
            state_counts.get("ready_for_review", 0)
            + state_counts.get("needs_review", 0)
        ),
        "preparation_blocked": state_counts.get("preparation_blocked", 0),
        "actually_submitted": int(actually_submitted),
        "interviews": state_counts.get("interview", 0),
        "offers": state_counts.get("offer", 0),
        "rejections": state_counts.get("rejected", 0),
    }


class ApplicationRepository(Protocol):
    def sync_preparation(self, preparation: ApplicationPreparation) -> ApplicationRecord: ...
    def get(self, application_id: str) -> ApplicationRecord | None: ...
    def list(self, *, limit: int = 100) -> list[ApplicationRecord]: ...
    def events(self, application_id: str, *, limit: int = 500) -> list[ApplicationEvent]: ...
    def summary(self) -> dict[str, Any]: ...


class MemoryApplicationRepository:
    def __init__(self, profile_id: str = "") -> None:
        self.profile_id = str(profile_id or "").strip()
        self._items: dict[str, ApplicationRecord] = {}
        self._events: dict[str, ApplicationEvent] = {}

    def _allowed(self, item: ApplicationRecord) -> bool:
        return not self.profile_id or item.profile_id == self.profile_id

    def sync_preparation(self, preparation: ApplicationPreparation) -> ApplicationRecord:
        if self.profile_id and preparation.profile_id != self.profile_id:
            raise ValueError("preparation belongs to a different profile")
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
        item = self._items.get(application_id)
        return item if item is not None and self._allowed(item) else None

    def list(self, *, limit: int = 100) -> list[ApplicationRecord]:
        bounded = max(1, min(int(limit), 500))
        return sorted(
            (item for item in self._items.values() if self._allowed(item)),
            key=lambda item: (item.updated_at, item.application_id),
            reverse=True,
        )[:bounded]

    def events(self, application_id: str, *, limit: int = 500) -> list[ApplicationEvent]:
        bounded = max(1, min(int(limit), 2000))
        if self.get(application_id) is None:
            return []
        return sorted(
            (item for item in self._events.values() if item.application_id == application_id),
            key=lambda item: (item.occurred_at, item.event_id),
        )[:bounded]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        allowed = [item for item in self._items.values() if self._allowed(item)]
        for item in allowed:
            counts[item.state] = counts.get(item.state, 0) + 1
        return _summary_payload(counts, sum(1 for item in allowed if item.has_been_submitted))


class PostgresApplicationRepository:
    def __init__(self, dsn: str, profile_id: str = "") -> None:
        self.dsn = str(dsn or "").strip()
        self.profile_id = str(profile_id or "").strip()
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
            profile_id=str(row[3] or "default"),
            state=str(row[4]),
            created_at=row[5].isoformat() if row[5] else "",
            updated_at=row[6].isoformat() if row[6] else "",
            submitted_at=row[7].isoformat() if row[7] else "",
            external_confirmation_id=str(row[8] or ""),
            external_reference=str(row[9] or ""),
            metadata=dict(row[10] or {}),
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
            SELECT application_id, canonical_key, package_id, profile_id, state, created_at, updated_at,
                   submitted_at, external_confirmation_id, external_reference, metadata
            FROM smartploy_applications
        """

    def sync_preparation(self, preparation: ApplicationPreparation) -> ApplicationRecord:
        if self.profile_id and preparation.profile_id != self.profile_id:
            raise ValueError("preparation belongs to a different profile")
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
                        application_id, canonical_key, package_id, profile_id, state, created_at, updated_at,
                        submitted_at, external_confirmation_id, external_reference, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
                        NULLIF(%s, '')::timestamptz, %s, %s, %s
                    )
                    ON CONFLICT (application_id) DO UPDATE SET
                        package_id = EXCLUDED.package_id,
                        profile_id = EXCLUDED.profile_id,
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
                        after.profile_id,
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
                if self.profile_id:
                    cur.execute(
                        self._record_select() + " WHERE application_id = %s AND profile_id = %s",
                        (application_id, self.profile_id),
                    )
                else:
                    cur.execute(self._record_select() + " WHERE application_id = %s", (application_id,))
                row = cur.fetchone()
        return self._record_from_row(row) if row else None

    def list(self, *, limit: int = 100) -> list[ApplicationRecord]:
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if self.profile_id:
                    cur.execute(
                        self._record_select()
                        + " WHERE profile_id = %s ORDER BY updated_at DESC, application_id DESC LIMIT %s",
                        (self.profile_id, bounded),
                    )
                else:
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
                if self.profile_id:
                    cur.execute(
                        """
                        SELECT event.event_id, event.application_id, event.event_type,
                               event.from_state, event.to_state, event.source_type,
                               event.source_id, event.occurred_at, event.metadata
                        FROM smartploy_application_events AS event
                        JOIN smartploy_applications AS app
                          ON app.application_id = event.application_id
                        WHERE event.application_id = %s
                          AND app.profile_id = %s
                        ORDER BY event.occurred_at, event.event_id
                        LIMIT %s
                        """,
                        (application_id, self.profile_id, bounded),
                    )
                else:
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

    def summary(self) -> dict[str, Any]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if self.profile_id:
                    cur.execute(
                        "SELECT state, count(*) FROM smartploy_applications "
                        "WHERE profile_id = %s GROUP BY state",
                        (self.profile_id,),
                    )
                else:
                    cur.execute(
                        "SELECT state, count(*) FROM smartploy_applications GROUP BY state"
                    )
                counts = {str(state): int(count) for state, count in cur.fetchall()}
                if self.profile_id:
                    cur.execute(
                        "SELECT count(*) FROM smartploy_applications "
                        "WHERE profile_id = %s AND submitted_at IS NOT NULL",
                        (self.profile_id,),
                    )
                else:
                    cur.execute(
                        "SELECT count(*) FROM smartploy_applications WHERE submitted_at IS NOT NULL"
                    )
                submitted = int(cur.fetchone()[0])
        return _summary_payload(counts, submitted)

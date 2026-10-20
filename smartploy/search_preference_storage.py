"""Owner-scoped, persistent job search modes and editable preferences."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from psycopg import connect
from psycopg.types.json import Jsonb

from .search_preferences import (
    SearchPreferences, SearchPreferenceConflict, revise_preferences,
)


def _stored(profile_id: str, row: tuple[Any, ...] | None) -> SearchPreferences:
    if not row:
        return SearchPreferences(profile_id=profile_id)
    mode, criteria, revision, updated_at = row
    criteria = criteria or {}
    return SearchPreferences(
        profile_id=profile_id,
        completed=True,
        mode=str(mode),
        roles=tuple(criteria.get("roles") or ()),
        locations=tuple(criteria.get("locations") or ()),
        languages=tuple(criteria.get("languages") or ()),
        work_modes=tuple(criteria.get("work_modes") or ()),
        keywords=tuple(criteria.get("keywords") or ()),
        skills=tuple(criteria.get("skills") or ()),
        seniority=str(criteria.get("seniority") or "any"),
        auto_draft_enabled=criteria.get("auto_draft_enabled") is True,
        revision=int(revision),
        updated_at=updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
    )


def _criteria(item: SearchPreferences) -> dict[str, Any]:
    return {
        "roles": list(item.roles), "locations": list(item.locations),
        "languages": list(item.languages), "work_modes": list(item.work_modes),
        "keywords": list(item.keywords), "skills": list(item.skills),
        "seniority": item.seniority,
        "auto_draft_enabled": item.auto_draft_enabled,
    }


class MemorySearchPreferenceRepository:
    def __init__(self) -> None:
        self._items: dict[str, SearchPreferences] = {}

    def get(self, profile_id: str) -> SearchPreferences:
        return self._items.get(profile_id) or SearchPreferences(profile_id=profile_id)

    def save(self, profile_id: str, data: dict[str, Any], expected_revision: int) -> SearchPreferences:
        original = self.get(profile_id)
        if original.revision != expected_revision:
            raise SearchPreferenceConflict("Search preferences changed in another session; reload before saving")
        item = revise_preferences(profile_id, data, revision=expected_revision)
        self._items[profile_id] = item
        return item

    @contextmanager
    def auto_draft_guard(self, profile_id: str, revision: int) -> Iterator[bool]:
        """Memory fixtures; a persisted opt-in is mandatory in production."""
        p = self._items.get(profile_id)
        yield bool(p and p.auto_draft_enabled and p.mode == "personalized" and
                   p.completed and p.revision == revision)


class PostgresSearchPreferenceRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def get(self, profile_id: str) -> SearchPreferences:
        with connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mode, criteria, revision, updated_at
                       FROM smartploy_search_preferences WHERE profile_id = %s""",
                    (profile_id,),
                )
                row = cursor.fetchone()
        return _stored(profile_id, row)

    def save(self, profile_id: str, data: dict[str, Any], expected_revision: int) -> SearchPreferences:
        candidate = revise_preferences(profile_id, data, revision=expected_revision)
        with connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO smartploy_search_preferences
                         (profile_id, mode, criteria, revision, updated_at)
                       VALUES (%s, %s, %s, %s, now())
                       ON CONFLICT (profile_id) DO UPDATE SET
                         mode = EXCLUDED.mode,
                         criteria = EXCLUDED.criteria,
                         revision = EXCLUDED.revision,
                         updated_at = now()
                       WHERE smartploy_search_preferences.revision = %s
                       RETURNING mode, criteria, revision, updated_at""",
                    (
                        profile_id, candidate.mode, Jsonb(_criteria(candidate)),
                        candidate.revision, expected_revision,
                    ),
                )
                row = cursor.fetchone()
        if not row:
            raise SearchPreferenceConflict("Search preferences changed in another session; reload before saving")
        return _stored(profile_id, row)

    def list_auto_draft_profiles(self, limit: int = 200) -> list[str]:
        """Only real ACTIVE owner profiles with a currently enabled IT job search.

        No email, CV, prompt or candidate data leaves PostgreSQL. A disabled or
        erasure-quarantined account cannot be discovered by the worker.
        """
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT p.profile_id
                       FROM smartploy_search_preferences p
                       JOIN smartploy_user_profiles up ON up.profile_id = p.profile_id
                       JOIN smartploy_users u ON u.user_id = up.user_id
                       WHERE p.mode = 'personalized'
                         AND p.criteria @> '{"auto_draft_enabled": true}'::jsonb
                         AND u.status = 'active'
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests e
                             WHERE e.user_id = u.user_id OR e.profile_id = p.profile_id
                         )
                       ORDER BY p.updated_at ASC, p.profile_id
                       LIMIT %s""",
                    (bounded,),
                )
                rows = cur.fetchall()
        return [str(row[0]) for row in rows]

    @contextmanager
    def auto_draft_guard(self, profile_id: str, revision: int) -> Iterator[bool]:
        """Serialize opt-out/quarantine with original workspace creation.

        The existing create_or_get() runs while this preference/account row
        is locked FOR SHARE. Thus, after a completed opt-out mutation returns,
        no old worker can create further drafts for that preference revision.
        This is an internal local-only write: it is never permission to
        contact an employer or remote AI processor.
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT p.revision
                       FROM smartploy_search_preferences p
                       JOIN smartploy_user_profiles up ON up.profile_id = p.profile_id
                       JOIN smartploy_users u ON u.user_id = up.user_id
                       WHERE p.profile_id = %s AND p.revision = %s
                         AND p.mode = 'personalized'
                         AND p.criteria @> '{"auto_draft_enabled": true}'::jsonb
                         AND u.status = 'active'
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests e
                             WHERE e.user_id = u.user_id OR e.profile_id = p.profile_id
                         )
                       FOR SHARE OF p, u""",
                    (profile_id, revision),
                )
                allowed = cur.fetchone() is not None
                yield allowed

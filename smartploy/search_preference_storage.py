"""Owner-scoped, persistent job search modes and editable preferences."""
from __future__ import annotations

from typing import Any

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
        auto_drafts_enabled=criteria.get("auto_drafts_enabled") is True,
        revision=int(revision),
        updated_at=updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
    )


def _criteria(item: SearchPreferences) -> dict[str, Any]:
    return {
        "roles": list(item.roles), "locations": list(item.locations),
        "languages": list(item.languages), "work_modes": list(item.work_modes),
        "keywords": list(item.keywords), "skills": list(item.skills),
        "seniority": item.seniority,
        "auto_drafts_enabled": item.auto_drafts_enabled,
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

    def list_auto_draft_profiles(self, *, limit: int = 50) -> list[tuple[str, str]]:
        """Only verified active owner/profile pairs who opted in to local drafting.

        Reuse the ORIGINAL account identity and search preferences tables;
        no separate privacy or consent ledger, no global profile fallback.
        """
        with connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT u.user_id,p.profile_id
                       FROM smartploy_search_preferences AS prefs
                       JOIN smartploy_user_profiles AS p
                         ON p.profile_id=prefs.profile_id
                       JOIN smartploy_users AS u ON u.user_id=p.user_id
                       WHERE u.status='active' AND prefs.mode='personalized'
                         AND prefs.criteria->>'auto_drafts_enabled'='true'
                       ORDER BY prefs.updated_at ASC,p.profile_id
                       LIMIT %s""",
                    (max(1,min(int(limit),100)),),
                )
                rows=cursor.fetchall()
        return [(str(user_id),str(profile_id)) for user_id,profile_id in rows]

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

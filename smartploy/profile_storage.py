"""Persistence for Smartploy candidate profile evidence."""

from __future__ import annotations

from typing import Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .profile import CandidateProfile, ProfileFact
from .storage import apply_migrations


class ProfileRepository(Protocol):
    profile_id: str
    def upsert_fact(self, fact: ProfileFact) -> ProfileFact: ...
    def list_facts(self) -> list[ProfileFact]: ...
    def profile(self) -> CandidateProfile: ...


class MemoryProfileRepository:
    def __init__(self, profile_id: str = "default") -> None:
        self.profile_id = profile_id
        self._facts: dict[str, ProfileFact] = {}

    def upsert_fact(self, fact: ProfileFact) -> ProfileFact:
        item = fact.normalized()
        self._facts[item.fact_id] = item
        return item

    def list_facts(self) -> list[ProfileFact]:
        return sorted(self._facts.values(), key=lambda item: (item.fact_type, item.value, item.fact_id))

    def profile(self) -> CandidateProfile:
        return CandidateProfile(profile_id=self.profile_id, facts=tuple(self.list_facts()))


class PostgresProfileRepository:
    def __init__(self, dsn: str, profile_id: str = "default") -> None:
        self.dsn = str(dsn or "").strip()
        self.profile_id = str(profile_id or "default").strip() or "default"
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def migrate(self) -> None:
        apply_migrations(self.dsn)

    def upsert_fact(self, fact: ProfileFact) -> ProfileFact:
        item = fact.normalized()
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_profile_facts (
                        profile_id, fact_id, fact_type, value, normalized_value, source,
                        approved, confidence, tags, created_at, metadata, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::timestamptz, %s, now()
                    )
                    ON CONFLICT (profile_id, fact_id) DO UPDATE SET
                        fact_type = EXCLUDED.fact_type,
                        value = EXCLUDED.value,
                        normalized_value = EXCLUDED.normalized_value,
                        source = EXCLUDED.source,
                        approved = EXCLUDED.approved,
                        confidence = EXCLUDED.confidence,
                        tags = EXCLUDED.tags,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    (
                        self.profile_id,
                        item.fact_id,
                        item.fact_type,
                        item.value,
                        item.to_dict()["normalized_value"],
                        item.source,
                        item.approved,
                        item.confidence,
                        Jsonb(list(item.tags)),
                        item.created_at,
                        Jsonb(dict(item.metadata)),
                    ),
                )
            conn.commit()
        return item

    @staticmethod
    def _from_row(row) -> ProfileFact:
        return ProfileFact(
            fact_id=str(row[0]),
            fact_type=str(row[1]),
            value=str(row[2]),
            source=str(row[3]),
            approved=bool(row[4]),
            confidence=float(row[5]),
            tags=tuple(row[6] or ()),
            created_at=row[7].isoformat() if row[7] else "",
            metadata=dict(row[8] or {}),
        ).normalized()

    def list_facts(self) -> list[ProfileFact]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT fact_id, fact_type, value, source, approved, confidence,
                           tags, created_at, metadata
                    FROM smartploy_profile_facts
                    WHERE profile_id = %s
                    ORDER BY fact_type, value, fact_id
                    """,
                    (self.profile_id,),
                )
                rows = cur.fetchall()
        return [self._from_row(row) for row in rows]

    def profile(self) -> CandidateProfile:
        return CandidateProfile(profile_id=self.profile_id, facts=tuple(self.list_facts()))

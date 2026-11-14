"""Persistence for Smartploy candidate profile evidence."""

from __future__ import annotations

from typing import Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .profile import CandidateProfile, ProfileFact
from .profile_application_answers import canonical_question, decode_profile_answer
from .storage import apply_migrations


class ProfileRepository(Protocol):
    profile_id: str
    def upsert_fact(self, fact: ProfileFact) -> ProfileFact: ...
    def list_facts(self) -> list[ProfileFact]: ...
    def delete_fact(self, fact_id: str) -> bool: ...
    def profile(self) -> CandidateProfile: ...


class MemoryProfileRepository:
    def __init__(self, profile_id: str = "default") -> None:
        self.profile_id = profile_id
        self._facts: dict[str, ProfileFact] = {}

    def upsert_fact(self, fact: ProfileFact) -> ProfileFact:
        item = fact.normalized()
        if item.fact_type == "application_answer":
            desired = canonical_question(decode_profile_answer(item.value)["question"])
            for fact_id, existing in list(self._facts.items()):
                if existing.fact_type != "application_answer" or fact_id == item.fact_id:
                    continue
                try:
                    previous = canonical_question(decode_profile_answer(existing.value)["question"])
                except ValueError:
                    continue
                if previous == desired:
                    del self._facts[fact_id]
        self._facts[item.fact_id] = item
        return item

    def delete_fact(self, fact_id: str) -> bool:
        return self._facts.pop(fact_id, None) is not None

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
                if item.fact_type == "application_answer":
                    # One owner-scoped transaction: replacement must use the
                    # SERVER's Python Unicode casefold and avoid competing
                    # answers appearing during concurrent browser sessions.
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                        (self.profile_id, "application_answer"),
                    )
                    desired = canonical_question(
                        decode_profile_answer(item.value)["question"]
                    )
                    cur.execute(
                        """
                        SELECT fact_id, value FROM smartploy_profile_facts
                        WHERE profile_id = %s AND fact_type = 'application_answer'
                        """,
                        (self.profile_id,),
                    )
                    replacing = []
                    for fact_id, value in cur.fetchall():
                        if str(fact_id) == item.fact_id:
                            continue
                        try:
                            question = decode_profile_answer(value)["question"]
                        except ValueError:
                            continue
                        if canonical_question(question) == desired:
                            replacing.append(str(fact_id))
                    if replacing:
                        cur.execute(
                            """
                            DELETE FROM smartploy_profile_facts
                            WHERE profile_id = %s AND fact_id = ANY(%s)
                            """,
                            (self.profile_id, replacing),
                        )
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

    def delete_fact(self, fact_id: str) -> bool:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM smartploy_profile_facts WHERE profile_id = %s AND fact_id = %s",
                    (self.profile_id, fact_id),
                )
                removed = cur.rowcount > 0
        return removed

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

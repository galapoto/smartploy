import os

import pytest
from psycopg import connect

from smartploy.profile import ProfileFact
from smartploy.profile_storage import PostgresProfileRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def repository():
    repo = PostgresProfileRepository(DSN)
    repo.migrate()
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE smartploy_profile_facts")
        conn.commit()
    return repo


def test_profile_facts_persist_with_approval_and_provenance(repository):
    approved = repository.upsert_fact(
        ProfileFact(
            fact_type="skill",
            value="Python",
            source="master-cv",
            approved=True,
            confidence=0.95,
            tags=("data",),
        )
    )
    repository.upsert_fact(
        ProfileFact(
            fact_type="skill",
            value="Rust",
            source="unverified-note",
            approved=False,
        )
    )

    reloaded = PostgresProfileRepository(DSN).profile()
    assert len(reloaded.facts) == 2
    assert reloaded.approved_evidence()["approved_fact_count"] == 1
    assert reloaded.approved_facts[0].fact_id == approved.fact_id
    assert reloaded.approved_facts[0].source == "master-cv"

import os

import pytest
from psycopg import connect

from smartploy.domain import SourceObservation, SourcePolicy
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def repository():
    repo = PostgresJobRepository(DSN)
    repo.migrate()
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE smartploy_application_events,
                         smartploy_applications,
                         smartploy_application_preparations,
                         smartploy_source_observations,
                         smartploy_source_health,
                         smartploy_jobs
                RESTART IDENTITY
                """
            )
        conn.commit()
    return repo


def policy():
    return SourcePolicy(
        source_id="test-feed",
        display_name="Test Feed",
        source_class="test",
        allowed_modes=("feed",),
    )


def observation(observed_at, suffix=""):
    return SourceObservation(
        source_id="test-feed",
        source_mode="feed",
        source_url=f"https://jobs.example.fi/roles/42?utm_source={suffix or 'first'}",
        raw_text="Example Oy Junior Data Analyst Python SQL",
        payload={
            "company": "Example Oy",
            "role_title": "Junior Data Analyst",
            "description": "Python SQL analytics",
            "location": "Helsinki",
            "work_mode": "hybrid",
            "application_url": "https://jobs.example.fi/roles/42",
        },
        observed_at=observed_at,
        posted_at="2026-10-09T12:00:00+00:00",
        source_external_id="42",
    )


def test_postgres_upsert_preserves_first_seen_and_persists_observations(repository):
    service = SmartployService(repository=repository)
    service.register_source(policy())

    first = service.ingest(observation("2026-10-10T00:00:00+00:00", "a"))
    second = service.ingest(observation("2026-10-10T02:00:00+00:00", "b"))

    assert first.candidate is not None
    assert second.candidate is not None
    assert first.candidate.canonical_key == second.candidate.canonical_key
    assert second.candidate.first_seen_at == "2026-10-10T00:00:00+00:00"
    assert second.candidate.last_seen_at == "2026-10-10T02:00:00+00:00"
    assert len(repository.values()) == 1
    assert repository.storage_status() == {"mode": "postgres", "ready": True}

    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM smartploy_source_observations")
            assert cur.fetchone()[0] == 2


def test_source_health_survives_repository_recreation(repository):
    first = repository.record_source_attempt(
        "kuntarekry",
        status="failed",
        item_count=0,
        parser_version="v1",
        attempted_at="2026-10-10T01:00:00+00:00",
        error="network failed",
    )
    assert first.consecutive_failures == 1

    second_repo = PostgresJobRepository(DSN)
    loaded = second_repo.get_source_health("kuntarekry")
    assert loaded is not None
    assert loaded.status == "failed"
    assert loaded.consecutive_failures == 1
    assert loaded.last_failure_at.startswith("2026-10-10T01:00:00")

    recovered = second_repo.record_source_attempt(
        "kuntarekry",
        status="healthy",
        item_count=0,
        parser_version="v1",
        attempted_at="2026-10-10T02:00:00+00:00",
    )
    assert recovered.status == "healthy"
    assert recovered.last_item_count == 0
    assert recovered.consecutive_failures == 0
    assert recovered.last_success_at.startswith("2026-10-10T02:00:00")

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
                "TRUNCATE smartploy_application_events, smartploy_applications, "
                "smartploy_application_preparations, smartploy_source_observations, "
                "smartploy_source_health, smartploy_jobs RESTART IDENTITY"
            )
        conn.commit()
    return repo


def observation(description, observed_at):
    return SourceObservation(
        source_id="lever-eu-acme",
        source_mode="api",
        source_url="https://jobs.lever.co/acme/job-1",
        raw_text="Data Analyst " + description,
        payload={
            "company": "Acme Oy",
            "role_title": "Data Analyst",
            "description": description,
            "location": "Helsinki",
            "application_url": "https://jobs.lever.co/acme/job-1/apply",
        },
        observed_at=observed_at,
        source_external_id="job-1",
    )


def test_postgres_external_id_rebinds_changed_content_to_existing_job(repository):
    service = SmartployService(repository=repository)
    service.register_source(
        SourcePolicy("lever-eu-acme", "Acme", "direct_employer_ats", ("api",))
    )

    first = service.ingest(observation("Short description", "2026-10-10T08:00:00+00:00"))
    second = service.ingest(
        observation(
            "Completely revised longer description with Python SQL Power BI analytics",
            "2026-10-10T09:00:00+00:00",
        )
    )
    assert first.candidate is not None and second.candidate is not None
    assert first.candidate.canonical_key == second.candidate.canonical_key
    assert len(repository.values()) == 1
    assert repository.active_source_external_ids("lever-eu-acme") == {"job-1"}
    assert (
        repository.canonical_key_for_source_external_id("lever-eu-acme", "job-1")
        == first.candidate.canonical_key
    )

    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(DISTINCT canonical_key), count(*) "
                "FROM smartploy_source_observations "
                "WHERE source_id = 'lever-eu-acme' AND source_external_id = 'job-1'"
            )
            canonical_count, observation_count = cur.fetchone()
    assert canonical_count == 1
    assert observation_count == 2


def test_retired_external_id_is_not_reused_as_live_identity_anchor(repository):
    service = SmartployService(repository=repository)
    service.register_source(
        SourcePolicy("lever-eu-acme", "Acme", "direct_employer_ats", ("api",))
    )
    first = service.ingest(observation("Old description", "2026-10-10T08:00:00+00:00"))
    assert first.candidate is not None
    repository.retire_source_external_id(
        "lever-eu-acme",
        "job-1",
        archived_at="2026-10-10T09:00:00+00:00",
    )
    assert repository.canonical_key_for_source_external_id("lever-eu-acme", "job-1") is None
    assert repository.active_source_external_ids("lever-eu-acme") == set()

import os

import pytest
from psycopg import connect

from smartploy.service import SmartployService
from smartploy.sources.jobmarket_finland import (
    TEST_ENDPOINT,
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
    parse_ndjson,
)
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


PUBLISHED_LINE = b"""{"metadata":{"externalId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","created":"2026-10-09T08:00:00Z","lastModified":"2026-10-10T01:00:00Z"},"client":{"company":"Example Oy"},"owner":{"company":{"fi":"Example Oy"}},"position":{"title":{"fi":"Data-analyytikko"},"jobDescription":{"fi":"Python SQL analytics"}},"location":{"workplacePostOffice":"Helsinki"},"application":{"published":"2026-10-09T09:00:00Z","expires":"2026-10-25T20:59:00Z","url":{"fi":"https://jobs.example.fi/data-analyst"}}}\n"""


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


def test_postgres_retirement_redacts_jobmarket_source_payload(repository):
    settings = JobMarketFinlandSettings(
        environment="test",
        endpoint=TEST_ENDPOINT,
        subscription_key="fixture-secret",
    )
    adapter = JobMarketFinlandAdapter(settings)
    service = SmartployService(repository=repository)
    service.register_source(adapter.policy())

    observation = parse_ndjson(
        PUBLISHED_LINE,
        status="PUBLISHED",
        endpoint=TEST_ENDPOINT,
        observed_at="2026-10-10T02:00:00+00:00",
    ).observations[0]
    result = service.ingest(observation)
    assert result.candidate is not None

    retired = repository.retire_source_external_id(
        "job-market-finland",
        observation.source_external_id,
        archived_at="2026-10-10T03:00:00+00:00",
    )
    assert retired is not None
    assert retired.source_current is False

    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_url, raw_text, payload FROM smartploy_source_observations "
                "WHERE source_id = 'job-market-finland' AND source_external_id = %s",
                (observation.source_external_id,),
            )
            source_url, raw_text, payload = cur.fetchone()
    assert source_url == ""
    assert raw_text == ""
    assert payload["retired"] is True
    assert "fixture-secret" not in str(payload)

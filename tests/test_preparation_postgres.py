import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from psycopg import connect

from smartploy.domain import SourceObservation, SourcePolicy
from smartploy.preparation_storage import PostgresPreparationRepository, with_runtime
from smartploy.preparations import build_preparation
from smartploy.profile import ProfileFact
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.scoring import score_candidate
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def repositories():
    jobs = PostgresJobRepository(DSN)
    jobs.migrate()
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE smartploy_application_events,
                         smartploy_applications,
                         smartploy_application_preparations,
                         smartploy_source_observations,
                         smartploy_source_health,
                         smartploy_profile_facts,
                         smartploy_jobs
                RESTART IDENTITY
                """
            )
        conn.commit()
    return jobs, PostgresProfileRepository(DSN), PostgresPreparationRepository(DSN)


def test_preparation_survives_repository_recreation(repositories):
    jobs, profiles, preparations = repositories
    profiles.upsert_fact(ProfileFact("skill", "Python", "cv", approved=True))
    profiles.upsert_fact(ProfileFact("skill", "SQL", "cv", approved=True))

    service = SmartployService(repository=jobs, profile_repository=profiles, preparation_repository=preparations)
    service.register_source(SourcePolicy("company-careers", "Company Careers", "company_careers", ("feed",)))
    ingested = service.ingest(
        SourceObservation(
            source_id="company-careers",
            source_mode="feed",
            source_url="https://jobs.example.fi/roles/42",
            raw_text="Example Data Analyst Python SQL",
            payload={
                "company": "Example Oy",
                "role_title": "Data Analyst",
                "description": "Python SQL",
                "requirements": ["Python", "SQL"],
            },
            observed_at="2026-10-10T01:00:00+00:00",
            posted_at="2026-10-10T01:00:00+00:00",
        )
    )
    assert ingested.candidate is not None

    profile = profiles.profile()
    score = score_candidate(
        ingested.candidate,
        profile,
        now=datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc),
    )
    package = build_preparation(ingested.candidate, profile, score)
    stored, created = preparations.create_or_get(package)
    assert created is True

    queued = with_runtime(
        stored,
        status="queued",
        obum_job_id="obum-job-persisted",
        obum_client_request_id="smartploy:test:request",
        updated_at="2026-10-10T03:00:00+00:00",
    )
    preparations.save(queued)

    reloaded = PostgresPreparationRepository(DSN).get(package.package_id)
    assert reloaded is not None
    assert reloaded.status == "queued"
    assert reloaded.obum_job_id == "obum-job-persisted"
    assert reloaded.job_snapshot_sha256 == package.job_snapshot_sha256
    assert reloaded.evidence_sha256 == package.evidence_sha256

    same, created_again = PostgresPreparationRepository(DSN).create_or_get(package)
    assert created_again is False
    assert same.package_id == package.package_id

    # Completed history is newer than the unfinished request, but must not
    # consume the refresh batch. SQL must filter before applying LIMIT.
    newer = (datetime.fromisoformat(queued.updated_at) + timedelta(days=1)).isoformat()
    for index in range(4):
        completed_source = replace(
            package, package_id=f"{package.package_id}-completed-{index}",
            requested_at=newer, updated_at=newer,
        )
        finished, was_new = preparations.create_or_get(completed_source)
        assert was_new
        preparations.save(with_runtime(
            finished, status="completed", obum_job_id=f"remote-completed-{index}",
            updated_at=newer,
        ))
    assert all(item.status == "completed" for item in preparations.list(limit=4))
    assert [item.package_id for item in preparations.list_refresh_candidates(limit=1)] == [
        package.package_id
    ]

    # Fresh polling must rotate: the least recently checked active package is first.
    second_source = replace(
        package, package_id=f"{package.package_id}-other-tenant",
        profile_id="other-synthetic-tenant", requested_at=newer, updated_at=newer,
    )
    second, was_new = preparations.create_or_get(second_source)
    assert was_new
    preparations.save(with_runtime(
        second, status="queued", obum_job_id="remote-second", updated_at=newer,
    ))
    assert [item.package_id for item in preparations.list_refresh_candidates(limit=2)] == [
        package.package_id, second_source.package_id
    ]
    after = (datetime.fromisoformat(newer) + timedelta(seconds=1)).isoformat()
    preparations.save(with_runtime(queued, status="running", updated_at=after))
    assert [item.package_id for item in preparations.list_refresh_candidates(limit=1)] == [
        second_source.package_id
    ]
    assert [item.package_id for item in PostgresPreparationRepository(
        DSN, profile_id="other-synthetic-tenant"
    ).list_refresh_candidates(limit=10)] == [second_source.package_id]

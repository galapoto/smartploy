import os

import pytest
from psycopg import connect

from smartploy.application_storage import PostgresApplicationRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.preparation_storage import PostgresPreparationRepository, with_runtime
from smartploy.preparations import build_preparation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.scoring import ScoreResult
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
    return jobs, PostgresPreparationRepository(DSN), PostgresApplicationRepository(DSN)


def test_crm_record_and_events_survive_restart_and_resync_is_idempotent(repositories):
    jobs, preparations, applications = repositories
    normalized = normalize_observation(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Data Analyst Python",
            payload={
                "company": "Example Oy",
                "role_title": "Data Analyst",
                "description": "Python analytics",
            },
            observed_at="2026-10-10T01:00:00+00:00",
        ),
        SourcePolicy("manual", "Manual", "manual", ("manual",)),
    )
    assert normalized.candidate is not None
    candidate = jobs.upsert(normalized.candidate)

    profile = CandidateProfile(
        facts=(ProfileFact("skill", "Python", "cv", approved=True),)
    )
    score = ScoreResult(
        canonical_key=candidate.canonical_key,
        fit_score=90,
        priority_score=90,
        queue="auto_prepare",
        fit_breakdown={"skill_overlap": 100},
        priority_breakdown={"fit": 90},
        matched_evidence_ids=(profile.approved_facts[0].fact_id,),
        matched_requirements=(),
        mandatory_gaps=(),
        preferred_gaps=(),
        prepare_recommended=True,
    )
    base = build_preparation(
        candidate,
        profile,
        score,
        requested_at="2026-10-10T01:30:00+00:00",
    )
    stored, created = preparations.create_or_get(base)
    assert created is True

    queued = with_runtime(
        stored,
        status="queued",
        obum_job_id="obum-postgres-1",
        updated_at="2026-10-10T02:00:00+00:00",
    )
    queued = preparations.save(queued)
    preparing = applications.sync_preparation(queued)
    applications.sync_preparation(queued)
    assert preparing.state == "preparing"
    assert len(applications.events(preparing.application_id)) == 1

    completed = with_runtime(
        queued,
        status="completed",
        result={
            "schema": "smartploy.application.draft.v1",
            "fit_summary": {},
            "cv_tailoring": {},
            "cover_letter": "draft",
            "application_answers": [],
            "gap_framing": [],
            "risks": [],
            "review_checklist": [],
        },
        raw_output="{}",
        completed_at="2026-10-10T03:00:00+00:00",
        updated_at="2026-10-10T03:00:00+00:00",
    )
    completed = preparations.save(completed)
    ready = applications.sync_preparation(completed)
    assert ready.state == "ready_for_review"
    assert ready.submitted_at == ""

    reloaded_repo = PostgresApplicationRepository(DSN)
    reloaded = reloaded_repo.get(ready.application_id)
    assert reloaded is not None
    assert reloaded.state == "ready_for_review"
    assert reloaded.has_been_submitted is False
    events = reloaded_repo.events(ready.application_id)
    assert len(events) == 2
    assert [event.to_state for event in events] == ["preparing", "ready_for_review"]

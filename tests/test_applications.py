from smartploy.applications import (
    ApplicationRecord,
    EXTERNAL_APPLICATION_STATES,
    MemoryError if False else ApplicationRecord,
    apply_preparation_to_application,
)
from smartploy.application_storage import MemoryApplicationRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.preparation_storage import with_runtime
from smartploy.preparations import build_preparation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.scoring import ScoreResult
from smartploy.service import SmartployService


def candidate():
    result = normalize_observation(
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
    assert result.candidate is not None
    return result.candidate


def package(status="queued", updated_at="2026-10-10T02:00:00+00:00"):
    item = candidate()
    profile = CandidateProfile(
        facts=(ProfileFact("skill", "Python", "cv", approved=True),)
    )
    score = ScoreResult(
        canonical_key=item.canonical_key,
        fit_score=90,
        priority_score=90,
        queue="auto_prepare",
        fit_breakdown={"mandatory_requirements": 100},
        priority_breakdown={"fit": 90},
        matched_evidence_ids=(profile.approved_facts[0].fact_id,),
        matched_requirements=("Python",),
        mandatory_gaps=(),
        preferred_gaps=(),
        prepare_recommended=True,
    )
    base = build_preparation(
        item,
        profile,
        score,
        requested_at="2026-10-10T01:30:00+00:00",
    )
    return with_runtime(
        base,
        status=status,
        obum_job_id="obum-1",
        updated_at=updated_at,
        completed_at=updated_at if status in {"completed", "completed_unparsed", "failed", "cancelled"} else "",
    )


def test_preparation_sync_is_idempotent_and_never_claims_submission():
    repo = MemoryApplicationRepository()
    queued = package("queued")
    first = repo.sync_preparation(queued)
    again = repo.sync_preparation(queued)

    assert first.state == "preparing"
    assert again.state == "preparing"
    assert first.submitted_at == ""
    assert len(repo.events(first.application_id)) == 1

    completed = package("completed", "2026-10-10T03:00:00+00:00")
    ready = repo.sync_preparation(completed)
    assert ready.state == "ready_for_review"
    assert ready.has_been_submitted is False
    assert len(repo.events(first.application_id)) == 2

    assert "submitted" in EXTERNAL_APPLICATION_STATES
    assert all(event.to_state != "submitted" for event in repo.events(first.application_id))


def test_preparation_failure_and_unparsed_output_are_distinct_review_states():
    repo = MemoryApplicationRepository()
    needs_review = repo.sync_preparation(package("completed_unparsed"))
    assert needs_review.state == "needs_review"

    blocked = repo.sync_preparation(package("failed", "2026-10-10T04:00:00+00:00"))
    assert blocked.state == "preparation_blocked"
    assert blocked.has_been_submitted is False


def test_preparation_sync_cannot_regress_externally_evidenced_state():
    prep = package("completed", "2026-10-10T05:00:00+00:00")
    submitted = ApplicationRecord(
        application_id="app-test",
        canonical_key=prep.canonical_key,
        package_id=prep.package_id,
        state="submitted",
        created_at="2026-10-10T01:00:00+00:00",
        updated_at="2026-10-10T04:00:00+00:00",
        submitted_at="2026-10-10T04:00:00+00:00",
        external_confirmation_id="confirm-1",
    )
    updated = apply_preparation_to_application(submitted, prep)
    assert updated.state == "submitted"
    assert updated.submitted_at == "2026-10-10T04:00:00+00:00"
    assert updated.external_confirmation_id == "confirm-1"


def test_application_summary_distinguishes_review_from_applied():
    repo = MemoryApplicationRepository()
    repo.sync_preparation(package("completed"))
    service = SmartployService(application_repository=repo)
    summary = service.application_summary()
    assert summary["awaiting_review"] == 1
    assert summary["actually_submitted"] == 0

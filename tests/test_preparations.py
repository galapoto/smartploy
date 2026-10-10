import json
from datetime import datetime, timezone

import httpx
import pytest

from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.obumai import ObumAIClient, ObumAISettings
from smartploy.preparation_storage import MemoryPreparationRepository
from smartploy.preparations import (
    DRAFT_RESULT_SCHEMA,
    PreparationNotEligible,
    build_preparation,
)
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.profile_storage import MemoryProfileRepository
from smartploy.scoring import score_candidate
from smartploy.service import SmartployService


NOW = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


def candidate(*, observed_at="2026-10-10T01:00:00+00:00", posted_at="2026-10-10T01:00:00+00:00", requirements=None):
    result = normalize_observation(
        SourceObservation(
            source_id="company-careers",
            source_mode="feed",
            source_url="https://jobs.example.fi/roles/42",
            raw_text="Example Oy Data Analyst Python SQL",
            payload={
                "company": "Example Oy",
                "role_title": "Junior Data Analyst",
                "description": "Data analysis using Python and SQL.",
                "location": "Helsinki",
                "work_mode": "hybrid",
                "requirements": list(requirements or ("Python", "SQL")),
                "application_url": "https://jobs.example.fi/roles/42",
                "seniority": "junior",
            },
            observed_at=observed_at,
            posted_at=posted_at,
            source_external_id="42",
        ),
        SourcePolicy(
            "company-careers",
            "Company Careers",
            "company_careers",
            ("feed",),
        ),
    )
    assert result.candidate is not None
    return result.candidate


def profile_repo(*, approved_extra=None, unapproved_extra=None):
    repo = MemoryProfileRepository()
    for fact in (
        ProfileFact("skill", "Python", "cv", approved=True),
        ProfileFact("skill", "SQL", "cv", approved=True),
        ProfileFact("location", "Helsinki", "confirmed", approved=True, tags=("location",)),
        ProfileFact("preference", "hybrid", "confirmed", approved=True, tags=("work_mode",)),
        ProfileFact("preference", "junior", "confirmed", approved=True, tags=("seniority",)),
        ProfileFact("preference", "Data Analyst", "confirmed", approved=True, tags=("role", "career")),
    ):
        repo.upsert_fact(fact)
    if approved_extra:
        repo.upsert_fact(ProfileFact("skill", approved_extra, "confirmed", approved=True))
    if unapproved_extra:
        repo.upsert_fact(ProfileFact("skill", unapproved_extra, "note", approved=False))
    return repo


def valid_draft():
    return {
        "schema": DRAFT_RESULT_SCHEMA,
        "fit_summary": {"summary": "Strong match", "strengths": ["Python"], "gaps": []},
        "cv_tailoring": {
            "headline": "Junior Data Analyst",
            "summary": "Evidence-backed analytics profile.",
            "skills_to_emphasize": ["Python", "SQL"],
            "experience_edits": [],
            "do_not_claim": [],
        },
        "cover_letter": "Evidence-backed draft cover letter.",
        "application_answers": [],
        "gap_framing": [],
        "risks": [],
        "review_checklist": ["Review before use"],
    }


def test_package_identity_ignores_freshness_and_unapproved_fact_changes():
    first = candidate()
    later = candidate(
        observed_at="2026-10-10T05:00:00+00:00",
        posted_at="2026-10-10T04:00:00+00:00",
    )
    base_profile = profile_repo().profile()
    note_profile = profile_repo(unapproved_extra="Rust").profile()

    first_score = score_candidate(first, base_profile, now=NOW)
    later_score = score_candidate(later, note_profile, now=NOW)
    first_package = build_preparation(first, base_profile, first_score)
    later_package = build_preparation(later, note_profile, later_score)

    assert first_package.package_id == later_package.package_id
    assert first_package.job_snapshot_sha256 == later_package.job_snapshot_sha256
    assert first_package.evidence_sha256 == later_package.evidence_sha256


def test_approved_evidence_change_mints_new_package():
    item = candidate()
    base_profile = profile_repo().profile()
    changed_profile = profile_repo(approved_extra="Azure").profile()

    base = build_preparation(item, base_profile, score_candidate(item, base_profile, now=NOW))
    changed = build_preparation(item, changed_profile, score_candidate(item, changed_profile, now=NOW))
    assert base.package_id != changed.package_id
    assert base.evidence_sha256 != changed.evidence_sha256


def test_prepare_is_idempotent_and_refresh_persists_valid_obum_draft():
    seen_posts = []

    def handler(request):
        if request.method == "POST" and request.url.path == "/api/v1/agent-jobs":
            seen_posts.append(json.loads(request.content))
            return httpx.Response(
                201,
                json={
                    "job": {"id": "obum-job-1", "state": "queued"},
                    "created": True,
                    "execution_started": False,
                    "external_actions_performed": 0,
                },
            )
        if request.method == "GET" and request.url.path == "/api/v1/agent-jobs/obum-job-1":
            return httpx.Response(
                200,
                json={
                    "id": "obum-job-1",
                    "state": "completed",
                    "output_text": json.dumps(valid_draft()),
                    "external_actions_performed": 0,
                },
            )
        return httpx.Response(404)

    obum = ObumAIClient(
        ObumAISettings(base_url="https://obum.example"),
        http_client=httpx.Client(
            base_url="https://obum.example",
            transport=httpx.MockTransport(handler),
        ),
    )
    service = SmartployService(
        profile_repository=profile_repo(),
        preparation_repository=MemoryPreparationRepository(),
        obumai=obum,
    )
    service.register_source(SourcePolicy("company-careers", "Company Careers", "company_careers", ("feed",)))
    ingested = service.ingest(
        SourceObservation(
            source_id="company-careers",
            source_mode="feed",
            source_url="https://jobs.example.fi/roles/42",
            raw_text="Example Oy Data Analyst Python SQL",
            payload={
                "company": "Example Oy",
                "role_title": "Junior Data Analyst",
                "description": "Data analysis using Python and SQL.",
                "location": "Helsinki",
                "work_mode": "hybrid",
                "requirements": ["Python", "SQL"],
                "application_url": "https://jobs.example.fi/roles/42",
                "seniority": "junior",
            },
            observed_at="2026-10-10T01:00:00+00:00",
            posted_at="2026-10-10T01:00:00+00:00",
        )
    )
    assert ingested.candidate is not None

    first = service.prepare_job(ingested.candidate.canonical_key, now=NOW)
    second = service.prepare_job(ingested.candidate.canonical_key, now=NOW)
    assert first.package_id == second.package_id
    assert first.status == "queued"
    assert len(seen_posts) == 1
    assert seen_posts[0]["agent_id"] == "obum-assistant"
    assert '"final_submit_authorized":false' in seen_posts[0]["prompt"]
    assert "Evidence-backed draft cover letter" not in seen_posts[0]["prompt"]

    completed = service.refresh_preparation(first.package_id)
    assert completed.status == "completed"
    assert completed.obum_job_id == "obum-job-1"
    assert completed.result["schema"] == DRAFT_RESULT_SCHEMA
    assert completed.result["cover_letter"] == "Evidence-backed draft cover letter."
    assert completed.to_dict()["authority"]["may_submit"] is False


def test_completed_invalid_json_is_preserved_as_unparsed():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(201, json={"job": {"id": "obum-2", "state": "queued"}})
        return httpx.Response(
            200,
            json={"id": "obum-2", "state": "completed", "output_text": "not-json"},
        )

    obum = ObumAIClient(
        ObumAISettings(base_url="https://obum.example"),
        http_client=httpx.Client(
            base_url="https://obum.example",
            transport=httpx.MockTransport(handler),
        ),
    )
    service = SmartployService(
        profile_repository=profile_repo(),
        preparation_repository=MemoryPreparationRepository(),
        obumai=obum,
    )
    service.register_source(SourcePolicy("company-careers", "Company Careers", "company_careers", ("feed",)))
    observation = SourceObservation(
        source_id="company-careers",
        source_mode="feed",
        source_url="https://jobs.example.fi/roles/42",
        raw_text="Example Oy Data Analyst Python SQL",
        payload={
            "company": "Example Oy",
            "role_title": "Junior Data Analyst",
            "description": "Python SQL",
            "requirements": ["Python", "SQL"],
        },
        observed_at="2026-10-10T01:00:00+00:00",
        posted_at="2026-10-10T01:00:00+00:00",
    )
    created = service.ingest(observation)
    assert created.candidate is not None
    package = service.prepare_job(created.candidate.canonical_key, now=NOW)
    refreshed = service.refresh_preparation(package.package_id)
    assert refreshed.status == "completed_unparsed"
    assert refreshed.raw_output == "not-json"
    assert refreshed.result == {}


def test_mandatory_gap_blocks_automatic_preparation():
    item = candidate(requirements=("Python", "SQL", "Azure"))
    repo = profile_repo()
    score = score_candidate(item, repo.profile(), now=NOW)
    assert "Azure" in score.mandatory_gaps

    service = SmartployService(profile_repository=repo, preparation_repository=MemoryPreparationRepository())
    service.repository.upsert(item)
    with pytest.raises(PreparationNotEligible, match="mandatory"):
        service.prepare_job(item.canonical_key, now=NOW)

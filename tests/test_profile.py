import json

import httpx

from smartploy.domain import SourceObservation, SourcePolicy
from smartploy.obumai import ObumAIClient, ObumAISettings
from smartploy.profile import CandidateProfile, ProfileFact, facts_from_json
from smartploy.profile_storage import MemoryProfileRepository
from smartploy.service import SmartployService


def test_only_approved_facts_enter_evidence():
    profile = CandidateProfile(
        facts=(
            ProfileFact("skill", "Python", "cv", approved=True),
            ProfileFact("skill", "Rust", "note", approved=False),
        )
    )
    evidence = profile.approved_evidence()
    values = [item["value"] for item in evidence["facts"]["skill"]]
    assert values == ["Python"]
    assert evidence["approved_fact_count"] == 1
    assert "Rust" not in json.dumps(evidence)


def test_json_profile_import_keeps_approval_state():
    facts = facts_from_json(
        {
            "facts": [
                {"fact_type": "language", "value": "Finnish", "source": "confirmed", "approved": True},
                {"fact_type": "skill", "value": "Go", "source": "note", "approved": False},
            ]
        }
    )
    assert len(facts) == 2
    assert sum(1 for item in facts if item.approved) == 1


def test_service_obumai_path_uses_approved_repository_evidence_only():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={"job": {"job_id": "1", "state": "queued"}, "created": True, "external_actions_performed": 0},
        )

    profile_repo = MemoryProfileRepository()
    profile_repo.upsert_fact(ProfileFact("skill", "Python", "cv", approved=True))
    profile_repo.upsert_fact(ProfileFact("skill", "Rust", "note", approved=False))

    obum = ObumAIClient(
        ObumAISettings(base_url="https://obum.example"),
        http_client=httpx.Client(base_url="https://obum.example", transport=httpx.MockTransport(handler)),
    )
    service = SmartployService(profile_repository=profile_repo, obumai=obum)
    service.register_source(SourcePolicy("manual", "Manual", "manual", ("manual",)))
    created = service.ingest(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Data Analyst",
            payload={"company": "Example", "role_title": "Data Analyst", "description": "Python"},
            observed_at="2026-10-10T00:00:00+00:00",
        )
    )
    assert created.candidate is not None
    service.submit_obumai(created.candidate.canonical_key, action="fit_analysis")

    prompt = seen[0]["prompt"]
    assert "Python" in prompt
    assert "Rust" not in prompt

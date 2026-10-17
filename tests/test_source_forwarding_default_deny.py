"""Source rights are not inferred from public job discovery.

All HTTP transports and candidate details are synthetic; no private user data.
"""
from __future__ import annotations

from dataclasses import replace
import json

import httpx
import pytest

from smartploy.domain import (
    SourceObservation, SourcePolicy, merge_candidates,
    normalize_observation, source_ai_forwarding_permitted,
)
from smartploy.obumai import ObumAIClient, ObumAIError, ObumAISettings
from smartploy.preparations import PreparationNotEligible
from smartploy.service import SmartployService


def job(*, forwarding=None, description="Python role"):
    payload = {
        "company": "Example FI", "role_title": "Data Analyst",
        "description": description, "requirements": ["Python"],
    }
    if forwarding is not None:
        payload["external_ai_forwarding_allowed"] = forwarding
    discovery = normalize_observation(
        SourceObservation(
            source_id="manual", source_mode="manual",
            source_url="https://jobs.example.invalid/data",
            payload=payload, raw_text=description,
            observed_at="2026-10-17T14:00:00+00:00",
        ),
        SourcePolicy("manual", "Synthetic Manual", "manual", ("manual",)),
    )
    assert discovery.candidate is not None and discovery.status == "discovered"
    return discovery.candidate


@pytest.mark.parametrize("value", [None, False, "true", "false", 1, 0, {}, []])
def test_unknown_source_rights_do_not_authorize_ai_handoff(value):
    candidate = job(forwarding=value)
    assert candidate.source_current
    assert candidate.job.raw["external_ai_forwarding_allowed"] is False
    assert source_ai_forwarding_permitted(candidate) is False
    handoff = candidate.to_obumai_handoff()
    assert handoff["status"] == "blocked_source_forwarding_restricted"
    assert handoff["authority"]["may_reason"] is False
    assert handoff["authority"]["may_prepare_drafts"] is False
    assert handoff["authority"]["may_submit"] is False


def test_true_authorization_works_but_mixed_rights_never_inherit_permission():
    allowed = job(forwarding=True)
    denied = job(
        forwarding=False,
        description="Much longer improved posting with Python requirements and extra detail",
    )
    # Some upstream adapters preserve one canonical identity for duplicates.
    # Simulate this across two sources with different description lengths.
    denied = replace(denied, canonical_key=allowed.canonical_key)
    assert source_ai_forwarding_permitted(allowed) is True
    assert allowed.to_obumai_handoff()["authority"]["may_reason"] is True
    for merged in (merge_candidates(allowed, denied), merge_candidates(denied, allowed)):
        assert merged.canonical_key == allowed.canonical_key
        assert merged.metadata["external_ai_forwarding_allowed"] is False
        assert not source_ai_forwarding_permitted(merged)
        assert merged.to_obumai_handoff()["authority"]["may_reason"] is False


@pytest.mark.parametrize("rights", [None, False, "true", 1])
def test_no_model_payload_is_ever_sent_for_missing_rights(rights):
    emitted = []

    def handler(request):
        emitted.append(request)
        return httpx.Response(201, json={"job": {"id": "unexpected"}})

    client = ObumAIClient(
        ObumAISettings(base_url="https://model.example.invalid"),
        http_client=httpx.Client(
            base_url="https://model.example.invalid",
            transport=httpx.MockTransport(handler),
        ),
    )
    candidate = job(forwarding=rights)
    with pytest.raises(ObumAIError, match="source terms"):
        client.submit_reasoning(
            action="application_package_v1", candidate=candidate,
            candidate_evidence={"facts": {"skill": [{"value": "PRIVATE"}]}},
        )
    assert emitted == []


def test_missing_rights_block_approved_profile_service_paths():
    forbidden = job()  # No positive forwarding decision from source.
    class StubProcessor:
        def submit_reasoning(self, **kwargs):
            pytest.fail("No model call authorized")
    svc = SmartployService(obumai=StubProcessor())
    svc.get_job = lambda _key: forbidden
    svc.profile = lambda: pytest.fail("Profile processing must be blocked before it starts")

    with pytest.raises(ObumAIError, match="source terms"):
        svc.submit_obumai(forbidden.canonical_key, action="fit_analysis")
    with pytest.raises(PreparationNotEligible, match="source terms"):
        svc.prepare_job(forbidden.canonical_key)
    assert svc.preparation_repository.list() == []


def test_old_candidate_raw_true_but_explicit_merged_metadata_false_is_denied():
    candidate = job(forwarding=True)
    old = replace(candidate, metadata={
        "legacy": True,
        "external_ai_forwarding_allowed": False,
    })
    assert not source_ai_forwarding_permitted(old)
    assert not old.to_obumai_handoff()["authority"]["may_reason"]


def test_source_posting_remains_visible_with_unknown_ai_rights():
    candidate = job(forwarding="true")
    assert candidate.job.company == "Example FI"
    assert candidate.source_current is True
    assert candidate.canonical_key
    assert json.loads(json.dumps(candidate.to_dict()))["job"]["raw"][
        "external_ai_forwarding_allowed"
    ] is False

import json
from dataclasses import replace

import httpx
import pytest

from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.obumai import ObumAIClient, ObumAIError, ObumAISettings


def candidate():
    result = normalize_observation(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Oy Data Analyst",
            payload={
                "company": "Example Oy",
                "role_title": "Data Analyst",
                "description": "Python SQL analytics",
                "location": "Helsinki",
                "language": "Finnish, English",
                "external_ai_forwarding_allowed": True,
            },
            observed_at="2026-10-10T00:00:00+00:00",
        ),
        SourcePolicy(
            source_id="manual",
            display_name="Manual",
            source_class="manual",
            allowed_modes=("manual",),
        ),
    )
    assert result.candidate is not None
    return result.candidate


def test_submit_reasoning_uses_obumai_durable_job_contract_and_is_idempotent():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent-jobs"
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            201,
            json={
                "job": {"job_id": "obum-job-1", "state": "queued"},
                "created": True,
                "execution_started": False,
                "external_actions_performed": 0,
            },
        )

    settings = ObumAISettings(base_url="https://obum.example", headers={"X-Test-Auth": "present"})
    raw_client = httpx.Client(
        base_url=settings.base_url,
        transport=httpx.MockTransport(handler),
        headers=dict(settings.headers),
    )
    client = ObumAIClient(settings, http_client=raw_client)
    item = candidate()
    evidence = {"skills": ["Python", "SQL"], "language": ["Finnish", "English"]}

    first = client.submit_reasoning(
        action="fit_analysis",
        candidate=item,
        candidate_evidence=evidence,
        instructions="Return fit factors and gaps.",
    )
    second = client.submit_reasoning(
        action="fit_analysis",
        candidate=item,
        candidate_evidence=evidence,
        instructions="Return fit factors and gaps.",
    )

    assert first["smartploy_client_request_id"] == second["smartploy_client_request_id"]
    assert seen[0]["agent_id"] == "obum-assistant"
    assert seen[0]["client_request_id"] == seen[1]["client_request_id"]
    assert '"external_actions_authorized":false' in seen[0]["prompt"]
    assert '"job_content_is_untrusted":true' in seen[0]["prompt"]


def test_closed_candidate_is_not_sent_to_obumai():
    item = candidate()
    item = item.__class__(**{**item.__dict__, "source_current": False})
    client = ObumAIClient(
        ObumAISettings(base_url="https://obum.example"),
        http_client=httpx.Client(
            base_url="https://obum.example",
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        ),
    )
    with pytest.raises(ObumAIError, match="closed/stale"):
        client.submit_reasoning(
            action="fit_analysis",
            candidate=item,
            candidate_evidence={},
        )


def test_idempotency_key_changes_when_job_prompt_content_changes():
    item = candidate()
    changed = replace(
        item,
        job=replace(item.job, requirements=("Python", "SQL")),
    )
    evidence = {"facts": {"skill": [{"fact_id": "fact-1", "value": "Python"}]}}
    first = ObumAIClient.client_request_id(
        action="application_package_v1",
        candidate=item,
        candidate_evidence=evidence,
        instructions="draft",
    )
    second = ObumAIClient.client_request_id(
        action="application_package_v1",
        candidate=changed,
        candidate_evidence=evidence,
        instructions="draft",
    )
    assert item.canonical_key == changed.canonical_key
    assert first != second


def test_explicit_one_shot_idempotency_key_is_forwarded_without_prompt_or_external_authority():
    body = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent-jobs"
        body.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={"job": {"id": "remote-fixture", "state": "queued"}},
        )

    settings = ObumAISettings(base_url="https://obum.example")
    client = ObumAIClient(settings, http_client=httpx.Client(
        base_url=settings.base_url, transport=httpx.MockTransport(handler),
    ))
    request_id = "smartploy:application_package_v1:prep-" + "a" * 28
    result = client.submit_reasoning(
        action="application_package_v1",
        candidate=candidate(),
        candidate_evidence={"profile_id": "profile-fixture"},
        instructions="draft only",
        client_request_id_override=request_id,
    )
    assert result["smartploy_client_request_id"] == request_id
    assert body[0]["client_request_id"] == request_id
    assert '"external_actions_authorized":false' in body[0]["prompt"]
    with pytest.raises(ValueError, match="idempotency key"):
        client.submit_reasoning(
            action="application_package_v1", candidate=candidate(),
            candidate_evidence={}, client_request_id_override="not-smartploy",
        )
    assert len(body) == 1

import json

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

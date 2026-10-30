"""SP76: KEHA production credential verification without production secrets or DB.

All credentials, postings, URLs and HTTP responses here are synthetic fixtures.
No real KEHA endpoint or SmartPloy production database is contacted by CI.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
import pytest

from scripts import probe_jobmarket_finland_production as smoke
from smartploy.sources.jobmarket_finland import PRODUCTION_ENDPOINT, TEST_ENDPOINT

FAKE_KEY = "only-synthetic-production-kipa-fixture-7422"
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc)
PUBLISHED = {
    "metadata": {"externalId": "00000000-aaaa-bbbb-cccc-123456789abc"},
    "client": {"company": "Fictional Employer Oy"},
    "position": {
        "title": {"fi": "Junior data-analyytikko"},
        "jobDescription": {"fi": "Synthetic fixture; no real vacancy"},
    },
    "location": {"workplacePostOffice": "Tampere"},
    "application": {"url": {"fi": "https://jobs.example.invalid/fictional"}},
}
ARCHIVED = {"metadata": {"externalId": "00000000-aaaa-bbbb-cccc-123456789abc"}}


def env(**overrides):
    return {
        "SMARTPLOY_ENVIRONMENT": "production",
        "JOBMARKET_FINLAND_API_ENABLED": "false",
        "JOBMARKET_FINLAND_ENVIRONMENT": "production",
        "JOBMARKET_FINLAND_ENDPOINT": PRODUCTION_ENDPOINT,
        "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY": FAKE_KEY,
        **overrides,
    }


def fake_transport(status=200, *, empty=False, malformed=False):
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append((request, body))
        if status != 200:
            return httpx.Response(
                status, text="PRIVATE-RESPONSE " + FAKE_KEY
                + " Fictional Employer Oy",
            )
        if malformed:
            return httpx.Response(200, content=b'{"sensitive":invalid}\n')
        if empty:
            return httpx.Response(200, content=b"")
        data = PUBLISHED if body["onlyStatus"] == "PUBLISHED" else ARCHIVED
        return httpx.Response(
            200, content=(json.dumps(data) + "\n").encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
        )

    return httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False), seen


def test_production_probe_uses_original_adapter_and_exact_official_host_twice():
    client, seen = fake_transport()
    try:
        receipt = smoke.run_production_probe(
            smoke.production_settings(env()), minutes=30, now=NOW,
            http_client=client,
        )
    finally:
        client.close()
    assert len(seen) == 2
    assert [request.method for request, _ in seen] == ["POST", "POST"]
    assert [str(request.url) for request, _ in seen] == [
        PRODUCTION_ENDPOINT, PRODUCTION_ENDPOINT,
    ]
    assert [payload["onlyStatus"] for _, payload in seen] == ["PUBLISHED", "ARCHIVED"]
    for request, payload in seen:
        assert request.headers["KIPA-Subscription-Key"] == FAKE_KEY
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Accept"] == "application/x-ndjson"
        assert payload["modified"] == {
            "from": "2026-10-30T13:30:00Z",
            "to": "2026-10-30T14:00:00Z",
        }
        assert payload["postingLanguageIn"] == ["fi", "en", "sv"]
    assert receipt["schema"] == smoke.SCHEMA
    assert receipt["status"] == "production_search_reachable"
    assert receipt["production_endpoint_verified"] is True
    assert receipt["published_count"] == 1
    assert receipt["archived_count"] == 1
    assert receipt["nonempty_published_payload_verified"] is True
    assert receipt["nonempty_archived_payload_verified"] is True
    for field in ("database_writes", "applicant_records_accessed",
                  "employer_applications_sent"):
        assert receipt[field] == 0
    assert receipt["worker_activation"] is False
    assert receipt["production_ingestion_verified"] is False
    assert receipt["external_ai_forwarding"] is False
    serialized = json.dumps(receipt)
    for forbidden in (FAKE_KEY, "Fictional Employer", "jobs.example.invalid",
                      "PRIVATE-RESPONSE", "SMARTPLOY_DATABASE_URL"):
        assert forbidden not in serialized


def test_empty_production_result_is_network_success_not_a_claim_of_loaded_jobs():
    client, seen = fake_transport(empty=True)
    try:
        receipt = smoke.run_production_probe(
            smoke.production_settings(env()), now=NOW, http_client=client,
        )
    finally:
        client.close()
    assert len(seen) == 2
    assert receipt["status"] == "production_search_reachable"
    assert receipt["published_count"] == 0
    assert receipt["archived_count"] == 0
    assert receipt["nonempty_published_payload_verified"] is False
    assert receipt["nonempty_archived_payload_verified"] is False
    assert receipt["production_ingestion_verified"] is False


@pytest.mark.parametrize("overrides,code", [
    ({"JOBMARKET_FINLAND_ENVIRONMENT": "test"}, "PRODUCTION_ENVIRONMENT_REQUIRED"),
    ({"JOBMARKET_FINLAND_ENVIRONMENT": ""}, "PRODUCTION_ENVIRONMENT_REQUIRED"),
    ({"SMARTPLOY_ENVIRONMENT": "test"}, "SMARTPLOY_PRODUCTION_CONTEXT_REQUIRED"),
    ({"JOBMARKET_FINLAND_ENDPOINT": TEST_ENDPOINT}, "OFFICIAL_PRODUCTION_ENDPOINT_REQUIRED"),
    ({"JOBMARKET_FINLAND_ENDPOINT": "http://api.ahtp.fi/kipa/p67/v2/jobpostings"}, "OFFICIAL_PRODUCTION_ENDPOINT_REQUIRED"),
    ({"JOBMARKET_FINLAND_ENDPOINT": "https://phishing.invalid/kipa/p67/v2/jobpostings"}, "OFFICIAL_PRODUCTION_ENDPOINT_REQUIRED"),
    ({"JOBMARKET_FINLAND_API_ENABLED": "true"}, "PRODUCTION_WORKER_MUST_REMAIN_DISABLED"),
    ({"JOBMARKET_FINLAND_API_ENABLED": "1"}, "PRODUCTION_WORKER_MUST_REMAIN_DISABLED"),
    ({"JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY": ""}, "PRODUCTION_KEY_MISSING"),
    ({"JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY": "key\r\nInjected: value"}, "PRODUCTION_KEY_FORMAT_INVALID"),
])
def test_prod_probe_refuses_qa_urls_worker_and_bad_secret(overrides, code):
    with pytest.raises(smoke.ProductionSmokeRejected, match=code):
        smoke.production_settings(env(**overrides))


@pytest.mark.parametrize("minutes", [-1, 0, 1, 4, 121, True, 1.5])
def test_production_probe_rejects_unbounded_or_invalid_modified_window(minutes):
    with pytest.raises(smoke.ProductionSmokeRejected, match="LOOKBACK"):
        smoke.run_production_probe(
            smoke.production_settings(env()), minutes=minutes, now=NOW,
        )


def test_production_probe_rejects_nonprod_adapter_even_when_key_is_present():
    qa = smoke.JobMarketFinlandSettings(
        environment="test", endpoint=TEST_ENDPOINT, subscription_key=FAKE_KEY,
    )
    with pytest.raises(smoke.ProductionSmokeRejected, match="OFFICIAL_PRODUCTION_ENDPOINT"):
        smoke.run_production_probe(qa, now=NOW)


def test_prod_offline_default_has_zero_network_and_does_not_require_a_key(monkeypatch, capsys):
    for key, value in env(JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY="").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(smoke, "JobMarketFinlandAdapter",
                        lambda *_args, **_kwargs: pytest.fail("network adapter used offline"))
    code = smoke.main([])
    output = capsys.readouterr()
    receipt = json.loads(output.out)
    assert code == 0
    assert receipt["credential_present"] is False
    assert receipt["status"] == "offline_configuration_only"
    assert receipt["network_requests"] == 0
    assert receipt["worker_activation"] is False
    assert receipt["live_production_verified"] is False


def test_prod_explicit_execute_prints_counts_only(monkeypatch, capsys):
    for key, value in env().items():
        monkeypatch.setenv(key, value)
    original = smoke.JobMarketFinlandAdapter
    client, seen = fake_transport()
    monkeypatch.setattr(smoke, "JobMarketFinlandAdapter",
                        lambda settings: original(settings, http_client=client))
    try:
        code = smoke.main(["--execute", "--minutes", "30"])
    finally:
        client.close()
    output = capsys.readouterr()
    assert code == 0
    assert len(seen) == 2
    receipt = json.loads(output.out)
    assert receipt["status"] == "production_search_reachable"
    assert FAKE_KEY not in output.out + output.err
    assert "Fictional Employer" not in output.out + output.err


@pytest.mark.parametrize("code,expected", [
    (401, "PRODUCTION_AUTHORIZATION_OR_IP_ACCESS_DENIED"),
    (403, "PRODUCTION_AUTHORIZATION_OR_IP_ACCESS_DENIED"),
    (429, "PRODUCTION_RATE_LIMITED"),
    (503, "PRODUCTION_UPSTREAM_UNAVAILABLE"),
])
def test_production_http_failure_never_prints_key_or_upstream_body(
    monkeypatch, capsys, code, expected,
):
    for key, value in env().items():
        monkeypatch.setenv(key, value)
    original = smoke.JobMarketFinlandAdapter
    client, seen = fake_transport(status=code)
    monkeypatch.setattr(smoke, "JobMarketFinlandAdapter",
                        lambda settings: original(settings, http_client=client))
    try:
        exit_code = smoke.main(["--execute"])
    finally:
        client.close()
    output = capsys.readouterr()
    assert exit_code == 3
    assert len(seen) == 1
    receipt = json.loads(output.err)
    assert receipt["status"] == "hold"
    assert receipt["reason"] == expected
    assert receipt["database_writes"] == 0
    assert receipt["worker_activation"] is False
    for forbidden in (FAKE_KEY, "PRIVATE-RESPONSE", "Fictional Employer"):
        assert forbidden not in output.out + output.err


def test_malformed_stream_never_echoes_record_content_or_secret(monkeypatch, capsys):
    for key, value in env().items():
        monkeypatch.setenv(key, value)
    original = smoke.JobMarketFinlandAdapter
    client, seen = fake_transport(malformed=True)
    monkeypatch.setattr(smoke, "JobMarketFinlandAdapter",
                        lambda settings: original(settings, http_client=client))
    try:
        exit_code = smoke.main(["--execute"])
    finally:
        client.close()
    output = capsys.readouterr()
    assert exit_code == 3
    assert json.loads(output.err)["reason"] == "PRODUCTION_RESPONSE_CONTRACT_INVALID"
    assert FAKE_KEY not in output.err + output.out


def test_worker_enabled_flag_refuses_to_probe_without_any_http(monkeypatch, capsys):
    for key, value in env(JOBMARKET_FINLAND_API_ENABLED="true").items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(smoke, "JobMarketFinlandAdapter",
                        lambda *_args, **_kwargs: pytest.fail("worker must stay disabled"))
    code = smoke.main(["--execute"])
    assert code == 3
    output = capsys.readouterr()
    assert json.loads(output.err)["reason"] == "PRODUCTION_WORKER_MUST_REMAIN_DISABLED"


def test_prod_smoke_contains_no_database_worker_obumai_or_employer_sender():
    text = (Path(__file__).resolve().parents[1] / "scripts"
            / "probe_jobmarket_finland_production.py").read_text(encoding="utf-8")
    for forbidden in (
        "PostgresJobRepository", "psycopg", "SmartployService",
        "poll_jobmarket_finland(", "source_worker(", "build_worker_task_specs(",
        "OBUMAI_BASE_URL", "startApplicationWorkspace(", "submit_to_employer(",
        "docker compose up", "print(settings.subscription_key)",
    ):
        assert forbidden not in text

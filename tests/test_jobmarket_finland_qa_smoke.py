"""SP60: QA access smoke tests using synthetic KIPA keys and HTTP responses.

No production credentials, live QA calls, personal data, persistent jobs,
database, or browser automation are needed to qualify this code.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

import httpx
import pytest

from scripts import probe_jobmarket_finland_qa as smoke
from smartploy.sources.jobmarket_finland import TEST_ENDPOINT, PRODUCTION_ENDPOINT


FAKE_KEY = "synthetic-fixture-only-kipa-key"
NOW = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)

PUBLISHED = {
    "metadata": {"externalId": "aaaa1111-2222-3333-4444-bbbb55556666"},
    "client": {"company": "Fixture Employer Oy"},
    "position": {"title": {"fi": "Junior Data Analyst"},
                 "jobDescription": {"en": "synthetic-only posting"}},
    "location": {"workplacePostOffice": "Tampere"},
    "application": {"url": {"fi": "https://jobs.example.invalid/fixture"}},
}
ARCHIVED = {
    "metadata": {"externalId": "aaaa1111-2222-3333-4444-bbbb55556666"},
}


def env(**overrides):
    return {
        "JOBMARKET_FINLAND_API_ENABLED": "false",
        "JOBMARKET_FINLAND_ENVIRONMENT": "test",
        "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY": FAKE_KEY,
        **overrides,
    }


def _fake_client(response_status: int = 200):
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append((request, body))
        if response_status != 200:
            return httpx.Response(response_status, text="PRIVATE-ERROR " + FAKE_KEY)
        posting = PUBLISHED if body["onlyStatus"] == "PUBLISHED" else ARCHIVED
        return httpx.Response(
            200, content=(json.dumps(posting) + "\n").encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
        )

    return httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False), seen


def test_qa_probe_reuses_exact_official_endpoint_real_adapter_and_sanitizes_receipt():
    client, seen = _fake_client()
    try:
        result = smoke.run_qa_probe(
            smoke.qa_settings(env()), http_client=client, now=NOW, minutes=30,
        )
    finally:
        client.close()

    assert [row[0].method for row in seen] == ["POST", "POST"]
    assert [row[0].url.__str__() for row in seen] == [TEST_ENDPOINT, TEST_ENDPOINT]
    assert [row[1]["onlyStatus"] for row in seen] == ["PUBLISHED", "ARCHIVED"]
    for request, body in seen:
        assert request.headers["KIPA-Subscription-Key"] == FAKE_KEY
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Accept"] == "application/x-ndjson"
        assert body["modified"] == {
            "from": "2026-10-28T12:30:00Z",
            "to": "2026-10-28T13:00:00Z",
        }
        assert body["postingLanguageIn"] == ["fi", "en", "sv"]

    assert result["schema"] == smoke.SCHEMA
    assert result["status"] == "qa_reachable"
    assert result["environment"] == "test"
    assert result["published_query_passed"] is True
    assert result["archived_query_passed"] is True
    assert result["published_posting_count"] == 1
    assert result["archived_posting_count"] == 1
    assert result["production_database_writes"] == 0
    assert result["qa_job_records_saved"] == 0
    assert result["applicant_records_accessed"] == 0
    assert result["employer_applications_sent"] == 0
    assert result["external_ai_forwarding"] is False
    serialized = json.dumps(result)
    assert FAKE_KEY not in serialized
    assert "Fixture Employer" not in serialized
    assert "jobs.example.invalid" not in serialized
    assert "POSTGRES_" not in serialized


def test_empty_qa_modified_interval_is_success_not_fake_job_count():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"")
    ))
    try:
        result = smoke.run_qa_probe(smoke.qa_settings(env()), http_client=client, now=NOW)
    finally:
        client.close()
    assert result["status"] == "qa_reachable"
    assert result["published_posting_count"] == 0
    assert result["archived_posting_count"] == 0


@pytest.mark.parametrize("overrides,code", [
    ({"JOBMARKET_FINLAND_ENVIRONMENT": "production"}, "QA_ENVIRONMENT_ONLY"),
    ({"JOBMARKET_FINLAND_ENDPOINT": PRODUCTION_ENDPOINT}, "QA_ENDPOINT_ONLY"),
    ({"JOBMARKET_FINLAND_ENDPOINT": "http://api-qa.ahtp.fi/kipa/p67/v2/jobpostings"},
     "QA_ENDPOINT_ONLY"),
    ({"JOBMARKET_FINLAND_ENDPOINT": "https://evil.invalid/kipa/p67/v2/jobpostings"},
     "QA_ENDPOINT_ONLY"),
    ({"JOBMARKET_FINLAND_API_ENABLED": "true"}, "QA_WORKER_MUST_REMAIN_DISABLED"),
    ({"JOBMARKET_FINLAND_API_ENABLED": "yes"}, "QA_WORKER_MUST_REMAIN_DISABLED"),
    ({"JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY": ""}, "QA_KEY_MISSING"),
])
def test_qa_smoke_rejects_live_worker_activation_prod_url_and_missing_key(overrides, code):
    with pytest.raises(smoke.QASmokeRejected, match=code):
        smoke.qa_settings(env(**overrides))


@pytest.mark.parametrize("minutes", [0, 1, 4, 121, -1, True, 1.5])
def test_qa_smoke_bounds_modified_query_window(minutes):
    with pytest.raises(smoke.QASmokeRejected, match="LOOKBACK"):
        smoke.run_qa_probe(smoke.qa_settings(env()), minutes=minutes, now=NOW)


def test_offline_default_never_creates_adapter_or_makes_network_call(monkeypatch, capsys):
    monkeypatch.setenv("JOBMARKET_FINLAND_API_ENABLED", "false")
    monkeypatch.setenv("JOBMARKET_FINLAND_ENVIRONMENT", "test")
    monkeypatch.setenv("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", FAKE_KEY)
    monkeypatch.setattr(smoke, "JobMarketFinlandAdapter", lambda *_args, **_kwargs:
                        pytest.fail("offline probe must not create a network adapter"))
    code = smoke.main([])
    captured = capsys.readouterr()
    assert code == 0
    report = json.loads(captured.out)
    assert report["status"] == "offline_configuration_only"
    assert report["credential_present"] is True
    assert report["network_requests"] == 0
    assert report["live_qa_verified"] is False
    assert FAKE_KEY not in captured.out + captured.err


def test_explicit_qa_execute_reads_key_only_from_env_never_prints_it(monkeypatch, capsys):
    for key, value in env().items():
        monkeypatch.setenv(key, value)

    original_adapter = smoke.JobMarketFinlandAdapter
    client, seen = _fake_client()
    monkeypatch.setattr(
        smoke, "JobMarketFinlandAdapter",
        lambda settings: original_adapter(settings, http_client=client),
    )
    try:
        code = smoke.main(["--execute", "--minutes", "30"])
    finally:
        client.close()
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert len(seen) == 2
    assert json.loads(captured.out)["status"] == "qa_reachable"
    assert FAKE_KEY not in captured.out + captured.err
    assert "Fixture Employer" not in captured.out + captured.err


def test_refused_qa_credentials_emit_only_safe_category_not_upstream_secrets(
    monkeypatch, capsys
):
    for key, value in env().items():
        monkeypatch.setenv(key, value)
    original_adapter = smoke.JobMarketFinlandAdapter
    client, seen = _fake_client(response_status=403)
    monkeypatch.setattr(
        smoke, "JobMarketFinlandAdapter",
        lambda settings: original_adapter(settings, http_client=client),
    )
    try:
        code = smoke.main(["--execute"])
    finally:
        client.close()
    captured = capsys.readouterr()
    assert code == 3
    report = json.loads(captured.err)
    assert report["reason"] == "QA_AUTHORIZATION_OR_IP_ACCESS_DENIED"
    assert report["live_qa_verified"] is False
    assert report["production_database_writes"] == 0
    assert len(seen) == 1
    assert FAKE_KEY not in captured.out + captured.err
    assert "PRIVATE-ERROR" not in captured.out + captured.err


def test_qa_smoke_reuses_original_credential_gated_source_without_db_or_deploy():
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1] / "scripts/probe_jobmarket_finland_qa.py"
              ).read_text(encoding="utf-8")
    assert "JobMarketFinlandAdapter" in script
    assert "JobMarketFinlandSettings" in script
    assert "TEST_ENDPOINT" in script
    for forbidden in (
        "PostgresJobRepository", "psycopg", "SmartployService",
        "poll_jobmarket_finland(", "create_or_get(", "docker compose up",
        "OBUMAI_BASE_URL", "print(settings.subscription_key)",
    ):
        assert forbidden not in script

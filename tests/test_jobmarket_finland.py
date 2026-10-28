import json
from datetime import datetime, timezone

import httpx
import pytest

from smartploy.domain import SourceObservation, SourcePolicy, canonical_json
from smartploy.preparations import PreparationNotEligible
from smartploy.service import SmartployService
from smartploy.sources.jobmarket_finland import (
    ORIGINAL_SOURCE_LABEL,
    PRODUCTION_ENDPOINT,
    TEST_ENDPOINT,
    JobMarketFinlandAPIError,
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
    compute_modified_window,
    parse_ndjson,
    validate_endpoint,
)
from smartploy.sources.jobmarket_finland_polling import poll_jobmarket_finland
from smartploy.storage import MemoryJobRepository


PUBLISHED = {
    "metadata": {
        "externalId": "11111111-2222-3333-4444-555555555555",
        "created": "2026-10-09T08:00:00Z",
        "lastModified": "2026-10-10T01:00:00Z",
    },
    "client": {
        "businessId": "1234567-8",
        "company": "Example Oy",
        "industryCode": "62010",
    },
    "owner": {
        "company": {"fi": "Example Oy", "en": "Example Ltd"},
        "employerType": "fixture-code-not-mapped",
    },
    "position": {
        "title": {"fi": "Data-analyytikko", "en": "Data Analyst"},
        "jobDescription": {
            "fi": "Python- ja SQL-analytiikkaa.",
            "en": "Python and SQL analytics.",
        },
        "workLanguages": ["fi", "en"],
        "workTime": ["FULLTIME"],
        "skills": [{"code": "python"}, {"code": "sql"}],
        "occupations": [{"code": "2511"}],
    },
    "location": {
        "workplacePostOffice": "Helsinki",
        "municipalities": ["091"],
        "regions": ["01"],
        "countries": ["FI"],
    },
    "application": {
        "published": "2026-10-09T09:00:00Z",
        "expires": "2026-10-25T20:59:00Z",
        "url": {
            "fi": "https://jobs.example.fi/data-analyst?utm_source=tmt",
            "en": "https://jobs.example.fi/data-analyst",
        },
    },
}

ARCHIVED = {
    "metadata": {
        "externalId": PUBLISHED["metadata"]["externalId"],
        "lastModified": "2026-10-10T03:00:00Z",
        "archived": "2026-10-10T02:55:00Z",
    }
}


def ndjson(*items):
    return ("\n".join(json.dumps(item) for item in items) + ("\n" if items else "")).encode()


@pytest.mark.parametrize(
    ("endpoint", "environment"),
    [
        ("http://api-qa.ahtp.fi/kipa/p67/v2/jobpostings", "test"),
        ("https://127.0.0.1/kipa/p67/v2/jobpostings", "test"),
        ("https://evil.example/kipa/p67/v2/jobpostings", "test"),
        ("https://api-qa.ahtp.fi:8443/kipa/p67/v2/jobpostings", "test"),
        ("https://api-qa.ahtp.fi/kipa/p67/v1/jobpostings", "test"),
        (PRODUCTION_ENDPOINT, "test"),
    ],
)
def test_endpoint_validation_fails_closed(endpoint, environment):
    with pytest.raises(JobMarketFinlandAPIError):
        validate_endpoint(endpoint, environment)


def test_from_env_uses_official_endpoint_when_override_is_blank(monkeypatch):
    monkeypatch.setenv("JOBMARKET_FINLAND_API_ENABLED", "true")
    monkeypatch.setenv("JOBMARKET_FINLAND_ENVIRONMENT", "test")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "test")
    monkeypatch.setenv("JOBMARKET_FINLAND_ENDPOINT", "")
    monkeypatch.setenv("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "fixture-key")
    settings = JobMarketFinlandSettings.from_env()
    assert settings is not None
    assert settings.endpoint == TEST_ENDPOINT


def test_settings_require_key_and_hide_it_from_repr():
    with pytest.raises(JobMarketFinlandAPIError, match="subscription key"):
        JobMarketFinlandSettings(
            environment="test",
            endpoint=TEST_ENDPOINT,
            subscription_key="",
        )

    settings = JobMarketFinlandSettings(
        environment="test",
        endpoint=TEST_ENDPOINT,
        subscription_key="super-secret-key",
    )
    assert "super-secret-key" not in repr(settings)


def test_published_ndjson_maps_localized_fields_and_restricts_ai_forwarding():
    batch = parse_ndjson(
        ndjson(PUBLISHED),
        status="PUBLISHED",
        endpoint=TEST_ENDPOINT,
        observed_at="2026-10-10T02:00:00+00:00",
    )
    assert batch.item_count == 1
    item = batch.observations[0]
    assert item.source_id == "job-market-finland"
    assert item.source_external_id == PUBLISHED["metadata"]["externalId"]
    assert item.payload["company"] == "Example Oy"
    assert item.payload["role_title"] == "Data-analyytikko"
    assert item.payload["location"] == "Helsinki"
    assert item.payload["source_attribution"] == ORIGINAL_SOURCE_LABEL
    assert item.payload["external_ai_forwarding_allowed"] is False
    assert item.payload["employer_sector"] == "unknown"
    assert item.payload["source_details"]["skills"] == ["python", "sql"]
    assert "super-secret" not in canonical_json(item.payload)


def test_archived_ndjson_does_not_create_a_current_observation():
    batch = parse_ndjson(
        ndjson(ARCHIVED),
        status="ARCHIVED",
        endpoint=TEST_ENDPOINT,
        observed_at="2026-10-10T03:00:00+00:00",
    )
    assert not batch.observations
    assert len(batch.archived) == 1
    assert batch.archived[0].external_id == PUBLISHED["metadata"]["externalId"]


def test_adapter_posts_official_filters_and_never_persists_key():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append((request, body))
        return httpx.Response(200, content=ndjson(PUBLISHED), headers={"content-type": "application/x-ndjson"})

    settings = JobMarketFinlandSettings(
        environment="test",
        endpoint=TEST_ENDPOINT,
        subscription_key="super-secret-key",
        posting_languages=("fi", "en"),
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = JobMarketFinlandAdapter(settings, http_client=client)

    batch = adapter.fetch_window(
        status="PUBLISHED",
        modified_from="2026-10-10T00:00:00Z",
        modified_to="2026-10-10T02:00:00Z",
        observed_at="2026-10-10T02:00:00+00:00",
    )
    request, body = seen[0]
    assert request.method == "POST"
    assert request.headers["KIPA-Subscription-Key"] == "super-secret-key"
    assert body == {
        "onlyStatus": "PUBLISHED",
        "modified": {
            "from": "2026-10-10T00:00:00Z",
            "to": "2026-10-10T02:00:00Z",
        },
        "postingLanguageIn": ["fi", "en"],
    }
    stored_form = canonical_json(batch.observations[0].payload) + batch.observations[0].raw_text
    assert "super-secret-key" not in stored_form


def test_modified_window_uses_overlap_after_last_success():
    start, end = compute_modified_window(
        last_success_at="2026-10-10T01:30:00+00:00",
        now=datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc),
        overlap_minutes=5,
    )
    assert start == "2026-10-10T01:25:00Z"
    assert end == "2026-10-10T02:00:00Z"


def test_poll_published_then_archived_retires_and_redacts_single_source_job():
    phase = {"archived": False}

    def handler(request):
        body = json.loads(request.content)
        if body["onlyStatus"] == "PUBLISHED":
            return httpx.Response(200, content=b"" if phase["archived"] else ndjson(PUBLISHED))
        return httpx.Response(200, content=ndjson(ARCHIVED) if phase["archived"] else b"")

    settings = JobMarketFinlandSettings(
        environment="test",
        endpoint=TEST_ENDPOINT,
        subscription_key="fixture-key",
    )
    adapter = JobMarketFinlandAdapter(
        settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    )
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)

    first = poll_jobmarket_finland(
        service,
        adapter,
        modified_from="2026-10-10T00:00:00Z",
        modified_to="2026-10-10T02:00:00Z",
        attempted_at="2026-10-10T02:00:00+00:00",
    )
    assert first.status == "healthy"
    assert first.discovered_count == 1
    candidate = repository.values()[0]
    assert candidate.source_current is True
    assert candidate.job.raw["external_ai_forwarding_allowed"] is False

    with pytest.raises(PreparationNotEligible, match="source terms restrict"):
        service.prepare_job(candidate.canonical_key)

    phase["archived"] = True
    second = poll_jobmarket_finland(
        service,
        adapter,
        modified_from="2026-10-10T02:00:00Z",
        modified_to="2026-10-10T04:00:00Z",
        attempted_at="2026-10-10T04:00:00+00:00",
    )
    assert second.retired_count == 1
    retired = repository.get(candidate.canonical_key)
    assert retired is not None
    assert retired.source_current is False
    assert retired.job.company == "Archived source"
    assert retired.job.description == ""


def test_empty_incremental_result_does_not_close_omitted_current_jobs():
    responses = []

    def handler(request):
        responses.append(json.loads(request.content))
        return httpx.Response(200, content=b"")

    settings = JobMarketFinlandSettings(
        environment="test",
        endpoint=TEST_ENDPOINT,
        subscription_key="fixture-key",
    )
    adapter = JobMarketFinlandAdapter(
        settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    )
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    policy = adapter.policy()
    service.register_source(policy)
    initial = parse_ndjson(
        ndjson(PUBLISHED),
        status="PUBLISHED",
        endpoint=TEST_ENDPOINT,
        observed_at="2026-10-10T01:00:00+00:00",
    ).observations[0]
    inserted = service.ingest(initial)
    assert inserted.candidate is not None

    summary = poll_jobmarket_finland(
        service,
        adapter,
        modified_from="2026-10-10T01:00:00Z",
        modified_to="2026-10-10T02:00:00Z",
        attempted_at="2026-10-10T02:00:00+00:00",
    )
    assert summary.status == "healthy"
    assert summary.published_count == 0
    assert summary.archived_count == 0
    assert repository.get(inserted.candidate.canonical_key).source_current is True
    assert {item["onlyStatus"] for item in responses} == {"PUBLISHED", "ARCHIVED"}


def test_retiring_one_source_preserves_an_independently_sourced_duplicate():
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)

    jobmarket_policy = SourcePolicy(
        "job-market-finland",
        "Job Market Finland",
        "national_job_market",
        ("api",),
    )
    direct_policy = SourcePolicy(
        "company-careers",
        "Company Careers",
        "company_careers",
        ("feed",),
    )
    service.register_source(jobmarket_policy)
    service.register_source(direct_policy)

    tmt = parse_ndjson(
        ndjson(PUBLISHED),
        status="PUBLISHED",
        endpoint=TEST_ENDPOINT,
        observed_at="2026-10-10T01:00:00+00:00",
    ).observations[0]
    first = service.ingest(tmt)
    assert first.candidate is not None

    direct = SourceObservation(
        source_id="company-careers",
        source_mode="feed",
        source_url="https://jobs.example.fi/data-analyst",
        raw_text=tmt.raw_text,
        payload={
            **dict(tmt.payload),
            "source_attribution": "",
            "external_ai_forwarding_allowed": True,
            "application_url": "https://jobs.example.fi/data-analyst",
        },
        observed_at="2026-10-10T01:30:00+00:00",
        posted_at=tmt.posted_at,
        source_external_id="company-42",
    )
    second = service.ingest(direct)
    assert second.candidate is not None
    assert second.candidate.canonical_key == first.candidate.canonical_key
    assert set(second.candidate.source_ids) == {"job-market-finland", "company-careers"}

    rebuilt = repository.retire_source_external_id(
        "job-market-finland",
        PUBLISHED["metadata"]["externalId"],
        archived_at="2026-10-10T03:00:00+00:00",
    )
    assert rebuilt is not None
    assert rebuilt.source_current is True
    assert rebuilt.source_ids == ("company-careers",)
    assert rebuilt.job.company == "Example Oy"
    assert rebuilt.job.raw["external_ai_forwarding_allowed"] is True


def test_sp60_qa_key_never_activates_production_p67_source(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("JOBMARKET_FINLAND_API_ENABLED", "true")
    monkeypatch.setenv("JOBMARKET_FINLAND_ENVIRONMENT", "test")
    monkeypatch.setenv("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "fixture-only-key")
    monkeypatch.setenv("JOBMARKET_FINLAND_ENDPOINT", TEST_ENDPOINT)
    with pytest.raises(JobMarketFinlandAPIError, match="QA credentials cannot be used"):
        JobMarketFinlandSettings.from_env()

    # Production endpoint and independently granted production credentials
    # are required for production. QA credentials cannot select it by mistake.
    monkeypatch.setenv("JOBMARKET_FINLAND_ENVIRONMENT", "production")
    with pytest.raises(JobMarketFinlandAPIError, match="official environment endpoint"):
        JobMarketFinlandSettings.from_env()

    # A later real production credential can use the official host after
    # separate KEHA authorization; the test never makes a real HTTP request.
    monkeypatch.setenv("JOBMARKET_FINLAND_ENDPOINT", PRODUCTION_ENDPOINT)
    production = JobMarketFinlandSettings.from_env()
    assert production is not None and production.environment == "production"
    assert "fixture-only-key" not in repr(production)

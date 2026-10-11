import json

import httpx
import pytest

from smartploy.domain import SourceObservation, SourcePolicy
from smartploy.preparations import PreparationNotEligible
from smartploy.service import SmartployService
from smartploy.sources.public_ats import (
    LEVER_ATTRIBUTION,
    SMARTRECRUITERS_ATTRIBUTION,
    LeverAdapter,
    PublicATSError,
    PublicATSRuntimeSettings,
    PublicATSSourceConfig,
    SmartRecruitersAdapter,
    build_public_ats_adapter,
    load_public_ats_sources,
)
from smartploy.sources.public_ats_polling import poll_public_ats
from smartploy.storage import MemoryJobRepository


def runtime(page_size=2):
    return PublicATSRuntimeSettings(
        timeout_seconds=5,
        page_size=page_size,
        max_items=20,
        max_response_bytes=1024 * 1024,
    )


def test_config_rejects_arbitrary_provider_tenant_and_fields(monkeypatch):
    with pytest.raises(PublicATSError, match="provider"):
        PublicATSSourceConfig("greenhouse", "acme", "Acme")
    with pytest.raises(PublicATSError, match="tenant"):
        PublicATSSourceConfig("lever", "https://evil.example/x", "Acme")
    with pytest.raises(PublicATSError, match="stack"):
        PublicATSSourceConfig("smartrecruiters", "acme", "Acme", stack="eu")
    with pytest.raises(PublicATSError, match="boolean"):
        PublicATSSourceConfig(
            "lever",
            "acme",
            "Acme",
            external_ai_forwarding_allowed="true",
        )

    monkeypatch.setenv(
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON",
        json.dumps([{"provider": "lever", "tenant": "acme", "label": "Acme", "url": "https://x"}]),
    )
    with pytest.raises(PublicATSError, match="unsupported"):
        load_public_ats_sources()


def test_config_loader_rejects_ambiguous_inline_and_file(monkeypatch, tmp_path):
    path = tmp_path / "ats.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", "[]")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE", str(path))
    with pytest.raises(PublicATSError, match="either"):
        load_public_ats_sources()


def test_config_source_ids_are_deterministic_and_ai_defaults_false():
    sr = PublicATSSourceConfig("smartrecruiters", "Acme-Finland", "Acme Finland")
    lever = PublicATSSourceConfig("lever", "Acme-Finland", "Acme Finland", stack="eu")
    assert sr.source_id == "smartrecruiters-acme-finland"
    assert lever.source_id == "lever-eu-acme-finland"
    assert sr.external_ai_forwarding_allowed is False
    assert lever.external_ai_forwarding_allowed is False


def test_smartrecruiters_pagination_detail_mapping_and_public_destination():
    seen = []

    details = {
        "p1": {
            "id": "p1",
            "uuid": "uuid-p1",
            "name": "Data Analyst",
            "company": {"name": "Acme Oy"},
            "releasedDate": "2026-10-10T08:00:00Z",
            "location": {"city": "Helsinki", "country": "Finland", "remote": True},
            "postingUrl": "https://jobs.smartrecruiters.com/acme/p1",
            "applyUrl": "https://jobs.smartrecruiters.com/acme/p1/apply",
            "industry": {"label": "Technology"},
            "department": {"label": "Data"},
            "function": {"label": "Analytics"},
            "experienceLevel": {"label": "Entry level"},
            "typeOfEmployment": {"label": "Full-time"},
            "jobAd": {
                "sections": {
                    "companyDescription": {"text": "<p>Acme builds things.</p>"},
                    "jobDescription": {"text": "<p>Use Python and SQL.</p>"},
                    "qualifications": {"text": "<p>Power BI is useful.</p>"},
                    "additionalInformation": {"text": "<p>Hybrid team.</p>"},
                }
            },
        },
        "p2": {
            "id": "p2",
            "name": "QA Engineer",
            "company": {"name": "Acme Oy"},
            "location": {"city": "Espoo", "country": "Finland"},
            "postingUrl": "https://jobs.smartrecruiters.com/acme/p2",
            "applyUrl": "https://jobs.smartrecruiters.com/acme/p2/apply",
            "jobAd": {"sections": {"jobDescription": {"text": "Testing APIs"}}},
        },
        "p3": {
            "id": "p3",
            "name": "Business Analyst",
            "company": {"name": "Acme Oy"},
            "location": {"city": "Vantaa", "country": "Finland"},
            "postingUrl": "https://jobs.smartrecruiters.com/acme/p3",
            "applyUrl": "https://jobs.smartrecruiters.com/acme/p3/apply",
            "jobAd": {"sections": {"jobDescription": {"text": "Requirements analysis"}}},
        },
    }

    def handler(request):
        seen.append(request)
        path = request.url.path
        if path.endswith("/postings"):
            offset = int(request.url.params.get("offset", "0"))
            assert request.url.params["destination"] == "PUBLIC"
            assert request.url.params["limit"] == "2"
            if offset == 0:
                return httpx.Response(
                    200,
                    json={"content": [{"id": "p1"}, {"id": "p2"}], "totalFound": 3},
                )
            if offset == 2:
                return httpx.Response(200, json={"content": [{"id": "p3"}], "totalFound": 3})
        posting_id = path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=details[posting_id])

    config = PublicATSSourceConfig(
        "smartrecruiters",
        "acme",
        "Acme Oy",
        employer_sector="private",
        external_ai_forwarding_allowed=True,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = SmartRecruitersAdapter(config, runtime(), http_client=client)
    observations = adapter.fetch_all(observed_at="2026-10-10T10:00:00+00:00")

    assert [item.source_external_id for item in observations] == ["p1", "p2", "p3"]
    first = observations[0]
    assert first.payload["company"] == "Acme Oy"
    assert first.payload["role_title"] == "Data Analyst"
    assert first.payload["work_mode"] == "remote"
    assert first.payload["employer_sector"] == "private"
    assert first.payload["source_attribution"] == SMARTRECRUITERS_ATTRIBUTION
    assert first.payload["external_ai_forwarding_allowed"] is True
    assert "Power BI is useful." in first.raw_text
    assert first.payload.get("requirements") is None
    assert len(seen) == 5


@pytest.mark.parametrize(
    ("stack", "expected_host"),
    [("global", "api.lever.co"), ("eu", "api.eu.lever.co")],
)
def test_lever_global_and_eu_pagination_mapping(stack, expected_host):
    seen = []

    def posting(identifier, title, location):
        return {
            "id": identifier,
            "text": title,
            "categories": {
                "location": location,
                "commitment": "Full-time",
                "team": "Engineering",
                "department": "Product",
                "allLocations": [location],
            },
            "country": "FI",
            "descriptionPlain": "Build data products.",
            "additionalPlain": "Python is useful.",
            "hostedUrl": "https://jobs.lever.co/acme/" + identifier,
            "applyUrl": "https://jobs.lever.co/acme/" + identifier + "/apply",
            "workplaceType": "hybrid",
            "salaryRange": {"currency": "EUR", "min": 3500, "max": 4500},
        }

    pages = {
        0: [posting("l1", "Data Engineer", "Helsinki"), posting("l2", "QA Engineer", "Espoo")],
        2: [posting("l3", "Business Analyst", "Vantaa")],
    }

    def handler(request):
        seen.append(request)
        assert request.url.host == expected_host
        assert request.url.params["mode"] == "json"
        assert request.url.params["limit"] == "2"
        skip = int(request.url.params.get("skip", "0"))
        return httpx.Response(200, json=pages[skip])

    config = PublicATSSourceConfig(
        "lever",
        "acme",
        "Acme Oy",
        stack=stack,
        employer_sector="private",
        external_ai_forwarding_allowed=True,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = LeverAdapter(config, runtime(), http_client=client)
    observations = adapter.fetch_all(observed_at="2026-10-10T10:00:00+00:00")

    assert [item.source_external_id for item in observations] == ["l1", "l2", "l3"]
    assert observations[0].payload["source_attribution"] == LEVER_ATTRIBUTION
    assert observations[0].payload["work_mode"] == "hybrid"
    assert observations[0].payload["salary_min_eur"] == 3500
    assert observations[0].payload["salary_max_eur"] == 4500
    assert observations[0].posted_at == ""
    assert len(seen) == 2


def test_same_external_id_update_keeps_one_canonical_job():
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    policy = SourcePolicy("lever-global-acme", "Acme", "direct_employer_ats", ("api",))
    service.register_source(policy)

    first = SourceObservation(
        source_id="lever-global-acme",
        source_mode="api",
        source_url="https://jobs.lever.co/acme/job-1",
        raw_text="Data Analyst first description",
        payload={
            "company": "Acme Oy",
            "role_title": "Data Analyst",
            "description": "First short description",
            "location": "Helsinki",
            "application_url": "https://jobs.lever.co/acme/job-1/apply",
        },
        observed_at="2026-10-10T08:00:00+00:00",
        source_external_id="job-1",
    )
    second = SourceObservation(
        source_id="lever-global-acme",
        source_mode="api",
        source_url="https://jobs.lever.co/acme/job-1",
        raw_text="Data Analyst completely changed expanded description",
        payload={
            "company": "Acme Oy",
            "role_title": "Data Analyst",
            "description": "Completely changed and much longer description with Python SQL analytics",
            "location": "Helsinki",
            "application_url": "https://jobs.lever.co/acme/job-1/apply",
        },
        observed_at="2026-10-10T09:00:00+00:00",
        source_external_id="job-1",
    )

    one = service.ingest(first)
    two = service.ingest(second)
    assert one.candidate is not None and two.candidate is not None
    assert one.candidate.canonical_key == two.candidate.canonical_key
    assert len(repository.values()) == 1
    assert repository.canonical_key_for_source_external_id("lever-global-acme", "job-1") == one.candidate.canonical_key


def test_successful_exhaustive_omission_retires_missing_posting():
    class FixtureAdapter:
        provider = "lever"
        parser_version = "fixture-v1"

        def __init__(self):
            self.config = PublicATSSourceConfig("lever", "acme", "Acme Oy")
            self.source_id = self.config.source_id
            self.items = ["a", "b"]

        def policy(self):
            return SourcePolicy(self.source_id, "Acme", "direct_employer_ats", ("api",))

        def fetch_all(self, *, observed_at=None):
            timestamp = observed_at or "2026-10-10T10:00:00+00:00"
            return [
                SourceObservation(
                    source_id=self.source_id,
                    source_mode="api",
                    source_url="https://jobs.lever.co/acme/" + item,
                    raw_text="Role " + item,
                    payload={
                        "company": "Acme Oy",
                        "role_title": "Role " + item,
                        "description": "Description " + item,
                        "application_url": "https://jobs.lever.co/acme/" + item + "/apply",
                    },
                    observed_at=timestamp,
                    source_external_id=item,
                )
                for item in self.items
            ]

    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    adapter = FixtureAdapter()

    first = poll_public_ats(service, adapter, attempted_at="2026-10-10T10:00:00+00:00")
    assert first.discovered_count == 2
    assert repository.active_source_external_ids(adapter.source_id) == {"a", "b"}

    adapter.items = ["a"]
    second = poll_public_ats(service, adapter, attempted_at="2026-10-10T11:00:00+00:00")
    assert second.status == "healthy"
    assert second.retired_count == 1
    assert repository.active_source_external_ids(adapter.source_id) == {"a"}


def test_failed_snapshot_retires_nothing():
    class FailingAdapter:
        provider = "lever"
        parser_version = "fixture-v1"

        def __init__(self):
            self.config = PublicATSSourceConfig("lever", "acme", "Acme Oy")
            self.source_id = self.config.source_id

        def policy(self):
            return SourcePolicy(self.source_id, "Acme", "direct_employer_ats", ("api",))

        def fetch_all(self, *, observed_at=None):
            raise PublicATSError("pagination failed")

    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    adapter = FailingAdapter()
    service.register_source(adapter.policy())
    existing = SourceObservation(
        source_id=adapter.source_id,
        source_mode="api",
        source_url="https://jobs.lever.co/acme/a",
        raw_text="Existing Role",
        payload={
            "company": "Acme Oy",
            "role_title": "Existing Role",
            "description": "Still current until proven otherwise",
        },
        observed_at="2026-10-10T09:00:00+00:00",
        source_external_id="a",
    )
    service.ingest(existing)

    result = poll_public_ats(service, adapter, attempted_at="2026-10-10T10:00:00+00:00")
    assert result.status == "failed"
    assert result.retired_count == 0
    assert repository.active_source_external_ids(adapter.source_id) == {"a"}


def test_default_tenant_ai_policy_blocks_application_preparation():
    config = PublicATSSourceConfig("lever", "acme", "Acme Oy")
    adapter = build_public_ats_adapter(
        config,
        runtime(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=[{
                        "id": "l1",
                        "text": "Data Analyst",
                        "categories": {"location": "Helsinki"},
                        "descriptionPlain": "Python SQL data analytics",
                        "hostedUrl": "https://jobs.lever.co/acme/l1",
                        "applyUrl": "https://jobs.lever.co/acme/l1/apply",
                    }],
                )
            ),
            follow_redirects=False,
        ),
    )
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    service.register_source(adapter.policy())
    observation = adapter.fetch_all(observed_at="2026-10-10T10:00:00+00:00")[0]
    result = service.ingest(observation)
    assert result.candidate is not None
    assert result.candidate.job.raw["external_ai_forwarding_allowed"] is False
    with pytest.raises(PreparationNotEligible, match="source terms restrict"):
        service.prepare_job(result.candidate.canonical_key)


def test_per_source_timeout_and_pagination_are_bounded_and_isolated():
    baseline = PublicATSRuntimeSettings(timeout_seconds=15, page_size=100, max_items=500)
    configs = [
        PublicATSSourceConfig("lever", "uprightproject", "Upright"),
        PublicATSSourceConfig("lever", "tsmg", "TSMG",
                              request_timeout_seconds=45, page_size=50),
    ]
    adapters = [LeverAdapter(config, baseline) for config in configs]
    try:
        assert adapters[0].runtime is baseline
        assert adapters[0].runtime.timeout_seconds == 15
        assert adapters[0].runtime.page_size == 100
        assert adapters[1].runtime.timeout_seconds == 45
        assert adapters[1].runtime.page_size == 50
        assert adapters[1].runtime.max_items == 500
        assert baseline.timeout_seconds == 15
        assert baseline.page_size == 100
    finally:
        for adapter in adapters:
            adapter.close()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("request_timeout_seconds", True),
        ("request_timeout_seconds", "45"),
        ("request_timeout_seconds", 4),
        ("request_timeout_seconds", 61),
        ("request_timeout_seconds", float("inf")),
        ("request_timeout_seconds", float("nan")),
        ("page_size", True),
        ("page_size", 0),
        ("page_size", 101),
        ("page_size", "50"),
    ],
)
def test_per_source_override_rejects_unbounded_or_untyped_settings(key, value):
    with pytest.raises(PublicATSError, match=key):
        PublicATSSourceConfig("lever", "tsmg", "TSMG", **{key: value})


def test_scoped_page_size_retrieves_complete_snapshot_and_keeps_fi_remote():
    baseline = PublicATSRuntimeSettings(timeout_seconds=15, page_size=100, max_items=120)
    pages = []

    def make_job(i):
        return {
            "id": "job-" + str(i),
            "text": "Finnish role " + str(i),
            "descriptionPlain": "Software and analytics",
            "country": "FI" if i == 5 else "SE",
            "categories": {"location": "Remote" if i == 5 else "Stockholm"},
            "hostedUrl": "https://jobs.lever.co/tsmg/job-" + str(i),
            "applyUrl": "https://jobs.lever.co/tsmg/job-" + str(i) + "/apply",
        }

    listings = [make_job(i) for i in range(51)]

    def handler(request):
        assert request.url.host == "api.lever.co"
        skip = int(request.url.params["skip"])
        count = int(request.url.params["limit"])
        pages.append((skip, count))
        return httpx.Response(200, json=listings[skip:skip + count])

    adapter = LeverAdapter(
        PublicATSSourceConfig(
            "lever", "tsmg", "TSMG",
            location_terms=("Finland", "Helsinki"),
            request_timeout_seconds=45,
            page_size=50,
        ), baseline,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        records = adapter.fetch_all()
        assert [row.source_external_id for row in records] == ["job-5"]
        assert pages == [(0, 50), (50, 50)]
        assert adapter.last_total_postings == 51
        assert adapter.last_location_filtered_count == 50
    finally:
        adapter.close()


def test_tsmg_timeout_on_second_page_does_not_retire_existing_jobs():
    state = {"fail": False}
    def job(identifier):
        return {
            "id": identifier,
            "text": "Data role " + identifier,
            "descriptionPlain": "Data analytics software",
            "country": "FI",
            "categories": {"location": "Helsinki"},
            "hostedUrl": "https://jobs.lever.co/tsmg/" + identifier,
            "applyUrl": "https://jobs.lever.co/tsmg/" + identifier + "/apply",
        }

    def handler(request):
        skip = int(request.url.params.get("skip", "0"))
        if not state["fail"]:
            return httpx.Response(200, json=[job("original")])
        if skip == 0:
            return httpx.Response(200, json=[job(str(index)) for index in range(50)])
        raise httpx.ReadTimeout("simulated slow second page")

    adapter = LeverAdapter(
        PublicATSSourceConfig(
            "lever", "tsmg", "TSMG", location_terms=("Finland",),
            request_timeout_seconds=45, page_size=50,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    try:
        first = poll_public_ats(service, adapter)
        assert first.status == "healthy"
        assert repository.active_source_external_ids(adapter.source_id) == {"original"}
        state["fail"] = True
        second = poll_public_ats(service, adapter)
        assert second.status == "failed"
        assert second.retired_count == 0
        assert repository.active_source_external_ids(adapter.source_id) == {"original"}
    finally:
        adapter.close()

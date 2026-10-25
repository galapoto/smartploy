"""Read-only Greenhouse published board integration and fail-closed polling."""
from __future__ import annotations

import httpx
import pytest

from smartploy.service import SmartployService
from smartploy.sources.public_ats import (
    GREENHOUSE_ATTRIBUTION,
    GreenhouseAdapter,
    PublicATSError,
    PublicATSSourceConfig,
    PublicATSRuntimeSettings,
    build_public_ats_adapter,
)
from smartploy.sources.public_ats_polling import poll_public_ats
from smartploy.storage import MemoryJobRepository


def runtime():
    return PublicATSRuntimeSettings(
        timeout_seconds=5, page_size=10, max_items=20, max_response_bytes=1024 * 1024,
    )


def posting(identifier, title, place, *, country="Finland", internal_id=1):
    return {
        "id": identifier,
        "internal_job_id": internal_id,
        "title": title,
        "content": "<p>Data analysis with Python &amp; SQL.</p>",
        "location": {"name": place},
        "language": "en",
        "updated_at": "2026-10-11T10:00:00Z",
        "offices": [{"id": 6, "name": "Data Office", "location": country}],
        "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{identifier}",
    }


def adapter_for(handler, *, location_terms=("Finland", "Helsinki", "Espoo")):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    config = PublicATSSourceConfig(
        "greenhouse", "Acme", "Acme Oy", location_terms=location_terms,
    )
    adapter = build_public_ats_adapter(config, runtime(), http_client=client)
    assert isinstance(adapter, GreenhouseAdapter)
    return adapter, client


def test_greenhouse_config_is_bounded_and_ai_forwarding_off_by_default():
    config = PublicATSSourceConfig("greenhouse", "Acme-Finland", "Acme Oy")
    assert config.source_id == "greenhouse-acme-finland"
    assert config.external_ai_forwarding_allowed is False
    assert config.stack == ""
    with pytest.raises(PublicATSError, match="stack"):
        PublicATSSourceConfig("greenhouse", "acme", "Acme", stack="eu")
    with pytest.raises(PublicATSError, match="tenant"):
        PublicATSSourceConfig("greenhouse", "../private", "Acme")
    with pytest.raises(PublicATSError, match="tenant"):
        PublicATSSourceConfig("greenhouse", "https://attacker.invalid", "Acme")
    with pytest.raises(PublicATSError, match="page_size"):
        PublicATSSourceConfig("greenhouse", "acme", "Acme", page_size=20)


def test_greenhouse_public_listing_filters_structured_fi_locations_and_prospects():
    seen = []
    data = [
        posting(101, "Data Analyst", "Helsinki, Finland"),
        posting(102, "QA Engineer", "Espoo", country="Finland"),
        posting(103, "Operations Analyst", "Stockholm", country="Sweden"),
        posting(104, "General application talent pool", "Helsinki", internal_id=None),
    ]

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert request.url.host == "boards-api.greenhouse.io"
        assert request.url.path == "/v1/boards/Acme/jobs"
        assert request.url.params["content"] == "true"
        return httpx.Response(200, json={"jobs": data, "meta": {"total": 4}})

    adapter, client = adapter_for(handler)
    try:
        rows = adapter.fetch_all(observed_at="2026-10-11T11:00:00+00:00")
        assert [row.source_external_id for row in rows] == ["101", "102"]
        first = rows[0]
        assert first.source_id == "greenhouse-acme"
        assert first.payload["role_title"] == "Data Analyst"
        assert "Data analysis with Python & SQL." in first.payload["description"]
        assert first.payload["work_mode"] == "review"
        assert first.payload["language"] == "en"
        assert first.payload["source_attribution"] == GREENHOUSE_ATTRIBUTION
        assert first.payload["external_ai_forwarding_allowed"] is False
        assert first.payload["application_url"] == "https://job-boards.greenhouse.io/acme/jobs/101"
        assert first.posted_at == ""  # API updated_at is not job publication date.
        assert first.payload["source_details"]["updated_at"] == "2026-10-11T10:00:00Z"
        assert adapter.last_total_postings == 4
        assert adapter.last_location_filtered_count == 1
        assert adapter.last_prospect_filtered_count == 1
        assert len(seen) == 1
    finally:
        client.close()


@pytest.mark.parametrize("malformed", [
    {"unexpected": []},
    {"jobs": "not-an-array"},
    {"jobs": [123]},
    {"jobs": [{"id": 1, "title": "Data Analyst", "location": {"name": "Helsinki"}}]},
    {"jobs": [posting(1, "Data Analyst", "Helsinki")], "meta": {"total": 2}},
    {"jobs": [{**posting(1, "Data Analyst", "Helsinki"), "absolute_url": "http://insecure.invalid/job"}]},
])
def test_greenhouse_malformed_or_incomplete_snapshot_fails(malformed):
    adapter, client = adapter_for(lambda request: httpx.Response(200, json=malformed))
    try:
        with pytest.raises(PublicATSError):
            adapter.fetch_all()
    finally:
        client.close()


def test_greenhouse_response_size_limit_fails_closed():
    payload = {"jobs": [posting(1, "Data Analyst", "Helsinki")]}
    config = PublicATSSourceConfig("greenhouse", "acme", "Acme")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
        follow_redirects=False,
    )
    adapter = GreenhouseAdapter(
        config,
        PublicATSRuntimeSettings(
            timeout_seconds=5, page_size=10, max_items=20, max_response_bytes=20,
        ),
        http_client=client,
    )
    try:
        with pytest.raises(PublicATSError, match="size"):
            adapter.fetch_all()
    finally:
        client.close()


def test_greenhouse_transport_failure_does_not_retire_live_posting():
    state = {"fail": False}
    def handler(request):
        if state["fail"]:
            raise httpx.ReadTimeout("synthetic request timed out")
        return httpx.Response(
            200, json={"jobs": [posting(12, "Data Analyst", "Helsinki")], "meta": {"total": 1}},
        )
    adapter, client = adapter_for(handler)
    service = SmartployService(repository=MemoryJobRepository())
    try:
        initial = poll_public_ats(service, adapter)
        assert initial.status == "healthy"
        assert initial.discovered_count == 1
        assert service.repository.active_source_external_ids(adapter.source_id) == {"12"}

        state["fail"] = True
        failed = poll_public_ats(service, adapter)
        assert failed.status == "failed"
        assert failed.retired_count == 0
        assert service.repository.active_source_external_ids(adapter.source_id) == {"12"}
    finally:
        client.close()


def test_greenhouse_full_successful_empty_snapshot_can_retire_removed_jobs():
    state = {"empty": False}
    def handler(request):
        jobs = [] if state["empty"] else [posting(12, "Data Analyst", "Helsinki")]
        return httpx.Response(200, json={"jobs": jobs, "meta": {"total": len(jobs)}})
    adapter, client = adapter_for(handler)
    service = SmartployService(repository=MemoryJobRepository())
    try:
        assert poll_public_ats(service, adapter).discovered_count == 1
        state["empty"] = True
        completed = poll_public_ats(service, adapter)
        assert completed.status == "healthy"
        assert completed.item_count == 0
        assert completed.retired_count == 1
        assert service.repository.active_source_external_ids(adapter.source_id) == set()
    finally:
        client.close()


def test_greenhouse_redirect_does_not_get_followed():
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://attacker.invalid/jobs"})
    adapter, client = adapter_for(handler)
    try:
        with pytest.raises(PublicATSError, match="redirect"):
            adapter.fetch_all()
        assert len(seen) == 1
        assert "attacker.invalid" not in seen[0]
    finally:
        client.close()


def test_greenhouse_foreign_location_is_not_overridden_by_finnish_office():
    foreign = posting(303, "Operations Analyst", "Stockholm", country="Finland")
    remote = posting(304, "Remote Data Analyst", "Remote", country="Finland")

    def handler(request):
        return httpx.Response(
            200, json={"jobs": [foreign, remote], "meta": {"total": 2}},
        )

    adapter, client = adapter_for(handler)
    try:
        records = adapter.fetch_all()
        assert [item.source_external_id for item in records] == ["304"]
        assert adapter.last_location_filtered_count == 1
        assert adapter.last_total_postings == 2
    finally:
        client.close()


def test_sp43_real_greenhouse_public_finnish_job_reaches_reviewed_browser_handoff():
    """Reuse the actual SP20 read-only adapter, source policy, CV workspace and packet."""
    from dataclasses import replace
    from datetime import datetime, timezone
    from smartploy.application_workspace import new_workspace
    from smartploy.browser_handoff import make_browser_packet, review_handoff
    from smartploy.domain import normalize_observation
    from smartploy.profile import CandidateProfile, ProfileFact

    source = posting(123456789, "Junior Data Engineer", "Helsinki, Finland")
    foreign = posting(123456790, "QA Tester", "Stockholm",country="Sweden")
    unseen = posting(123456791, "Talent pool", "Helsinki",internal_id=None)
    calls = []
    def respond(request):
        calls.append((request.method,str(request.url)))
        return httpx.Response(200,json={
            "jobs":[source,foreign,unseen],"meta":{"total":3},
        })
    adapter,client=adapter_for(respond)
    try:
        observations=adapter.fetch_all(
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
        assert len(observations)==1
        candidate=normalize_observation(observations[0],adapter.policy()).candidate
        assert candidate is not None and candidate.source_current
        assert candidate.job.application_url==source["absolute_url"]
        assert candidate.source_ids==("greenhouse-acme",)
        person=CandidateProfile("sp43-synthetic-user",(
            ProfileFact("identity","Reviewed Candidate","user-entered",approved=True).normalized(),
            ProfileFact("email","reviewed@example.invalid","user-entered",approved=True).normalized(),
            ProfileFact("skill","SQL","user-entered",approved=True).normalized(),
        ))
        space=new_workspace(candidate,person,source_cv_text=(
            "Reviewed Candidate, SQL and Python experience, Helsinki."
        ))
        space=replace(space,cover_letter_text=(
            "Dear Hiring Team, I reviewed this Junior Data Engineer position. "
            "My SQL and Python experience supports its requirements. "
            "Kind regards, Reviewed Candidate."
        ))
        assert review_handoff(space,candidate,person)["ready"] is True
        packet=make_browser_packet(space,candidate,person)
        assert packet["application_url"]==source["absolute_url"]
        assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
        assert packet["fields"]["email"]=="reviewed@example.invalid"
        assert "SQL and Python experience, Helsinki" not in str(packet)
        assert calls==[("GET","https://boards-api.greenhouse.io/v1/boards/Acme/jobs?content=true")]
    finally:
        client.close()

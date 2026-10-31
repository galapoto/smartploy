"""KEHA P67 incomplete-identity handling: bounded, auditable, fail-closed."""

from copy import deepcopy
import json

import httpx
import pytest

from smartploy.service import SmartployService
from smartploy.sources.jobmarket_finland import (
    JobMarketFinlandAPIError,
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
    TEST_ENDPOINT,
    parse_ndjson,
)
from smartploy.sources.jobmarket_finland_polling import poll_jobmarket_finland
from smartploy.storage import MemoryJobRepository


def _published(index: int) -> dict:
    return {
        "metadata": {"externalId": f"keha-fixture-{index}"},
        "client": {"company": "Example Oy"},
        "owner": {"company": "Example Oy"},
        "position": {
            "title": {"fi": "Junior Data Analyst"},
            "jobDescription": {"fi": "SQL and reporting"},
        },
        "location": {
            "workplacePostOffice": "Helsinki",
            "countries": ["FI"],
        },
        "application": {
            "url": f"https://example.org/jobs/{index}",
            "published": "2026-10-30T08:00:00Z",
            "expires": "2027-01-30T08:00:00Z",
        },
    }


def _ndjson(*items: dict) -> bytes:
    return ("\n".join(json.dumps(item) for item in items) + "\n").encode("utf-8")


def _missing_title(index: int) -> dict:
    record = deepcopy(_published(index))
    record["position"]["title"] = {}
    return record


def _missing_id(index: int) -> dict:
    record = deepcopy(_published(index))
    record["metadata"].pop("externalId")
    return record


def _adapter(*items: dict) -> JobMarketFinlandAdapter:
    def handle(request: httpx.Request) -> httpx.Response:
        status = json.loads(request.content)["onlyStatus"]
        return httpx.Response(200, content=_ndjson(*items) if status == "PUBLISHED" else b"")

    settings = JobMarketFinlandSettings(
        environment="test", endpoint=TEST_ENDPOINT, subscription_key="fixture-secret"
    )
    return JobMarketFinlandAdapter(
        settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        quarantine_missing_identity=True,
    )


def test_strict_default_still_rejects_missing_identity():
    with pytest.raises(JobMarketFinlandAPIError, match="missing employer/title identity"):
        parse_ndjson(
            _ndjson(_published(1), _missing_title(2)),
            status="PUBLISHED",
            endpoint=TEST_ENDPOINT,
        )


def test_opt_in_quarantines_only_missing_identity_and_keeps_valid_records():
    batch = parse_ndjson(
        _ndjson(_published(1), _missing_title(2), _missing_id(3)),
        status="PUBLISHED",
        endpoint=TEST_ENDPOINT,
        quarantine_missing_identity=True,
    )
    assert batch.item_count == 1
    assert batch.quarantined_count == 2
    assert batch.observations[0].source_external_id == "keha-fixture-1"
    assert batch.observations[0].payload["external_ai_forwarding_allowed"] is False


def test_bounded_quarantine_marks_poll_degraded_and_preserves_valid_posting():
    adapter = _adapter(_published(1), _missing_title(2))
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)

    receipt = poll_jobmarket_finland(
        service,
        adapter,
        modified_from="2026-10-30T00:00:00Z",
        modified_to="2026-10-31T00:00:00Z",
    )
    assert receipt.status == "degraded"
    assert receipt.quarantined_count == 1
    assert receipt.blocked_count == 1
    assert receipt.discovered_count == 1
    assert len(repository.active_source_external_ids("job-market-finland")) == 1

    health = repository.get_source_health("job-market-finland")
    assert health is not None
    assert health.status == "degraded"
    assert health.metadata["quarantined_count"] == 1
    assert health.metadata["published_received_count"] == 2
    receipt_json = json.dumps(receipt.to_dict())
    assert "fixture-secret" not in receipt_json
    assert "SQL and reporting" not in receipt_json


def test_quarantine_budget_fails_before_any_job_is_ingested():
    adapter = _adapter(_published(1), _missing_title(2), _missing_title(3), _missing_id(4))
    repository = MemoryJobRepository()
    receipt = poll_jobmarket_finland(
        SmartployService(repository=repository),
        adapter,
        modified_from="2026-10-30T00:00:00Z",
        modified_to="2026-10-31T00:00:00Z",
    )
    assert receipt.status == "failed"
    assert receipt.discovered_count == 0
    assert repository.values() == []
    assert "quarantine limit exceeded" in receipt.error


def test_quarantine_never_ignores_invalid_json_or_archived_missing_id():
    with pytest.raises(JobMarketFinlandAPIError, match="invalid P67 NDJSON"):
        parse_ndjson(
            b'{"metadata": bad-json}\n',
            status="PUBLISHED",
            endpoint=TEST_ENDPOINT,
            quarantine_missing_identity=True,
        )
    with pytest.raises(JobMarketFinlandAPIError, match="missing metadata.externalId"):
        parse_ndjson(
            _ndjson({"metadata": {}}),
            status="ARCHIVED",
            endpoint=TEST_ENDPOINT,
            quarantine_missing_identity=True,
        )

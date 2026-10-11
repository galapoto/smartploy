"""Read-only Finland employer feed pilot safety, geography and operator activation."""
from __future__ import annotations

import json

import httpx
import pytest

from scripts.configure_finland_ats_pilot import (
    PilotConfigurationError, plan_env_update, plan_tsmg_transport_upgrade,
    reviewed_sources, stage_pilot
)
from smartploy.service import SmartployService
from smartploy.sources.public_ats import (
    LeverAdapter, PublicATSError, PublicATSRuntimeSettings,
    PublicATSSourceConfig, SmartRecruitersAdapter, load_public_ats_sources
)
from smartploy.sources.public_ats_polling import poll_public_ats
from smartploy.storage import MemoryJobRepository


def lever_item(identifier: str, location: str, country: str = "") -> dict:
    return {
        "id": identifier,
        "text": "Junior Data Analyst " + identifier,
        "descriptionPlain": "Python, SQL and dashboards",
        "categories": {
            "location": location,
            "allLocations": [location],
            "department": "Analytics",
        },
        "country": country,
        "hostedUrl": "https://jobs.lever.co/test-firm/" + identifier,
        "applyUrl": "https://jobs.lever.co/test-firm/" + identifier + "/apply",
    }


def test_public_ats_location_terms_validate_and_default_empty():
    default = PublicATSSourceConfig("lever", "test-firm", "Test Firm")
    assert default.location_terms == ()
    config = PublicATSSourceConfig(
        "lever", "test-firm", "Test Firm",
        location_terms=("Finland", "Helsinki", "Helsinki")
    )
    assert config.location_terms == ("finland", "helsinki")
    for invalid in ("Finland", (123,), ("X",), ("Foo\nBar",), tuple("city" for _ in range(21))):
        with pytest.raises(PublicATSError, match="location_terms"):
            PublicATSSourceConfig("lever", "test-firm", "Test Firm", location_terms=invalid)


def test_lever_only_imports_selected_locations_and_records_exclusions():
    payload = [
        lever_item("fi-1", "Helsinki"),
        lever_item("fi-2", "Remote", "FI"),
        lever_item("ee-1", "Tallinn", "EE"),
        lever_item("fr-1", "Paris", "FR"),
    ]

    def handler(request):
        assert request.url.host == "api.lever.co"
        return httpx.Response(200, json=payload)

    adapter = LeverAdapter(
        PublicATSSourceConfig(
            "lever", "test-firm", "Test Firm",
            location_terms=("Finland", "Helsinki")
        ),
        PublicATSRuntimeSettings(page_size=20),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    service = SmartployService(repository=MemoryJobRepository())
    first = poll_public_ats(service, adapter)
    assert first.status == "healthy"
    assert first.item_count == 2
    assert first.discovered_count == 2
    assert first.location_filtered_count == 2
    assert len(service.list_jobs()) == 2
    health = service.source_health(adapter.source_id)
    assert health is not None
    assert health.metadata["total_source_postings"] == 4
    assert health.metadata["location_filtered_count"] == 2
    assert health.metadata["external_ai_forwarding_allowed"] is False


def test_successful_location_change_retires_old_finland_listing():
    current = [lever_item("fi-1", "Helsinki")]

    def handler(request):
        return httpx.Response(200, json=current)

    adapter = LeverAdapter(
        PublicATSSourceConfig("lever", "test-firm", "Test Firm", location_terms=("Finland", "Helsinki")),
        PublicATSRuntimeSettings(page_size=10),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    repo = MemoryJobRepository()
    service = SmartployService(repository=repo)
    assert poll_public_ats(service, adapter).discovered_count == 1
    assert repo.active_source_external_ids(adapter.source_id) == {"fi-1"}
    current[:] = [lever_item("fi-1", "Stockholm", "SE")]
    second = poll_public_ats(service, adapter)
    assert second.retired_count == 1
    assert second.location_filtered_count == 1
    assert repo.active_source_external_ids(adapter.source_id) == set()


def test_smartrecruiters_location_terms_filter_detail_location():
    def handler(request):
        if request.url.path.endswith("/postings"):
            return httpx.Response(200, json={"content": [{"id": "fi"}, {"id": "se"}], "totalFound": 2})
        identifier = request.url.path.rsplit("/", 1)[-1]
        is_finland = identifier == "fi"
        return httpx.Response(200, json={
            "id": identifier,
            "name": "Data Analyst",
            "company": {"name": "Test Firm"},
            "location": {
                "city": "Helsinki" if is_finland else "Stockholm",
                "country": "Finland" if is_finland else "Sweden",
            },
            "jobAd": {"sections": {"jobDescription": {"text": "Data analytics role"}}},
        })

    adapter = SmartRecruitersAdapter(
        PublicATSSourceConfig(
            "smartrecruiters", "test-firm", "Test Firm",
            location_terms=("Finland", "Helsinki")
        ),
        PublicATSRuntimeSettings(page_size=10),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    observations = adapter.fetch_all()
    assert [item.source_external_id for item in observations] == ["fi"]
    assert adapter.last_location_filtered_count == 1
    assert adapter.last_total_postings == 2


def test_reviewed_pilot_is_explicit_opt_in_and_does_not_enable_ai(monkeypatch):
    sources = reviewed_sources()
    assert len(sources) == 5
    assert len({row["tenant"] for row in sources}) == 5
    assert all(row["external_ai_forwarding_allowed"] is False for row in sources)
    assert all(row["location_terms"] for row in sources)
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", json.dumps(sources))
    monkeypatch.delenv("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE", raising=False)
    loaded = load_public_ats_sources()
    assert len(loaded) == 5
    assert all(item.location_terms for item in loaded)


def test_private_env_staging_is_idempotent_and_refuses_override(tmp_path):
    source = tmp_path / "private.env"
    source.write_text(
        "POSTGRES_PASSWORD=not-printed\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    untouched = source.read_text()
    dry = stage_pilot(env=source)
    assert dry["private_env"] == "change_ready"
    assert source.read_text() == untouched
    applied = stage_pilot(env=source, apply=True)
    assert applied["source_count"] == 5
    assert applied["private_env"] == "updated"
    assert (source.stat().st_mode & 0o777) == 0o600
    assert "POSTGRES_PASSWORD=not-printed" in source.read_text()
    assert stage_pilot(env=source, apply=True)["private_env"] == "unchanged"
    data = source.read_text().replace("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=[", "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=other[")
    source.write_text(data)
    with pytest.raises(PilotConfigurationError, match="Refusing to override"):
        stage_pilot(env=source, apply=True)
    source.write_text("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=/tmp/custom.json\n")
    with pytest.raises(PilotConfigurationError, match="registry file"):
        stage_pilot(env=source)


def test_env_rejects_duplicate_values_and_preserves_unrelated_lines():
    with pytest.raises(PilotConfigurationError, match="Duplicate"):
        plan_env_update("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=\nSMARTPLOY_PUBLIC_ATS_SOURCES_JSON=\n", "[]")
    proposed, changed = plan_env_update("KUNTAREKRY_FEED_URL=\n", "[]")
    assert changed is True
    assert proposed.startswith("KUNTAREKRY_FEED_URL=\n")
    assert proposed.endswith("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=[]\n")


def test_reviewed_tsmg_transport_override_is_only_for_failing_source():
    registry = reviewed_sources()
    tsmg = next(item for item in registry if item["tenant"] == "tsmg")
    assert tsmg["request_timeout_seconds"] == 45
    assert tsmg["page_size"] == 50
    for item in registry:
        if item["tenant"] != "tsmg":
            assert "request_timeout_seconds" not in item
            assert "page_size" not in item


def test_upgrade_existing_private_pilot_is_dry_run_idempotent_and_scoped(tmp_path):
    old_registry = reviewed_sources()
    old_registry = [dict(item) for item in old_registry]
    tsmg = next(item for item in old_registry if item["tenant"] == "tsmg")
    tsmg.pop("request_timeout_seconds")
    tsmg.pop("page_size")

    path = tmp_path / "env"
    existing_json = json.dumps(old_registry, ensure_ascii=False, separators=(",", ":"))
    existing = (
        "POSTGRES_PASSWORD=private-password-never-printed\n"
        + "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + existing_json + "\n"
        + "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=\n"
    )
    path.write_text(existing, encoding="utf-8")
    path.chmod(0o600)

    report = stage_pilot(env=path, upgrade_tsmg_transport=True)
    assert report["private_env"] == "change_ready"
    assert report["transport_scope"] == "TSMG only"
    assert path.read_text() == existing

    applied = stage_pilot(env=path, upgrade_tsmg_transport=True, apply=True)
    assert applied["private_env"] == "updated"
    assert (path.stat().st_mode & 0o777) == 0o600
    final = path.read_text()
    assert "POSTGRES_PASSWORD=private-password-never-printed\n" in final
    assert json.loads(
        next(line.split("=", 1)[1] for line in final.splitlines()
             if line.startswith("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON="))
    ) == reviewed_sources()
    assert stage_pilot(env=path, upgrade_tsmg_transport=True, apply=True)["private_env"] == "unchanged"


def test_upgrade_refuses_operator_source_modifications_and_file_registry():
    original = reviewed_sources()
    previous = [dict(item) for item in original]
    target = next(item for item in previous if item["tenant"] == "tsmg")
    target.pop("request_timeout_seconds")
    target.pop("page_size")
    previous[0]["label"] = "Custom Employer Name"
    value = json.dumps(previous, separators=(",", ":"))
    with pytest.raises(PilotConfigurationError, match="operator-modified"):
        plan_tsmg_transport_upgrade("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + value + "\n", original)
    with pytest.raises(PilotConfigurationError, match="inline ATS pilot"):
        plan_tsmg_transport_upgrade(
            "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + value
            + "\nSMARTPLOY_PUBLIC_ATS_SOURCES_FILE=/some/custom.json\n", original,
        )

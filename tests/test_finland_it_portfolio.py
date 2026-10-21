"""Conservative, reversible nationwide Finland employer-source expansion.

No external network or employer application is used in regression tests.
"""
from __future__ import annotations

import json

import httpx
import pytest

from scripts.configure_finland_ats_pilot import (
    PilotConfigurationError, plan_it_portfolio_upgrade, reviewed_it_portfolio,
    reviewed_sources, stage_pilot,
)
from smartploy.career_scope import career_area
from smartploy.service import SmartployService
from smartploy.sources.public_ats import (
    GreenhouseAdapter, PublicATSSourceConfig, PublicATSRuntimeSettings,
)
from smartploy.sources.public_ats_polling import poll_public_ats
from smartploy.storage import MemoryJobRepository


def test_seven_actual_approved_public_employer_boards_and_full_country_markers(monkeypatch):
    settings = reviewed_it_portfolio()
    assert len(settings) == 7
    assert {(item["provider"], item["tenant"]) for item in settings} == {
        ("lever", "uprightproject"), ("lever", "brightlyworks"),
        ("lever", "netlight"), ("lever", "rovio-2"),
        ("greenhouse", "oura"), ("greenhouse", "wolt"),
        ("greenhouse", "smartlyio"),
    }
    assert all(len(item["location_terms"]) == 20 for item in settings)
    assert all("Finland" in item["location_terms"] for item in settings)
    assert all(item["external_ai_forwarding_allowed"] is False for item in settings)
    assert not any(item["tenant"] == "tsmg" for item in settings)
    from smartploy.sources.public_ats import load_public_ats_sources
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", json.dumps(settings))
    monkeypatch.delenv("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE", raising=False)
    loaded = load_public_ats_sources()
    assert len(loaded) == 7
    assert len({item.source_id for item in loaded}) == 7


def test_portfolio_private_upgrade_dry_run_apply_idempotent_and_reversible(tmp_path):
    original = reviewed_sources()
    updated = reviewed_it_portfolio()
    original_json = json.dumps(original, ensure_ascii=False, separators=(",", ":"))
    existing = (
        "# Synthetic only; never print private OVH settings\n"
        "POSTGRES_PASSWORD=synthetic-old-rotated-never-print\n"
        "SMARTPLOY_OIDC_ISSUER=https://auth.komplyint.fi\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + original_json + "\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=\n"
    )
    path = tmp_path / "env"
    path.write_text(existing, encoding="utf-8")
    path.chmod(0o600)

    dry = stage_pilot(env=path, upgrade_it_portfolio=True)
    assert dry["private_env"] == "change_ready"
    assert dry["source_count"] == 7
    assert path.read_text(encoding="utf-8") == existing

    result = stage_pilot(env=path, apply=True, upgrade_it_portfolio=True)
    assert result["private_env"] == "updated"
    assert result["source_count"] == 7
    assert (path.stat().st_mode & 0o777) == 0o600
    changed = path.read_text(encoding="utf-8")
    assert "synthetic-old-rotated-never-print" in changed
    assert "SMARTPLOY_OIDC_ISSUER=https://auth.komplyint.fi" in changed
    assert json.loads(next(line.split("=", 1)[1] for line in changed.splitlines()
                           if line.startswith("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON="))) == updated
    assert stage_pilot(env=path, apply=True, upgrade_it_portfolio=True)["private_env"] == "unchanged"
    rollback = stage_pilot(env=path, apply=True, rollback_it_portfolio=True)
    assert rollback["source_count"] == 5
    assert rollback["private_env"] == "updated"
    assert path.read_text(encoding="utf-8") == existing
    assert stage_pilot(env=path, apply=True, rollback_it_portfolio=True)["private_env"] == "unchanged"


def test_portfolio_refuses_modified_previous_sources_instead_of_clobbering(tmp_path):
    existing = reviewed_sources()
    existing[0]["label"] = "operator-owned-custom-name"
    path = tmp_path / "env"
    path.write_text(
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + json.dumps(existing) + "\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    with pytest.raises(PilotConfigurationError, match="operator-modified"):
        stage_pilot(env=path, apply=True, upgrade_it_portfolio=True)

    old = reviewed_sources()
    new = reviewed_it_portfolio()
    text = "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + json.dumps(old) + "\n"
    with pytest.raises(PilotConfigurationError, match="registry file"):
        plan_it_portfolio_upgrade(text + "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=/tmp/override.json\n", old, new)
    with pytest.raises(PilotConfigurationError, match="invalid JSON"):
        plan_it_portfolio_upgrade("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=\n", old, new)


def test_source_roster_rejects_rogue_board_and_removed_country(tmp_path):
    portfolio = reviewed_it_portfolio()
    path = tmp_path / "portfolio.json"
    portfolio[0]["tenant"] = "unexpected-new-employer"
    path.write_text(json.dumps(portfolio), encoding="utf-8")
    with pytest.raises(PilotConfigurationError, match="Unreviewed employer"):
        reviewed_it_portfolio(path)
    portfolio = reviewed_it_portfolio()
    portfolio[-1]["location_terms"] = ["Stockholm"]
    path.write_text(json.dumps(portfolio), encoding="utf-8")
    with pytest.raises(PilotConfigurationError, match="Country term Finland"):
        reviewed_it_portfolio(path)


def test_greenhouse_finland_poll_reuses_original_adapters_and_ignores_foreign_postings():
    positions = [
        {
            "id": 1, "internal_job_id": 111, "title": "Junior Data Engineer",
            "absolute_url": "https://job-boards.greenhouse.io/oura/jobs/1",
            "location": {"name": "Hybrid - Oulu, North Ostrobothnia"},
            "content": "Write Python data pipelines",
        },
        {
            "id": 2, "internal_job_id": 222, "title": "Software Developer",
            "absolute_url": "https://job-boards.greenhouse.io/oura/jobs/2",
            "location": {"name": "Tampere, Finland"},
            "content": "Develop software",
        },
        {
            "id": 3, "internal_job_id": 333, "title": "Truck Driver",
            "absolute_url": "https://job-boards.greenhouse.io/oura/jobs/3",
            "location": {"name": "Rovaniemi, Finland"},
            "content": "The job mentions Python apps and planning technology",
        },
        {
            "id": 4, "internal_job_id": 444, "title": "Data Engineer",
            "absolute_url": "https://job-boards.greenhouse.io/oura/jobs/4",
            "location": {"name": "Stockholm, Sweden"},
            "content": "Wrong country",
        },
        {
            "id": 5, "internal_job_id": None, "title": "Future Talent Pool",
            "absolute_url": "https://job-boards.greenhouse.io/oura/jobs/5",
            "location": {"name": "Helsinki, Finland"},
            "content": "No actual vacancy",
        },
    ]

    def handler(request):
        assert request.url.host == "boards-api.greenhouse.io"
        assert request.url.params.get("content") == "true"
        return httpx.Response(200, json={"jobs": positions, "meta": {"total": len(positions)}})

    config = PublicATSSourceConfig.from_dict(
        next(item for item in reviewed_it_portfolio() if item["tenant"] == "oura")
    )
    adapter = GreenhouseAdapter(
        config, PublicATSRuntimeSettings(max_items=100),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    repo = MemoryJobRepository()
    summary = poll_public_ats(SmartployService(repository=repo), adapter)
    assert summary.status == "healthy"
    assert summary.item_count == 3
    assert summary.location_filtered_count == 1
    assert adapter.last_prospect_filtered_count == 1
    assert summary.discovered_count == 3
    actual = {item.job.role_title: item for item in repo.values()}
    assert "Software Developer" in actual
    assert "Data Engineer" not in actual
    assert career_area(actual["Truck Driver"].job.role_title) == "other"
    assert all(job.job.raw["external_ai_forwarding_allowed"] is False for job in actual.values())

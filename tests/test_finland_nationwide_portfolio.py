"""SP19: source breadth + reversible staging; no real network or applicants."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from scripts.configure_finland_ats_pilot import (
    PilotConfigurationError,
    plan_nationwide_portfolio_upgrade,
    reviewed_it_portfolio,
    reviewed_nationwide_portfolio,
    reviewed_sources,
    stage_pilot,
)
from smartploy.sources.public_ats import (
    PublicATSSourceConfig, PublicATSRuntimeSettings, SmartRecruitersAdapter,
    load_public_ats_sources,
)


def _env(current):
    return (
        "# synthetic private env; never echo values\n"
        "POSTGRES_PASSWORD=synthetic-keep-private\n"
        "SMARTPLOY_OIDC_CLIENT_ID=synthetic-keep-id\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON="
        + json.dumps(current, separators=(",", ":"), ensure_ascii=False)
        + "\nSMARTPLOY_PUBLIC_ATS_SOURCES_FILE=\n"
    )


def test_nationwide_portfolio_is_22_distinct_finnish_boards_with_no_driver_pilot(monkeypatch):
    all_sources = reviewed_nationwide_portfolio()
    assert len(all_sources) == 22
    assert {p: sum(row["provider"] == p for row in all_sources)
            for p in ("lever", "greenhouse", "smartrecruiters")} == {
        "lever": 9, "greenhouse": 7, "smartrecruiters": 6,
    }
    assert not any(row["tenant"] == "tsmg" for row in all_sources)
    assert all(row["external_ai_forwarding_allowed"] is False for row in all_sources)
    assert all("Finland" in row["location_terms"] for row in all_sources)
    assert all("Oulu" in row["location_terms"] for row in all_sources)
    assert len({(x["provider"], x.get("stack", ""), x["tenant"]) for x in all_sources}) == 22
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", json.dumps(all_sources))
    monkeypatch.delenv("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE", raising=False)
    assert len({c.source_id for c in load_public_ats_sources()}) == 22


@pytest.mark.parametrize("baseline", ["five", "seven"])
def test_nationwide_upgrade_preserves_private_configuration_and_rollback(tmp_path, baseline):
    old = reviewed_sources() if baseline == "five" else reviewed_it_portfolio()
    env = tmp_path / "env"
    original = _env(old)
    env.write_text(original, encoding="utf-8")
    env.chmod(0o600)

    dry = stage_pilot(env=env, upgrade_nationwide_portfolio=True)
    assert dry["source_count"] == 22
    assert dry["private_env"] == "change_ready"
    assert env.read_text(encoding="utf-8") == original

    activated = stage_pilot(env=env, upgrade_nationwide_portfolio=True, apply=True)
    assert activated["private_env"] == "updated"
    assert activated["source_count"] == 22
    assert (env.stat().st_mode & 0o777) == 0o600
    after = env.read_text(encoding="utf-8")
    assert "synthetic-keep-private" in after
    assert "SMARTPLOY_OIDC_CLIENT_ID=synthetic-keep-id" in after
    assert "tsmg" not in next(x for x in after.splitlines()
                              if x.startswith("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON="))
    assert stage_pilot(env=env, upgrade_nationwide_portfolio=True)["private_env"] == "unchanged"

    rolled = stage_pilot(env=env, apply=True, **{
        "rollback_nationwide_to_five" if baseline == "five"
        else "rollback_nationwide_to_seven": True,
    })
    assert rolled["source_count"] == len(old)
    assert rolled["private_env"] == "updated"
    assert env.read_text(encoding="utf-8") == original


def test_nationwide_staging_rejects_changed_operator_roster_and_external_file(tmp_path):
    rogue = reviewed_it_portfolio()
    rogue[0]["label"] = "private-operator-custom-value"
    env = tmp_path / "env"
    original = _env(rogue)
    env.write_text(original, encoding="utf-8")
    env.chmod(0o600)
    with pytest.raises(PilotConfigurationError, match="operator-modified"):
        stage_pilot(env=env, upgrade_nationwide_portfolio=True, apply=True)
    assert env.read_text(encoding="utf-8") == original

    with pytest.raises(PilotConfigurationError, match="registry file"):
        plan_nationwide_portfolio_upgrade(
            _env(reviewed_sources())
            + "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=/private/unrelated.json\n",
            reviewed_sources(), reviewed_it_portfolio(), reviewed_nationwide_portfolio(),
        )
    with pytest.raises(PilotConfigurationError, match="Invalid portfolio rollback"):
        plan_nationwide_portfolio_upgrade(
            _env(reviewed_nationwide_portfolio()),
            reviewed_sources(), reviewed_it_portfolio(), reviewed_nationwide_portfolio(),
            rollback_to="custom",
        )


def test_nationwide_roster_rejects_rogue_boards_and_unscoped_locations(tmp_path):
    sources = reviewed_nationwide_portfolio()
    sources[0]["tenant"] = "arbitrary-unreviewed-board"
    candidate = tmp_path / "portfolio.json"
    candidate.write_text(json.dumps(sources), encoding="utf-8")
    with pytest.raises(PilotConfigurationError, match="Unreviewed employer"):
        reviewed_nationwide_portfolio(candidate)

    sources = reviewed_nationwide_portfolio()
    sources[0]["location_terms"] = ["Sweden"]
    candidate.write_text(json.dumps(sources), encoding="utf-8")
    with pytest.raises(PilotConfigurationError, match="Finland-scoped"):
        reviewed_nationwide_portfolio(candidate)


def test_smartrecruiters_prefilters_foreign_country_before_detail_fetch():
    """A Finnish board's global listing must not cause hundreds of foreign GETs."""
    listed = [
        {"id": "foreign", "location": {"country": "se", "city": "Stockholm"}},
        {"id": "finnish", "location": {"country": "FI", "city": "Oulu"}},
        {"id": "unknown", "location": {"city": "Tampere"}},
    ]
    detailed = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.smartrecruiters.com"
        if request.url.path.endswith("/postings"):
            assert request.url.params.get("destination") == "PUBLIC"
            return httpx.Response(200, json={"content": listed, "totalFound": 3})
        external_id = request.url.path.rsplit("/", 1)[1]
        detailed.append(external_id)
        if external_id == "foreign":
            pytest.fail("Foreign posting must be excluded before fetching details")
        return httpx.Response(200, json={
            "id": external_id, "name": "Information Management Planner",
            "company": {"name": "Synthetic Finnish Employer"},
            "location": {
                "country": "fi", "city": "Oulu" if external_id == "finnish" else "Tampere",
            },
            "postingUrl": "https://jobs.smartrecruiters.com/Synthetic/" + external_id,
            "jobAd": {"sections": {"jobDescription": {"text": "Intranet, Power BI and planning"}}},
        })

    settings = next(x for x in reviewed_nationwide_portfolio()
                    if x["provider"] == "smartrecruiters")
    config = PublicATSSourceConfig.from_dict(settings)
    adapter = SmartRecruitersAdapter(
        config, PublicATSRuntimeSettings(page_size=10, max_items=20),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    results = adapter.fetch_all(observed_at="2026-10-22T00:00:00Z")
    assert len(results) == 2
    assert detailed == ["finnish", "unknown"]
    assert adapter.last_total_postings == 3
    assert adapter.last_location_filtered_count == 1
    assert all(o.payload["role_title"] == "Information Management Planner" for o in results)


def test_nationwide_ovh_staging_uses_stock_python_without_site_packages(tmp_path):
    """Reproduce /usr/bin/python3 without pip packages on the Ubuntu host.

    The API/worker containers have httpx, but root-managed host staging must
    never require app imports or manipulate live env outside exact guard.
    """
    env = tmp_path / "private-env"
    original = _env(reviewed_sources())
    env.write_text(original, encoding="utf-8")
    env.chmod(0o600)
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "configure_finland_ats_pilot.py"
    runner = (
        "import json, runpy, sys; from pathlib import Path; "
        "script = runpy.run_path(sys.argv[1]); "
        "receipt = script['stage_pilot']("
        "env=Path(sys.argv[2]), upgrade_nationwide_portfolio=True); "
        "print(json.dumps(receipt, sort_keys=True))"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-S", "-c", runner, str(script), str(env)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert done.returncode == 0, done.stderr
    receipt = json.loads(done.stdout)
    assert receipt["source_count"] == 22
    assert receipt["private_env"] == "change_ready"
    assert "synthetic-keep-private" not in done.stdout
    assert env.read_text(encoding="utf-8") == original

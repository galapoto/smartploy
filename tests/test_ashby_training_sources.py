"""SP20: actual Ashby trainee jobs, public programme leads, safe source upgrade."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from scripts.configure_finland_ats_pilot import (
    PilotConfigurationError, reviewed_nationwide_portfolio,
    reviewed_ashby_trainee_portfolio, stage_pilot,
)
from smartploy.career_scope import opportunity_kind
from smartploy.service import SmartployService
from smartploy.sources.public_ats import (
    AshbyAdapter, PublicATSError, PublicATSSourceConfig, PublicATSRuntimeSettings,
    build_public_ats_adapter, load_public_ats_sources,
)
from smartploy.sources.public_ats_polling import poll_public_ats
from smartploy.storage import MemoryJobRepository
from smartploy.training_directory import TrainingDirectoryError, load_training_programs


def config() -> PublicATSSourceConfig:
    return PublicATSSourceConfig.from_dict({
        "provider": "ashby", "tenant": "hoxhunt", "label": "Hoxhunt",
        "location_terms": ["Finland", "FI", "Helsinki", "Espoo"],
        "external_ai_forwarding_allowed": False,
        "employer_sector": "private",
    })


def job(code: str, **overrides):
    value = {
        "title": "Junior Threat Analyst",
        "isListed": True,
        "jobUrl": f"https://jobs.ashbyhq.com/hoxhunt/{code}",
        "applyUrl": f"https://jobs.ashbyhq.com/hoxhunt/{code}/application",
        "location": "Helsinki, Finland", "isRemote": False,
        "descriptionPlain": "Local cybersecurity work. Power BI is useful.",
        "publishedAt": "2026-10-22T08:30:00+03:00",
        "employmentType": "Intern", "workplaceType": "Hybrid",
        "department": "Security",
    }
    value.update(overrides)
    return value


def test_ashby_public_api_ingests_only_listed_finnish_jobs_with_stable_ids():
    postings = [
        job("intern"),
        job("graduate", title="Graduate Data Engineer", employmentType="FullTime",
            location="Remote", isRemote=True, workplaceType="Remote",
            address={"postalAddress": {"addressCountry": "FI", "addressLocality": "Espoo"}}),
        job("foreign", location="Stockholm, Sweden",
            address={"postalAddress": {"addressCountry": "SE"}}),
        job("global", location="Anywhere", isRemote=True),
        job("unlisted", isListed=False, location="Helsinki, Finland"),
    ]
    observed_requests = []

    def serve(request: httpx.Request) -> httpx.Response:
        observed_requests.append(str(request.url))
        assert str(request.url) == "https://api.ashbyhq.com/posting-api/job-board/hoxhunt"
        assert request.method == "GET"
        return httpx.Response(200, json={"apiVersion": "1", "jobs": postings})

    adapter = build_public_ats_adapter(
        config(), PublicATSRuntimeSettings(max_items=30),
        http_client=httpx.Client(transport=httpx.MockTransport(serve)),
    )
    assert isinstance(adapter, AshbyAdapter)
    fetched = adapter.fetch_all(observed_at="2026-10-22T05:00:00Z")
    assert len(fetched) == 2
    assert adapter.last_total_postings == 5
    assert adapter.last_location_filtered_count == 2
    assert adapter.last_unlisted_filtered_count == 1
    assert fetched[0].source_external_id != fetched[1].source_external_id
    assert len(fetched[0].source_external_id) == 64
    assert fetched[0].posted_at == "2026-10-22T08:30:00+03:00"
    assert fetched[0].payload["external_ai_forwarding_allowed"] is False
    assert fetched[0].payload["source_details"]["employment_type"] == "Intern"
    assert fetched[1].payload["work_mode"] == "remote"
    assert len(observed_requests) == 1
    results = poll_public_ats(
        SmartployService(repository=MemoryJobRepository()),
        adapter,
    )
    assert results.status == "healthy"
    assert results.item_count == 2


def test_ashby_fail_closed_on_unlisted_malicious_url_and_truncated_board():
    good = job("h")
    responses = [
        {"jobs": [job("wrong-host", jobUrl="https://another.example.invalid/malicious")]},
        {"jobs": [job("other-board", jobUrl="https://jobs.ashbyhq.com/othercompany/id")]},
        {"jobs": "not a list"},
        {"jobs": [good] * 5},
    ]
    for entry in responses:
        adapter = AshbyAdapter(
            config(), PublicATSRuntimeSettings(max_items=3),
            http_client=httpx.Client(transport=httpx.MockTransport(
                lambda request, value=entry: httpx.Response(200, json=value)
            )),
        )
        with pytest.raises(PublicATSError):
            adapter.fetch_all()


def test_ashby_remote_flag_does_not_manufacture_a_finnish_workplace():
    entry = job("remote", location="Remote", isRemote=True, workplaceType="Remote",
                address={"postalAddress": {"addressCountry": "US"}})
    adapter = AshbyAdapter(
        config(), http_client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"jobs": [entry]})
        )),
    )
    assert adapter.fetch_all() == []


def test_ashby_source_fails_without_retiring_last_successful_positions():
    settings = config()
    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    ok = AshbyAdapter(settings, http_client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"jobs": [job("keep")]})
    )))
    initial = poll_public_ats(service, ok)
    assert initial.status == "healthy"
    failed = AshbyAdapter(settings, http_client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(502, json={"error": "temporarily unavailable"})
    )))
    snapshot = poll_public_ats(service, failed)
    assert snapshot.status == "failed"
    assert snapshot.retired_count == 0
    assert repository.values()[0].source_current is True


@pytest.mark.parametrize(("title", "employment", "expected"), [
    ("Software Engineer Intern", "Intern", "internship"),
    ("Harjoittelija, tietohallinto", "", "internship"),
    ("Data Analyst Trainee", "FullTime", "traineeship"),
    ("Oppisopimus IT-tukihenkilö", "", "traineeship"),
    ("Graduate Data Engineer", "FullTime", "graduate"),
    ("Graduate Programme - Project Office", "", "graduate"),
    ("Junior Software Tester", "FullTime", "job"),
    ("Customer Service", "Contract", "job"),
])
def test_opportunity_kind_only_uses_title_and_employer_classification(title, employment, expected):
    assert opportunity_kind(title, employment) == expected


def test_training_provider_links_not_counted_as_live_vacancies_or_autoapply():
    programs = load_training_programs()
    assert len(programs) == 12
    assert any("AI Academy F.E.C Uusimaa" in str(p["title"]) for p in programs)
    assert any("Software, Analytics & AI Academy" in str(p["title"]) for p in programs)
    assert {"Saranen", "Academic Work Academy", "Siemens", "Nokia"}.issubset(
        {p["provider"] for p in programs}
    )
    assert all(row["opening_status"] == "check_provider" for row in programs)
    assert all(row["counts_as_live_job"] is False for row in programs)
    assert all(row["automatic_application_authorized"] is False for row in programs)
    assert all(row["listing_type"] == "directory_link" for row in programs)


def test_directory_rejects_malicious_links_unknown_providers_and_duplicate_ids(tmp_path):
    registry = Path(__file__).resolve().parents[1] / "config" / "finland_training_program_directory.json"
    entries = json.loads(registry.read_text(encoding="utf-8"))
    target = tmp_path / "programs.json"
    entries[0]["url"] = "https://www.saranen.fi.evil.example/collect"
    target.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(TrainingDirectoryError, match="domain"):
        load_training_programs(target)
    entries[0]["url"] = "https://www.saranen.fi/tyonhakijalle"
    entries[0]["id"] = entries[1]["id"]
    target.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(TrainingDirectoryError, match="duplicate"):
        load_training_programs(target)


def test_29_board_roster_preserves_old_sources_and_locations(monkeypatch):
    existing = reviewed_nationwide_portfolio()
    growth = reviewed_ashby_trainee_portfolio()
    assert len(existing) == 22
    assert len(growth) == 29
    assert growth[:22] == existing
    assert {x["tenant"].casefold() for x in growth[22:]} == {
        "hoxhunt", "reaktor", "skylo", "swarmia",
        "distance", "zeal-network", "n8n",
    }
    assert all("Finland" in x["location_terms"] for x in growth)
    assert all(x["external_ai_forwarding_allowed"] is False for x in growth)
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", json.dumps(growth))
    monkeypatch.delenv("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE", raising=False)
    assert len({x.source_id for x in load_public_ats_sources()}) == 29


def test_ashby_29_board_operator_upgrade_and_rollback_on_stock_python(tmp_path):
    original = reviewed_nationwide_portfolio()
    env = tmp_path / "env"
    private = (
        "POSTGRES_PASSWORD=synthetic-secret-not-to-disclose\n"
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" +
        json.dumps(original, separators=(",", ":"), ensure_ascii=False) +
        "\nSMARTPLOY_PUBLIC_ATS_SOURCES_FILE=\n"
    )
    env.write_text(private, encoding="utf-8")
    env.chmod(0o600)
    dry = stage_pilot(env=env, upgrade_ashby_trainee_portfolio=True)
    assert dry["source_count"] == 29
    assert dry["private_env"] == "change_ready"
    assert env.read_text(encoding="utf-8") == private
    result = stage_pilot(env=env, upgrade_ashby_trainee_portfolio=True, apply=True)
    assert result["source_count"] == 29
    assert result["private_env"] == "updated"
    assert (env.stat().st_mode & 0o777) == 0o600
    assert stage_pilot(env=env, upgrade_ashby_trainee_portfolio=True)["private_env"] == "unchanged"
    back = stage_pilot(env=env, rollback_ashby_trainee_portfolio=True, apply=True)
    assert back["source_count"] == 22
    assert back["private_env"] == "updated"
    assert env.read_text(encoding="utf-8") == private

    # OVH host has stock Python without runtime Docker dependencies.
    argv = [
        sys.executable, "-I", "-S", "-c",
        "import json, runpy, sys; from pathlib import Path; "
        "script = runpy.run_path(sys.argv[1]); "
        "print(json.dumps(script['stage_pilot']("
        "env=Path(sys.argv[2]), upgrade_ashby_trainee_portfolio=True)))",
        str(Path(__file__).resolve().parents[1] / "scripts" / "configure_finland_ats_pilot.py"),
        str(env),
    ]
    done = subprocess.run(argv, text=True, capture_output=True, timeout=12, check=False)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["source_count"] == 29
    assert "synthetic-secret" not in done.stdout

    altered = json.loads(json.dumps(original))
    altered[0]["label"] = "operator-configured"
    env.write_text("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=" + json.dumps(altered) + "\n",
                   encoding="utf-8")
    with pytest.raises(PilotConfigurationError, match="operator-modified"):
        stage_pilot(env=env, upgrade_ashby_trainee_portfolio=True, apply=True)

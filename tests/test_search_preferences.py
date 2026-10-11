"""First-use job discovery is private, editable, and general-mode unprofiled."""
from __future__ import annotations

from dataclasses import replace
import os

from fastapi.testclient import TestClient
import pytest

from smartploy.api import create_app
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.search_preferences import (
    SearchPreferenceError, SearchPreferenceConflict,
    SearchPreferences, revise_preferences, search_jobs,
)
from smartploy.search_preference_storage import (
    MemorySearchPreferenceRepository, PostgresSearchPreferenceRepository,
)
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


SOURCE = SourcePolicy("manual-import", "Manual", "manual", ("manual",))


def job(title, location="Helsinki", language="", work_mode="review", company="Example Oy"):
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url="https://careers.example.fi/jobs/" + title.casefold().replace(" ", "-"),
            raw_text=title + " vacancy",
            observed_at="2026-10-11T10:00:00+00:00",
            payload={
                "company": company, "role_title": title,
                "description": "Work with data and Python",
                "location": location, "language": language, "work_mode": work_mode,
                "application_url": "https://careers.example.fi/jobs/" + title.casefold().replace(" ", "-"),
            },
        ),
        SOURCE,
    )
    assert result.candidate
    return result.candidate


def search_settings(**overrides):
    values = {
        "mode": "personalized",
        "roles": ["Data analyst", "Software tester"],
        "locations": ["Helsinki"],
        "languages": ["english"],
        "work_modes": ["remote", "hybrid"],
        "keywords": [],
        "skills": ["Python"],
        "seniority": "entry",
    }
    values.update(overrides)
    return values


def test_default_first_use_requires_choice_and_no_profile():
    blank = SearchPreferences(profile_id="new-user")
    assert blank.completed is False
    assert blank.mode == "personalized"
    assert blank.revision == 0
    results = search_jobs([job("Data Analyst")], blank)
    assert results["mode"] == "setup_required"
    assert results["available_count"] == 1
    assert results["recommendations"] == []
    assert results["all_jobs"] == []


def test_personalized_ranks_matching_titles_with_explanations_not_fake_qualification():
    selected = revise_preferences("one", search_settings(), revision=0)
    matches = search_jobs([
        job("Junior Data Analyst", location="Helsinki", language="English", work_mode="remote"),
        job("Senior Nurse", location="Turku", language="Finnish", work_mode="onsite"),
        job("Software Tester", location="Espoo", language="", work_mode="review"),
    ], selected)
    assert matches["mode"] == "personalized"
    assert matches["score_kind"] == "preference_alignment_not_verified_qualification"
    assert len(matches["recommendations"]) == 2
    best = matches["recommendations"][0]
    assert best["job"]["role_title"] == "Junior Data Analyst"
    assert best["preference_score"] > 50
    assert any("title" in text.casefold() for text in best["reasons"])
    assert all(row["job"]["role_title"] != "Senior Nurse" for row in matches["recommendations"])
    tester = next(row for row in matches["recommendations"] if "Tester" in row["job"]["role_title"])
    assert "Job language not specified" in tester["unknown_fields"]
    assert "Work arrangement not stated" in tester["unknown_fields"]
    assert len(matches["broader"]) == 1
    assert "experience" not in str(best["reasons"]).casefold() or best["preference_score"] <= 100


def test_declared_skills_help_rank_jobs_but_are_not_automatically_approved_cv_facts():
    pref = revise_preferences("candidate", search_settings(
        roles=["Data analyst"], skills=["Python", "Power BI"],
    ), revision=0)
    result = search_jobs([
        job("Junior Data Analyst"),
        job("General Store Manager", company="Unrelated Employer"),
    ], pref)
    first = result["recommendations"][0]
    assert first["preference_score"] > 0
    assert any("Your stated skills mentioned" in reason for reason in first["reasons"])
    assert "approved" not in first["reasons"][0].casefold()
    assert result["score_kind"] == "preference_alignment_not_verified_qualification"


def test_unknown_job_metadata_does_not_gain_full_match_credit():
    pref = revise_preferences("p", search_settings(roles=["Data Analyst"]), revision=0)
    incomplete = search_jobs([job("Data Analyst", location="", language="", work_mode="review")], pref)
    item = incomplete["recommendations"][0]
    assert item["preference_score"] < 100
    assert "Location not provided" in item["unknown_fields"]
    assert "Job language not specified" in item["unknown_fields"]
    assert "Work arrangement not stated" in item["unknown_fields"]


def test_general_and_equally_scored_searches_sort_by_posting_date_not_source_poll():
    original = job("Older Data Analyst")
    recent = job("Newer Data Analyst")
    older = replace(
        original, posted_at="2025-01-01T08:00:00Z",
        first_seen_at="2026-10-11T10:00:00Z", last_seen_at="2026-10-11T15:10:00Z",
    )
    newer = replace(
        recent, posted_at="2026-10-10T12:00:00+00:00",
        first_seen_at="2026-10-10T12:10:00Z", last_seen_at="2026-10-11T15:00:00Z",
    )
    general = revise_preferences("p", {"mode": "general"}, revision=0)
    result = search_jobs([older, newer], general)
    assert [entry["job"]["role_title"] for entry in result["all_jobs"]] == [
        "Newer Data Analyst", "Older Data Analyst",
    ]
    personal = revise_preferences("p", {
        "mode": "personalized", "roles": ["Data Analyst"],
    }, revision=0)
    result = search_jobs([older, newer], personal)
    assert result["recommendations"][0]["job"]["role_title"] == "Newer Data Analyst"



def test_keyword_matches_are_recommended_even_if_saved_titles_differ():
    pref = revise_preferences("p", search_settings(
        roles=["Software tester"], keywords=["Python"], seniority="any",
        skills=[], locations=[], languages=[], work_modes=[],
    ), revision=0)
    result = search_jobs([job("Data Analyst")], pref)
    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0]["job"]["role_title"] == "Data Analyst"
    assert any("Keywords: Python" in reason for reason in result["recommendations"][0]["reasons"])


def test_explicit_seniority_conflicts_are_visible_in_explore_more():
    pref = revise_preferences("p", search_settings(
        roles=["Data Analyst"], seniority="entry",
    ), revision=0)
    result = search_jobs([
        job("Senior Data Analyst", language="Finnish", work_mode="onsite"),
        job("Junior Data Analyst", language="English", work_mode="remote"),
    ], pref)
    assert [item["job"]["role_title"] for item in result["recommendations"]] == ["Junior Data Analyst"]
    senior = result["broader"][0]
    assert senior["job"]["role_title"] == "Senior Data Analyst"
    assert "Listed senior role differs from your entry experience preference" in senior["mismatched_fields"]
    assert "Advertised language differs from preferred languages" in senior["mismatched_fields"]
    assert "Work arrangement differs from preferred arrangements" in senior["mismatched_fields"]
    assert senior["preference_score"] < 100


def test_unknown_job_seniority_remains_discoverable_not_falsely_matched():
    pref = revise_preferences("p", search_settings(roles=["Data Analyst"], seniority="entry"), revision=0)
    result = search_jobs([job("Data Analyst")], pref)
    assert len(result["recommendations"]) == 1
    assert "Experience level not specified" in result["recommendations"][0]["unknown_fields"]
    assert result["recommendations"][0]["mismatched_fields"] == []


def test_general_mode_ignores_saved_personal_criteria():
    prefs = revise_preferences("p", search_settings(
        mode="general", roles=["Data Analyst"], keywords=["python"],
        locations=["Helsinki"], languages=["english"]), revision=0)
    source = [
        job("Senior Nurse", location="Turku"),
        job("Data Analyst", location="Helsinki"),
    ]
    output = search_jobs(source, prefs)
    assert output["mode"] == "general"
    assert output["available_count"] == 2
    assert len(output["all_jobs"]) == 2
    assert output["recommendations"] == []
    assert output["broader"] == []
    assert all(row["preference_score"] is None and not row["reasons"]
               for row in output["all_jobs"])
    assert all("raw" not in row["job"] and "description" not in row["job"]
               for row in output["all_jobs"])


def test_preference_validation_limits_bad_inputs():
    for changes in (
        {"mode": "automatic_apply"},
        {"roles": []},
        {"roles": ["bad\x00job"]},
        {"roles": ["x" * 91]},
        {"roles": ["data"] * 13},
        {"languages": ["Portuguese"]},
        {"work_modes": ["maybe"]},
        {"seniority": "superexpert"},
        {"keywords": ["one"] * 13},
        {"skills": ["one"] * 17},
        {"locations": ["x" * 100]},
    ):
        with pytest.raises(SearchPreferenceError):
            revise_preferences("user", search_settings(**changes), revision=0)
    chosen = revise_preferences("user", search_settings(
        roles=["Data Analyst", "data analyst", "Software tester"],
        languages=["ENGLISH", "finnish"]), revision=0)
    assert chosen.roles == ("Data Analyst", "Software tester")
    assert chosen.languages == ("english", "finnish")


def test_memory_preferences_stay_isolated_and_switch_modes_in_place():
    store = MemorySearchPreferenceRepository()
    assert store.get("alice").completed is False
    alice = store.save("alice", search_settings(), expected_revision=0)
    assert alice.mode == "personalized"
    assert alice.revision == 1
    assert store.get("bob").completed is False
    with pytest.raises(SearchPreferenceConflict):
        store.save("alice", search_settings(mode="general"), expected_revision=0)
    general = store.save("alice", search_settings(mode="general"), expected_revision=1)
    assert general.mode == "general"
    assert general.roles == alice.roles  # kept for a later return to personalized mode
    restored = store.save("alice", search_settings(), expected_revision=2)
    assert restored.mode == "personalized"
    assert store.get("bob").revision == 0


def test_authenticated_api_first_use_to_personalized_and_back_to_general():
    service = SmartployService()
    service.register_source(SOURCE)
    client = TestClient(create_app(service))
    source = client.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "raw_text": "Junior data analyst",
            "payload": {
                "company": "Example Oy", "role_title": "Junior Data Analyst",
                "description": "Python and SQL", "location": "Helsinki",
                "language": "English", "work_mode": "remote",
            },
        }
    })
    assert source.status_code == 200, source.text
    initial = client.get("/api/v1/search-preferences")
    assert initial.status_code == 200
    assert initial.json()["completed"] is False
    assert client.get("/api/v1/search-results").json()["mode"] == "setup_required"
    failed = client.put("/api/v1/search-preferences", json={
        **search_settings(), "expected_revision": 0, "profile_id": "victim"
    })
    assert failed.status_code == 422
    set_personalized = client.put("/api/v1/search-preferences", json={
        **search_settings(), "expected_revision": 0,
    })
    assert set_personalized.status_code == 200, set_personalized.text
    assert set_personalized.json()["completed"] is True
    assert set_personalized.json()["revision"] == 1
    results = client.get("/api/v1/search-results").json()
    assert results["mode"] == "personalized"
    assert len(results["recommendations"]) == 1
    assert results["recommendations"][0]["preference_score"] > 50
    stale = client.put("/api/v1/search-preferences", json={
        **search_settings(mode="general"), "expected_revision": 0,
    })
    assert stale.status_code == 409
    general = client.put("/api/v1/search-preferences", json={
        "mode": "general", "expected_revision": 1,
    })
    assert general.status_code == 200, general.text
    assert general.json()["revision"] == 2
    all_jobs = client.get("/api/v1/search-results").json()
    assert all_jobs["mode"] == "general"
    assert len(all_jobs["all_jobs"]) == 1
    assert all_jobs["all_jobs"][0]["preference_score"] is None
    assert all_jobs["external_actions_authorized"] is False
    assert client.get("/api/v1/applications/summary").json()["actually_submitted"] == 0


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="requires PostgreSQL test database")
def test_postgres_preferences_persist_and_concurrent_edit_is_rejected():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    from psycopg import connect
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM smartploy_search_preferences WHERE profile_id LIKE 'search-test-%'")
    repo = PostgresSearchPreferenceRepository(dsn)
    assert repo.get("search-test-alice").completed is False
    alice = repo.save("search-test-alice", search_settings(), expected_revision=0)
    assert alice.revision == 1
    assert repo.get("search-test-bob").completed is False
    assert PostgresSearchPreferenceRepository(dsn).get("search-test-alice").roles == alice.roles
    with pytest.raises(SearchPreferenceConflict):
        repo.save("search-test-alice", search_settings(mode="general"), expected_revision=0)
    general = repo.save("search-test-alice", search_settings(mode="general"), expected_revision=1)
    assert general.mode == "general" and general.revision == 2
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM smartploy_search_preferences WHERE profile_id LIKE 'search-test-%'")


def test_inline_brand_mark_and_favicon_have_separate_static_assets():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    icon = (root / "web/public/smartploy-mark-v2.svg").read_text(encoding="utf-8")
    app = (root / "web/src/App.tsx").read_text(encoding="utf-8")
    brand = (root / "web/src/BrandMark.tsx").read_text(encoding="utf-8")
    html = (root / "web/index.html").read_text(encoding="utf-8")
    assert 'viewBox="0 0 192 192"' in icon
    assert "#06D9E8" in icon and "#021E3D" in icon
    assert "BrandMark className" in app
    assert "smartploy-mark-v2.svg?v=2" in html
    assert "src=\"/smartploy-mark.png\"" not in app
    assert "<svg" in brand

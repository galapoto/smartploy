"""Finland-wide technical/planning browse and driver false-positive regression."""
from __future__ import annotations

import pytest

from smartploy.career_scope import career_area, relevant_career_title, title_experience
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.search_preferences import revise_preferences, search_jobs

POLICY = SourcePolicy("career-fixtures", "Synthetic", "manual", ("manual",))


def posting(title: str, description: str = "The employer uses Python for scheduling"):
    result = normalize_observation(SourceObservation(
        source_id="career-fixtures", source_mode="manual",
        source_url="https://jobs.example.invalid/test/" + str(len(title)) + title.replace(" ", "-"),
        raw_text="Synthetic " + title,
        observed_at="2026-10-21T09:00:00+00:00",
        source_external_id=title,
        payload={
            "company": "Synthetic Employer Oy", "role_title": title,
            "location": "Rovaniemi, Finland", "description": description,
            "application_url": "https://jobs.example.invalid/" + str(len(title)),
        },
    ), POLICY)
    assert result.candidate is not None
    return result.candidate


@pytest.mark.parametrize(("title", "category"), [
    ("Junior Data Engineer", "it_data"),
    ("Data-analyytikko", "it_data"),
    ("Software Tester", "it_data"),
    ("ICT Specialist", "it_data"),
    ("IT-tukihenkilö", "it_data"),
    ("Ohjelmistosuunnittelija", "it_data"),
    ("Azure Cloud Engineer", "it_data"),
    ("Kyberturva-asiantuntija", "it_data"),
    ("AI Business Analyst", "it_data"),
    ("Power BI Developer", "it_data"),
    ("Suunnittelija", "planning"),
    ("Projektikoordinaattori", "planning"),
    ("Hankesuunnittelija", "planning"),
    ("Project Planner", "planning"),
    ("Urban Planner", "planning"),
    ("Environmental Engineer", "planning"),
    ("Delivery Driver", "other"),
    ("Truck Driver", "other"),
    ("Kuljettaja, Kuopio", "other"),
    ("IT delivery driver", "other"),
    ("Data Entry Clerk", "other"),
    ("Kitchen Assistant", "other"),
    ("Sales Representative", "other"),
    ("Warehouse Worker", "other"),
])
def test_title_career_classification_never_reads_job_description(title, category):
    assert career_area(title) == category
    assert relevant_career_title(title) == (category != "other")


@pytest.mark.parametrize(("title", "level"), [
    ("Junior Data Engineer", "entry"),
    ("Nuorempi suunnittelija", "entry"),
    ("Trainee Software Developer", "entry"),
    ("Senior Data Engineer", "senior"),
    ("Johtava järjestelmäasiantuntija", "senior"),
    ("Lead Project Coordinator", "senior"),
    ("Data Engineer", "unspecified"),
    ("Suunnittelija", "unspecified"),
])
def test_only_explicit_title_seniority_is_labeled(title, level):
    assert title_experience(title) == level


def test_general_search_remains_complete_but_metadata_enables_it_first_view():
    jobs = [
        posting("Junior Data Engineer"),
        posting("Suunnittelija"),
        posting("Driver", "SQL, Azure and Python apps used on the road"),
        posting("Senior Software Developer"),
    ]
    general = revise_preferences("synthetic-user", {"mode": "general"}, revision=0)
    out = search_jobs(jobs, general)
    assert len(out["all_jobs"]) == out["available_count"] == 4
    by_title = {card["job"]["role_title"]: card["job"] for card in out["all_jobs"]}
    assert by_title["Junior Data Engineer"]["career_area"] == "it_data"
    assert by_title["Junior Data Engineer"]["title_experience"] == "entry"
    assert by_title["Suunnittelija"]["career_area"] == "planning"
    assert by_title["Driver"]["career_area"] == "other"
    assert by_title["Senior Software Developer"]["title_experience"] == "senior"
    assert all(card["preference_score"] is None for card in out["all_jobs"])


def test_keyword_in_driver_description_cannot_be_recommended_for_it_user():
    pref = revise_preferences("synthetic-user", {
        "mode": "personalized", "roles": ["Data Engineer", "Suunnittelija"],
        "keywords": ["Python"], "seniority": "entry",
    }, revision=0)
    jobs = [
        posting("Driver", "We use Python to plan driving routes"),
        posting("Junior Data Engineer", "Use Python and SQL"),
        posting("Junior suunnittelija", "Planning and Python"),
    ]
    result = search_jobs(jobs, pref)
    rec = {v["job"]["role_title"] for v in result["recommendations"]}
    assert "Driver" not in rec
    assert "Junior Data Engineer" in rec
    driver = next(c for c in result["broader"] if c["job"]["role_title"] == "Driver")
    assert "Job title is outside your IT or planning career targets" in driver["mismatched_fields"]


def test_explicit_unrelated_target_does_not_get_blocked_by_it_focus():
    pref = revise_preferences("synthetic-user", {
        "mode": "personalized", "roles": ["Driver"],
        "keywords": ["Python"],
    }, revision=0)
    res = search_jobs([posting("Driver", "Uses Python")], pref)
    assert len(res["recommendations"]) == 1

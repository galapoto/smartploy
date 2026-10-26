"""SP21: real CV-file-to-current-database matching, zero employer actions."""
from __future__ import annotations

from base64 import b64encode
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile
import json

from fastapi.testclient import TestClient
import pytest

from smartploy.api import create_app
from smartploy.cv_job_matching import cv_job_matches, detected_cv_signals
from smartploy.cv_storage import StoredCV
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.service import SmartployService


SOURCE = SourcePolicy("manual-import", "Manual", "manual", ("manual",))


def vacancy(title: str, description: str = "Data analysis and Power BI"):
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import",
            source_mode="manual",
            source_url="https://jobs.example.invalid/" + title.casefold().replace(" ", "-"),
            raw_text=title + "\n" + description,
            payload={
                "company": "Synthetic Employer",
                "role_title": title,
                "description": description,
                "location": "Helsinki",
                "application_url": "https://jobs.example.invalid/" + title.casefold().replace(" ", "-"),
            },
            observed_at="2026-10-22T06:00:00+00:00",
        ),
        SOURCE,
    )
    assert result.candidate is not None
    return result.candidate


def stored(profile: str, text: str) -> StoredCV:
    return StoredCV(
        profile_id=profile, filename="My Career CV.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"synthetic cv fixture", text=text, updated_at="2026-10-22T06:00:00Z",
    )


def _docx(text: str) -> bytes:
    doc = BytesIO()
    with ZipFile(doc, "w") as z:
        z.writestr("[Content_Types].xml", "<Types />")
        z.writestr("word/document.xml",
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
    return doc.getvalue()


def test_vahehyva_planner_cv_finds_current_office_and_data_roles_without_approved_facts():
    text = ("Planner, Suunnittelija in public administration. "
            "Responsible for intranet, SharePoint, Power BI reporting and project coordination. "
            "Private email person-private@example.invalid should never appear in matches.")
    roles, topics = detected_cv_signals(text)
    assert "Suunnittelija" in roles
    assert "Power BI" in topics
    assert "SharePoint" in topics
    jobs = [
        vacancy("Toimistosuunnittelija"),
        vacancy("IT Suunnittelija"),
        vacancy("Junior Data Analyst"),
        vacancy("Delivery Driver", "This van driver job uses Power BI and SharePoint occasionally"),
    ]
    matches = cv_job_matches(stored("candidate", text), jobs, profile_id="candidate")
    assert matches["cv_present"] is True
    assert matches["matched_from"] == "local_cv_text_not_approved_evidence"
    assert matches["qualifications_verified"] is False
    assert matches["employer_actions_performed"] is False
    assert matches["current_jobs_count"] == 4
    names = {row["job"]["role_title"] for row in matches["recommended"]}
    assert "IT Suunnittelija" in names
    # An office-planning related title is still visible in Explore more,
    # without falsely claiming a direct title match from this CV.
    related = {row["job"]["role_title"] for row in matches["other_jobs"]}
    assert "Toimistosuunnittelija" in names | related
    assert "Delivery Driver" not in names
    assert all(row["job"]["source_current"] for row in matches["recommended"])
    assert "person-private@example.invalid" not in json.dumps(matches)


def test_missing_cv_requires_upload_and_no_cv_signals_do_not_fabricate_matching():
    jobs = [vacancy("Junior Data Analyst"), vacancy("Office Planner")]
    empty = cv_job_matches(None, jobs, profile_id="p")
    assert empty["match_mode"] == "upload_cv"
    assert empty["recommended"] == []
    assert empty["current_jobs_count"] == 2
    ambiguous = cv_job_matches(stored("p", "Candidate worked in various locations and sectors."), jobs, profile_id="p")
    assert ambiguous["match_mode"] == "no_recognized_cv_signals"
    assert ambiguous["recommended"] == []
    assert len(ambiguous["other_jobs"]) == 2
    assert all(row["preference_score"] is None for row in ambiguous["other_jobs"])


def test_cross_owner_cv_is_rejected_and_outdated_jobs_are_not_returned():
    cv = stored("alice", "I am a planner and a data analyst with Python skills.")
    with pytest.raises(ValueError, match="owner"):
        cv_job_matches(cv, [vacancy("Data Analyst")], profile_id="bob")
    old = replace(vacancy("Office Planner"), source_current=False)
    matches = cv_job_matches(cv, [old, vacancy("Data Analyst")], profile_id="alice")
    assert matches["current_jobs_count"] == 1
    assert all(row["job"]["role_title"] != "Office Planner"
               for row in matches["recommended"] + matches["other_jobs"])


def test_cv_upload_then_read_only_matches_uses_actual_database_not_user_preferences():
    service = SmartployService()
    service.register_source(SOURCE)
    for name in ("Office Planner", "Delivery Driver", "Data Analyst"):
        result = service.ingest(SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url="https://jobs.example.invalid/" + name.lower().replace(" ","-"),
            raw_text=name + " vacancy",
            observed_at="2026-10-22T06:00:00+00:00",
            payload={
                "company": "Employer", "role_title": name,
                "location": "Espoo", "description": "Intranet, Excel and Power BI",
                "application_url": "https://jobs.example.invalid/" + name.lower().replace(" ","-"),
            },
        ))
        assert result.status == "discovered"

    client = TestClient(create_app(service))
    before = client.get("/api/v1/profile/cv/matches")
    assert before.status_code == 200
    assert before.json()["cv_present"] is False
    assert before.headers["cache-control"] == "private, no-store"
    doc = _docx("Experienced planner, Suunnittelija. Power BI, intranet and SharePoint office work.")
    uploaded = client.post("/api/v1/profile/cv", json={
        "filename": "Planner.docx",
        "content_base64": b64encode(doc).decode(),
    })
    assert uploaded.status_code == 200, uploaded.text
    assert client.get("/api/v1/profile/status").json()["approved_fact_count"] == 0
    matches = client.get("/api/v1/profile/cv/matches")
    assert matches.status_code == 200, matches.text
    data = matches.json()
    assert data["cv_present"] is True
    assert data["current_jobs_count"] == 3
    assert data["recommended_count"] >= 1
    assert data["employer_actions_performed"] is False
    assert all(row["job"]["role_title"] != "Delivery Driver"
               for row in data["recommended"])
    assert "Power BI, intranet" not in matches.text
    assert "Planner.docx" == data["cv_filename"]
    assert client.get("/api/v1/search-results").json()["mode"] == "setup_required"
    # Even without separately saving search preferences, matches now work.
    client.delete("/api/v1/profile/cv")
    assert client.get("/api/v1/profile/cv/matches").json()["cv_present"] is False


def test_sp48_pages_all_current_jobs_and_pins_exact_job_beyond_first_page():
    jobs = [vacancy(f"Junior Data Analyst {number:03d}") for number in range(175)]
    cv = stored("p", "Experienced Data Analyst, Power BI and Python.")
    first = cv_job_matches(cv, jobs, profile_id="p", max_items=30)
    assert first["recommended_count"] == 175
    assert first["other_jobs_count"] == 0
    assert len(first["recommended"]) == 30
    later = cv_job_matches(
        cv, jobs, profile_id="p", max_items=30,
        recommended_offset=130, selected_job_key=jobs[157].canonical_key,
    )
    assert len(later["recommended"]) == 30
    assert later["recommended_count"] == 175
    assert later["selected_job"]["canonical_key"] == jobs[157].canonical_key
    assert later["selected_job"]["job"]["source_current"] is True
    assert not (
        {item["canonical_key"] for item in first["recommended"]}
        & {item["canonical_key"] for item in later["recommended"]}
    )
    filtered = cv_job_matches(
        cv, jobs, profile_id="p", max_items=20,
        query="Analyst 157", selected_job_key=jobs[3].canonical_key,
    )
    assert filtered["recommended_count"] == 1
    assert filtered["recommended"][0]["canonical_key"] == jobs[157].canonical_key
    assert filtered["selected_job"]["canonical_key"] == jobs[3].canonical_key
    assert filtered["current_jobs_count"] == 175
    retired = [replace(j, source_current=False) if j.canonical_key ==
               jobs[157].canonical_key else j for j in jobs]
    assert cv_job_matches(
        cv, retired, profile_id="p",
        selected_job_key=jobs[157].canonical_key,
    )["selected_job"] is None


def test_sp48_paginated_other_jobs_without_recognized_cv_signals():
    jobs = [vacancy(f"Office Coordinator {number:03d}") for number in range(135)]
    cv = stored("p", "My career history includes different tasks.")
    first = cv_job_matches(cv, jobs, profile_id="p", max_items=40)
    assert first["match_mode"] == "no_recognized_cv_signals"
    assert first["recommended_count"] == 0
    assert first["other_jobs_count"] == 135
    assert len(first["other_jobs"]) == 40
    later = cv_job_matches(cv, jobs, profile_id="p", max_items=40, other_offset=120)
    assert len(later["other_jobs"]) == 15
    found = cv_job_matches(cv, jobs, profile_id="p", query="Coordinator 128")
    assert len(found["other_jobs"]) == 1
    assert found["other_jobs"][0]["canonical_key"] == jobs[128].canonical_key


@pytest.mark.parametrize("options", [
    {"max_items": 0}, {"max_items": 301}, {"max_items": True},
    {"recommended_offset": -1}, {"other_offset": 100001},
    {"other_offset": True}, {"query": "x" * 121},
    {"query": "planner\nadmin"}, {"selected_job_key": "x" * 161},
    {"selected_job_key": "job\x00secret"},
])
def test_sp48_invalid_cv_search_windows_refuse(options):
    with pytest.raises(ValueError, match="Invalid"):
        cv_job_matches(stored("p", "Data Analyst"), [vacancy("Data Analyst")],
                       profile_id="p", **options)


def test_sp48_api_read_only_paging_filter_and_selected_job_without_match_leak():
    service = SmartployService()
    service.register_source(SOURCE)
    for number in range(132):
        result = service.ingest(SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url=f"https://jobs.example.invalid/junior-data-analyst-{number:03d}",
            raw_text=f"Junior Data Analyst {number:03d} vacancy",
            observed_at="2026-10-22T06:00:00+00:00",
            payload={
                "company": "Synthetic Employer",
                "role_title": f"Junior Data Analyst {number:03d}",
                "location": "Helsinki",
                "description": "Data analysis and Power BI",
                "application_url":
                    f"https://jobs.example.invalid/junior-data-analyst-{number:03d}",
            },
        ))
        assert result.status == "discovered"
    client = TestClient(create_app(service))
    doc = _docx("Experienced Data Analyst and Power BI specialist.")
    assert client.post("/api/v1/profile/cv", json={
        "filename": "Career.docx", "content_base64": b64encode(doc).decode(),
    }).status_code == 200
    first = client.get("/api/v1/profile/cv/matches", params={"limit": 20})
    assert first.status_code == 200
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json()["recommended_count"] == 132
    assert len(first.json()["recommended"]) == 20
    selected = first.json()["recommended"][0]["canonical_key"]
    filtered = client.get("/api/v1/profile/cv/matches", params={
        "limit": 20, "query": "Analyst 127", "recommended_offset": 0,
        "selected_job_key": selected,
    })
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["recommended_count"] == 1
    assert payload["selected_job"]["canonical_key"] == selected
    assert payload["recommended"][0]["job"]["role_title"] == "Junior Data Analyst 127"
    assert payload["employer_actions_performed"] is False
    assert client.get("/api/v1/profile/cv/matches", params={"limit": 101}).status_code == 422
    assert client.get(
        "/api/v1/profile/cv/matches", params={"recommended_offset": -1}
    ).status_code == 422
    assert client.get(
        "/api/v1/profile/cv/matches", params={"query": "a" * 121}
    ).status_code == 422

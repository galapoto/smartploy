"""Matched IT jobs -> owned, review-only application drafts.

All tests reuse original source normalization, search scoring, profile/CV
approval and deterministic workspace idempotency. No LLM or employer API.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.auto_application_queue import (
    AutoDraftSetupRequired, _usable_application_url,
    prepare_matching_application_drafts,
)
from smartploy.application_workspace_storage import MemoryWorkspaceRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.search_preferences import revise_preferences, SearchPreferences
from smartploy.service import SmartployService


SOURCE = SourcePolicy("manual-import", "Manual", "manual", ("manual",))


def candidate(title="Junior Data Analyst", *, city="Helsinki", app_url=None):
    slug = title.casefold().replace(" ", "-")
    url = app_url if app_url is not None else "https://careers.example.fi/jobs/" + slug
    result = normalize_observation(SourceObservation(
        source_id="manual-import",source_mode="manual",
        source_url="https://careers.example.fi/jobs/" + slug,
        raw_text=title+" Python SQL work in Helsinki.",
        payload={
            "company":"Example Oy", "role_title":title,
            "description":"Use Python SQL to analyze data",
            "location":city, "language":"English",
            "work_mode":"remote", "application_url":url,
        },
    ),SOURCE)
    assert result.candidate is not None
    return result.candidate


def profile(profile_id="local-auto-alice"):
    return CandidateProfile(profile_id=profile_id,facts=(
        ProfileFact("identity","Synthetic Candidate","user-entered",approved=True).normalized(),
        ProfileFact("skill","SQL","user-entered",approved=True).normalized(),
    ))


def prefs(profile_id="local-auto-alice", **overrides):
    data={
        "mode":"personalized","roles":["Data Analyst"],"locations":["Helsinki"],
        "languages":["english"],"work_modes":["remote"],"skills":[],
        "keywords":[],"seniority":"entry","auto_drafts_enabled":True,
    }
    data.update(overrides)
    return revise_preferences(profile_id,data,revision=0)


def test_auto_drafting_reuses_ranked_current_job_and_never_sends_to_employer():
    repository=MemoryWorkspaceRepository()
    result=prepare_matching_application_drafts(
        profile=profile(),preferences=prefs(),
        candidates=[
            candidate(),candidate("Senior Data Analyst"),
            candidate("QA Engineer"),
            replace(candidate("Data Analyst"),source_current=False),
        ],
        workspace_repository=repository,
        now=datetime.now(timezone.utc),
    )
    data=result.to_dict()
    assert data["created_count"]==1, data
    assert data["created"][0]["role_title"]=="Junior Data Analyst"
    assert data["requires_owner_review"] is True
    assert data["actual_employer_submissions"]==0
    assert data["external_ai_forwarding_performed"] is False
    assert data["external_actions_authorized"] is False
    kit=repository.list(profile().profile_id)
    assert len(kit)==1
    assert kit[0].status=="draft"
    assert kit[0].to_dict()["authority"]["may_submit_to_employer"] is False
    assert "Synthetic Candidate" in kit[0].cv_text
    assert "[Explain why you are interested" in kit[0].cover_letter_text
    rerun=prepare_matching_application_drafts(
        profile=profile(),preferences=prefs(),candidates=[candidate()],
        workspace_repository=repository,
    )
    assert rerun.created==()
    assert len(repository.list(profile().profile_id))==1


def test_auto_drafts_never_prepare_another_owner_or_unspecified_criteria():
    repository=MemoryWorkspaceRepository()
    with pytest.raises(AutoDraftSetupRequired):
        prepare_matching_application_drafts(
            profile=profile("alice"),preferences=prefs("bob"),
            candidates=[candidate()],workspace_repository=repository,
        )
    with pytest.raises(AutoDraftSetupRequired):
        prepare_matching_application_drafts(
            profile=profile(),preferences=SearchPreferences(profile_id=profile().profile_id),
            candidates=[candidate()],workspace_repository=repository,
        )
    with pytest.raises(AutoDraftSetupRequired):
        prepare_matching_application_drafts(
            profile=profile(),preferences=prefs(auto_drafts_enabled=False,mode="general"),
            candidates=[candidate()],workspace_repository=repository,
        )
    assert not repository.list("alice")


def test_previous_employer_attempt_and_bad_url_are_excluded():
    attempted=[]
    result=prepare_matching_application_drafts(
        profile=profile(),preferences=prefs(),
        candidates=[candidate(),candidate("Data Analyst",app_url="http://unsafe.invalid/apply")],
        workspace_repository=MemoryWorkspaceRepository(),
        previous_attempt=lambda item: attempted.append(item.canonical_key) or True,
    )
    assert result.to_dict()["created_count"]==0
    assert result.skipped_previous_attempt==1
    assert len(attempted)==1
    for invalid in (
        "http://careers.example.fi/apply", "https://user:pass@careers.example.fi/x",
        "javascript:alert(1)", "https://localhost/job", "https://x.invalid:wrong/job",
        "https://x.invalid:8080/job", "",
    ):
        assert _usable_application_url(invalid) is False


def test_max_five_local_drafts_a_day_and_owner_idempotence():
    jobs=[candidate("Junior Data Analyst "+str(x)) for x in range(12)]
    repository=MemoryWorkspaceRepository()
    a=prepare_matching_application_drafts(
        profile=profile(),preferences=prefs(roles=["Data Analyst"],keywords=["Python"]),
        candidates=jobs,workspace_repository=repository,
    )
    assert a.to_dict()["created_count"]<=5
    b=prepare_matching_application_drafts(
        profile=profile(),preferences=prefs(roles=["Data Analyst"],keywords=["Python"]),
        candidates=jobs,workspace_repository=repository,
    )
    assert b.to_dict()["created_count"]==0
    assert b.remaining_today==0


def test_existing_api_bulk_endpoint_requires_revised_search_and_local_confirmation():
    service=SmartployService()
    service.register_source(SOURCE)
    api=TestClient(create_app(service))
    source=api.post("/api/v1/jobs/ingest",json={"observation":{
        "source_id":"manual-import","source_mode":"manual",
        "source_url":"https://careers.example.fi/jobs/analyst",
        "raw_text":"Junior data analyst Python SQL",
        "payload":{
            "company":"Example Oy","role_title":"Junior Data Analyst",
            "description":"Use SQL Python in analytics","location":"Helsinki",
            "language":"English","work_mode":"remote",
            "application_url":"https://careers.example.fi/jobs/analyst",
        },
    }})
    assert source.status_code==200,source.text
    path="/api/v1/application-workspaces/prepare-matches"
    assert api.post(path,json={
        "expected_preferences_revision":1,"confirm_private_local_drafting":True,
    }).status_code==409
    saved=api.put("/api/v1/search-preferences",json={
        "mode":"personalized","roles":["Data Analyst"],"locations":["Helsinki"],
        "languages":["english"],"work_modes":["remote"],"seniority":"entry",
        "auto_drafts_enabled":True,"expected_revision":0,
    })
    assert saved.status_code==200,saved.text
    assert saved.json()["auto_drafts_enabled"] is True
    assert saved.json()["auto_submit_enabled"] is False
    assert api.post(path,json={
        "expected_preferences_revision":1,"confirm_private_local_drafting":False,
    }).status_code==422
    assert api.post(path,json={
        "expected_preferences_revision":0,"confirm_private_local_drafting":True,
    }).status_code==422  # bounded positive model revision
    assert api.post(path,json={
        "expected_preferences_revision":2,"confirm_private_local_drafting":True,
    }).status_code==409
    assert api.post("/api/v1/profile/facts",json={
        "fact_type":"identity","value":"Synthetic Candidate","approved":True
    }).status_code==201
    fresh=api.post(path,json={
        "expected_preferences_revision":1,"confirm_private_local_drafting":True,
    })
    assert fresh.status_code==200,fresh.text
    assert fresh.json()["created_count"]==1
    assert fresh.json()["actual_employer_submissions"]==0
    assert fresh.json()["external_ai_forwarding_performed"] is False
    assert fresh.json()["created"][0]["company"]=="Example Oy"
    assert api.get("/api/v1/application-workspaces").json()["count"]==1
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"]==0
    again=api.post(path,json={
        "expected_preferences_revision":1,"confirm_private_local_drafting":True,
    })
    assert again.status_code==200
    assert again.json()["created_count"]==0
    assert api.get("/api/v1/application-workspaces").json()["count"]==1
    toggled=api.put("/api/v1/search-preferences",json={
        "mode":"general","expected_revision":1,"auto_drafts_enabled":False,
    })
    assert toggled.status_code==200
    assert toggled.json()["auto_drafts_enabled"] is False
    assert api.post(path,json={
        "expected_preferences_revision":2,"confirm_private_local_drafting":True,
    }).status_code==409


def test_search_preference_boolean_opt_in_cannot_be_coerced():
    for invalid in ("true",1,None,[],{}):
        with pytest.raises(Exception):
            revise_preferences(profile().profile_id,{
                "mode":"personalized", "roles":["Data Analyst"],
                "auto_drafts_enabled":invalid,
            },revision=0)
    with pytest.raises(Exception):
        revise_preferences(profile().profile_id,{
            "mode":"general","auto_drafts_enabled":True,
        },revision=0)

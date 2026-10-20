"""SP15j: discovery -> genuine owner-only local application drafts, not employer POSTs."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import connect

from smartploy.api import create_app
from smartploy.auto_stage_matches import stage_owner_matches
from smartploy.application_workspace_storage import MemoryWorkspaceRepository
from smartploy.cv_storage import StoredCV
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.search_preference_storage import PostgresSearchPreferenceRepository
from smartploy.search_preferences import SearchPreferenceError, revise_preferences
from smartploy.storage import PostgresJobRepository


SOURCE=SourcePolicy("manual-import","Synthetic manual","manual",("manual",))


def fixture_job(title="Junior Data Analyst", *, location="Helsinki", application_url=""):
    slug=title.casefold().replace(" ","-")
    url=application_url or "https://jobs.example.invalid/finland/"+slug
    record=normalize_observation(
        SourceObservation(
            source_id="manual-import",source_mode="manual",source_url=url,
            raw_text="Synthetic Finnish IT opportunity",
            payload={
                "company":"Synthetic IT Oy","role_title":title,
                "description":"Python SQL and QA analytics",
                "location":location,"language":"English",
                "work_mode":"remote","application_url":url,
            },
            observed_at="2026-10-20T10:00:00+00:00",
        ),SOURCE,
    )
    assert record.candidate
    return record.candidate


def fixture_pref(pid="profile-a",**changes):
    values={
        "mode":"personalized", "roles":["Data Analyst"],
        "locations":["Helsinki"], "languages":["english"],
        "work_modes":["remote"], "skills":["Python"], "seniority":"entry",
        "auto_stage_drafts":True,
    }
    values.update(changes)
    return revise_preferences(pid,values,revision=0)


def fixture_profile(pid="profile-a"):
    return CandidateProfile(profile_id=pid,facts=(
        ProfileFact("identity","Applicant Synthetic","user-entered",approved=True).normalized(),
        ProfileFact("skill","Python SQL","user-entered",approved=True).normalized(),
    ))


def test_opt_in_creates_real_existing_application_workspaces_without_employer_action():
    profile=fixture_profile()
    items=[fixture_job(),fixture_job("Senior Data Analyst")]
    storage=MemoryWorkspaceRepository()
    kwargs=dict(preferences=fixture_pref(),candidates=items,profile=profile,
                cv=None,workspaces=storage)
    report=stage_owner_matches(**kwargs)
    assert report["created"]==1,report
    assert report["no_employer_actions"] is True
    assert report["submission_authorized"] is False
    assert report["external_ai_requests"]==0
    saved=storage.list(profile.profile_id)
    assert len(saved)==1
    assert saved[0].status=="draft"
    assert saved[0].role_title=="Junior Data Analyst"
    assert "Applicant Synthetic" in saved[0].cv_text
    assert "[Explain why you are interested" in saved[0].cover_letter_text
    assert saved[0].to_dict()["authority"]["may_submit_to_employer"] is False
    replay=stage_owner_matches(**kwargs)
    assert replay["created"]==0 and replay["existing"]==1
    assert len(storage.list(profile.profile_id))==1


def test_opt_out_general_mode_and_other_account_must_not_stage():
    repo=MemoryWorkspaceRepository()
    job=fixture_job()
    for pref in [
        fixture_pref(auto_stage_drafts=False),
        fixture_pref(mode="general",auto_stage_drafts=False),
        fixture_pref(pid="other-profile"),
    ]:
        result=stage_owner_matches(
            preferences=pref,candidates=[job],profile=fixture_profile(),
            cv=None,workspaces=repo,
        )
        assert result["status"]=="not_opted_in"
        assert result["created"]==0
    assert repo.list("profile-a")==[]


def test_claimed_jobs_and_weak_or_conflicting_fit_stay_out_of_drafts():
    job=fixture_job()
    repo=MemoryWorkspaceRepository()
    report=stage_owner_matches(
        preferences=fixture_pref(),candidates=[job],
        profile=fixture_profile(),cv=None,workspaces=repo,
        claimed_keys=frozenset({job.canonical_key}),
    )
    assert report["created"]==0
    assert report["skipped"]["prior_employer_attempt"]==1
    assert repo.list("profile-a")==[]
    senior=stage_owner_matches(
        preferences=fixture_pref(),
        candidates=[fixture_job("Senior Data Analyst")],
        profile=fixture_profile(),cv=None,workspaces=repo,
    )
    assert senior["created"]==0
    assert repo.list("profile-a")==[]


def test_missing_approved_evidence_and_invalid_application_link_skip():
    repo=MemoryWorkspaceRepository()
    blank=CandidateProfile(profile_id="profile-a",facts=())
    skipped=stage_owner_matches(
        preferences=fixture_pref(),candidates=[fixture_job()],
        profile=blank,cv=None,workspaces=repo,
    )
    assert skipped["created"]==0
    assert skipped["skipped"]["missing_approved_cv_evidence"]==1
    unsafe=stage_owner_matches(
        preferences=fixture_pref(),
        candidates=[fixture_job(application_url="http://jobs.example.invalid/apply")],
        profile=fixture_profile(),cv=None,workspaces=repo,
    )
    assert unsafe["created"]==0
    assert unsafe["skipped"]["no_verified_application_link"]==1


def test_uploaded_real_cv_is_reused_verbatim_not_invented():
    cv=StoredCV(profile_id="profile-a",filename="real.pdf",media_type="application/pdf",
                content=b"file-content-synthetic",text="Approved synthetic CV content\nExperience: QA",
                updated_at="2026-10-20T10:00:00Z")
    repo=MemoryWorkspaceRepository()
    outcome=stage_owner_matches(
        preferences=fixture_pref(),candidates=[fixture_job()],
        profile=fixture_profile(),cv=cv,workspaces=repo,
    )
    assert outcome["created"]==1
    saved=repo.list("profile-a")[0]
    assert saved.cv_text==cv.text
    assert saved.source_cv_sha256==cv.digest


def test_auto_stage_setting_requires_boolean_and_no_general_mode():
    for invalid in ["true","false",1,None,[],{}]:
        with pytest.raises(SearchPreferenceError):
            fixture_pref(auto_stage_drafts=invalid)
    with pytest.raises(SearchPreferenceError,match="personalized"):
        fixture_pref(mode="general",auto_stage_drafts=True)


def test_signed_out_browser_never_runs_private_auto_stage(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE","disabled")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT","test")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL",raising=False)
    client=TestClient(create_app())
    result=client.post("/api/v1/job-autopilot/stage",json={})
    assert result.status_code==403


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"),reason="PostgreSQL required")
def test_owner_opt_in_is_durable_and_only_active_user_profiles_are_listed():
    dsn=os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    issuer="https://sso.synthetic.invalid"
    subj="auto-stage-"+uuid4().hex
    identities=PostgresIdentityRepository(dsn)
    binding=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer=issuer,subject=subj,email="synthetic@example.invalid",auth_source="oidc"
    ))
    try:
        prefs=PostgresSearchPreferenceRepository(dsn)
        saved=prefs.save(binding.profile_id,{
            "mode":"personalized","roles":["Data Analyst"],"auto_stage_drafts":True,
        },expected_revision=0)
        assert saved.auto_stage_drafts is True
        listed=prefs.list_auto_stage_profiles(limit=100)
        assert binding.profile_id in {p.profile_id for p in listed}
        with connect(dsn) as conn:
            conn.execute(
                "UPDATE smartploy_users SET status='disabled' WHERE user_id=%s",
                (binding.user_id,),
            )
        assert binding.profile_id not in {
            p.profile_id for p in prefs.list_auto_stage_profiles(limit=100)
        }
        with connect(dsn) as conn:
            conn.execute(
                "UPDATE smartploy_users SET status='active' WHERE user_id=%s",
                (binding.user_id,),
            )
        disabled=prefs.save(binding.profile_id,{
            "mode":"personalized","roles":["Data Analyst"],"auto_stage_drafts":False,
        },expected_revision=saved.revision)
        assert disabled.auto_stage_drafts is False
        assert binding.profile_id not in {
            p.profile_id for p in prefs.list_auto_stage_profiles(limit=100)
        }
    finally:
        with connect(dsn) as conn:
            conn.execute("DELETE FROM smartploy_search_preferences WHERE profile_id=%s",(binding.profile_id,))
            conn.execute("DELETE FROM smartploy_user_identities WHERE user_id=%s",(binding.user_id,))
            conn.execute("DELETE FROM smartploy_user_profiles WHERE user_id=%s",(binding.user_id,))
            conn.execute("DELETE FROM smartploy_users WHERE user_id=%s",(binding.user_id,))

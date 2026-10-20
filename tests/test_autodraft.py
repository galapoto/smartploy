"""Actual SmartPloy source -> personalized IT match -> private CV/letter draft.

No AI, browser, employer API or application final click in these tests.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from smartploy.autodraft import (
    AutoDraftConflict,AutoDraftError,AutoDraftSettings,
    MemoryAutoDraftRepository,draft_matching_jobs,
)
from smartploy.application_workspace_storage import MemoryWorkspaceRepository
from smartploy.domain import SourceObservation,SourcePolicy,normalize_observation
from smartploy.identity import UserProfileBinding
from smartploy.profile import CandidateProfile,ProfileFact
from smartploy.search_preferences import revise_preferences


OWNER=UserProfileBinding(
    user_id="usr-auto-fixture-a",profile_id="profile-auto-fixture-a",
    email="shared@example.invalid",
)
OTHER=UserProfileBinding(
    user_id="usr-auto-fixture-b",profile_id="profile-auto-fixture-b",
    email="shared@example.invalid",
)


def job(title:str, *, current:bool=True, url:str="", language:str="English"):
    slug=title.lower().replace(" ","-")
    location="Helsinki"
    result=normalize_observation(
        SourceObservation(
            source_id="manual-import",source_mode="manual",
            source_url=url or "https://jobs.example.fi/"+slug,
            raw_text=title+" Helsinki remote Python SQL analytics",
            observed_at="2026-10-20T12:00:00+00:00",
            payload={
                "company":"Synthetic IT Employer",
                "role_title":title,
                "location":location,"language":language,
                "work_mode":"remote",
                "description":"Data quality, Python SQL and Power BI analytics",
                "application_url":url or "https://jobs.example.fi/"+slug,
            },
        ),
        SourcePolicy("manual-import","Manual","manual",("manual",)),
    )
    assert result.candidate
    return replace(result.candidate,source_current=current)


def prefs(profile_id=OWNER.profile_id,roles=None,mode="personalized"):
    return revise_preferences(profile_id,{
        "mode":mode,"roles":roles if roles is not None else ["Data Analyst"],
        "locations":["Helsinki"],"languages":["english"],
        "work_modes":["remote"],"skills":["SQL"],"seniority":"entry",
    },revision=0)


def profile(binding=OWNER,approved=True):
    return CandidateProfile(
        profile_id=binding.profile_id,
        facts=(
            ProfileFact("identity","Test Applicant","user",approved=approved),
            ProfileFact("skill","SQL","user",approved=approved),
        ),
    )


def run(binding=OWNER,*,settings=None,preference=None,candidates=None,
        candidate_profile=None,workspace_repo=None,still_enabled=None):
    return draft_matching_jobs(
        binding,settings or AutoDraftSettings(binding.user_id,binding.profile_id,True),
        preference or prefs(binding.profile_id),
        candidates if candidates is not None else [
            job("Junior Data Analyst"),job("Senior Data Analyst"),job("Nurse"),
        ],
        candidate_profile if candidate_profile is not None else profile(binding),
        None,workspace_repo if workspace_repo is not None else MemoryWorkspaceRepository(),
        still_enabled=still_enabled,
    )


def test_default_disabled_and_one_account_revision_controls():
    repo=MemoryAutoDraftRepository()
    assert repo.get(OWNER.user_id,OWNER.profile_id).enabled is False
    assert repo.list_enabled()==[]
    enabled=repo.save(OWNER,expected_revision=0,enabled=True,
                      minimum_score=75,max_per_cycle=5)
    assert enabled.enabled and enabled.revision==1
    assert repo.list_enabled()==[enabled]
    with pytest.raises(AutoDraftConflict):
        repo.save(OWNER,expected_revision=0,enabled=False,
                  minimum_score=75,max_per_cycle=5)
    assert repo.get(OTHER.user_id,OTHER.profile_id).enabled is False
    disabled=repo.save(OWNER,expected_revision=1,enabled=False,
                       minimum_score=75,max_per_cycle=5)
    assert disabled.revision==2 and repo.list_enabled()==[]
    assert disabled.public()["automatic_employer_submission_authorized"] is False
    assert disabled.public()["external_ai_processing_authorized"] is False


def test_real_personalized_matches_generate_once_without_employer_actions():
    repo=MemoryWorkspaceRepository()
    first=run(workspace_repo=repo)
    assert first["status"]=="ready"
    assert first["created_count"]==1
    assert first["employer_applications_submitted"]==0
    assert first["external_actions_performed"] is False
    assert first["external_ai_calls"]==0
    assert first["created"][0]["preference_score"]>=75
    workspace=repo.list(OWNER.profile_id)[0]
    assert workspace.status=="draft"
    assert "Test Applicant" in workspace.cv_text
    assert "SQL" in workspace.cv_text
    assert "[Explain why you are interested" in workspace.cover_letter_text
    assert workspace.to_dict()["authority"]["may_submit_to_employer"] is False
    again=run(workspace_repo=repo)
    assert again["created_count"]==0
    assert again["existing_count"]==1
    assert len(repo.list(OWNER.profile_id))==1


def test_general_search_missing_setup_or_unapproved_cv_cannot_autodraft():
    no_setup=prefs(roles=[],mode="general")
    assert run(preference=no_setup)["status"]=="personalized_search_required"
    assert run(candidate_profile=profile(approved=False))["status"]=="profile_evidence_required"
    with pytest.raises(AutoDraftError):
        run(settings=AutoDraftSettings(OWNER.user_id,OWNER.profile_id,False))
    with pytest.raises(AutoDraftError):
        run(binding=OTHER,settings=AutoDraftSettings(OWNER.user_id,OWNER.profile_id,True))
    with pytest.raises(AutoDraftError):
        run(candidate_profile=profile(OTHER))


def test_source_closure_seniority_and_unsafe_job_urls_never_generate_drafts():
    for jobs in (
        [job("Junior Data Analyst",current=False)],
        [job("Senior Data Analyst")],
        [job("Junior Data Analyst",url="http://unsafe.invalid/job")],
        [job("Junior Data Analyst",url="https://localhost/job")],
    ):
        result=run(candidates=jobs)
        assert result["created_count"]==0
        assert result["employer_applications_submitted"]==0


def test_pause_and_revision_change_prevent_more_drafts():
    calls=0
    def revoked():
        nonlocal calls
        calls+=1
        return False
    result=run(candidates=[job("Junior Data Analyst")],still_enabled=revoked)
    assert calls==1
    assert result["status"]=="disabled_during_cycle"
    assert result["created_count"]==0


def test_two_user_identical_email_keeps_separate_private_workspaces():
    shared=MemoryWorkspaceRepository()
    a=run(workspace_repo=shared)
    b=run(binding=OTHER,preference=prefs(OTHER.profile_id),
          candidate_profile=profile(OTHER),workspace_repo=shared)
    assert a["created_count"]==1 and b["created_count"]==1
    assert len(shared.list(OWNER.profile_id))==1
    assert len(shared.list(OTHER.profile_id))==1
    assert shared.list(OWNER.profile_id)[0].workspace_id != shared.list(OTHER.profile_id)[0].workspace_id


@pytest.mark.parametrize(("score","limit"),[
    (59,5),(101,5),(75,0),(75,11),
])
def test_unsafe_limits_fail_closed(score,limit):
    with pytest.raises(AutoDraftError):
        run(settings=AutoDraftSettings(
            OWNER.user_id,OWNER.profile_id,True,score,limit
        ))

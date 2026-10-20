"""SP15j: automatic per-account IT discovery and LOCAL application drafts.

Tests use original SmartPloy matching, evidence, CV and workspace products.
No network, ObumAI or employer final-submit engine is mocked in or invoked.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from smartploy.auto_draft_shortlist import prepare_profile_shortlist
from smartploy.application_workspace_storage import MemoryWorkspaceRepository, PostgresWorkspaceRepository
from smartploy.cv_storage import MemoryCVRepository, PostgresCVRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.profile import ProfileFact
from smartploy.profile_storage import MemoryProfileRepository, PostgresProfileRepository
from smartploy.search_preferences import SearchPreferenceError
from smartploy.search_preference_storage import (
    MemorySearchPreferenceRepository, PostgresSearchPreferenceRepository,
)
from smartploy.storage import MemoryJobRepository, PostgresJobRepository


def candidate(title: str, *, url: str = "", requirements: list[str] | None = None):
    slug = title.casefold().replace(" ", "-")
    href = url or "https://careers.example.fi/jobs/" + slug
    observed = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url=href, raw_text=title + " vacancy",
            observed_at="2026-10-20T11:00:00+00:00",
            payload={
                "company":"Synthetic Employer", "role_title":title,
                "description":"Python data analysis and SQL business reporting",
                "location":"Helsinki","application_url":href,
                "requirements":requirements or [],
            },
        ),
        SourcePolicy("manual-import","Manual","manual",("manual",)),
    )
    assert observed.candidate
    return observed.candidate


def fixture():
    owner = "synthetic-it-user"
    prefs = MemorySearchPreferenceRepository()
    repo = MemoryJobRepository()
    profile = MemoryProfileRepository(profile_id=owner)
    for skill in ("Python", "SQL", "data analysis"):
        profile.upsert_fact(ProfileFact(
            "skill", skill, "user-entered", approved=True
        ))
    cv = MemoryCVRepository()
    spaces = MemoryWorkspaceRepository()
    pref_payload = {
        "mode":"personalized", "roles":["Data Analyst"], "locations":[],
        "languages":[], "work_modes":[], "skills":[], "keywords":[],
        "seniority":"any", "auto_draft_enabled":True,
    }
    prefs.save(owner,pref_payload,expected_revision=0)
    for j in (candidate("Junior Data Analyst"),candidate("Senior Marketing Manager")):
        repo.upsert(j)
    return owner,prefs,repo,profile,cv,spaces,pref_payload


def run_local(f):
    pid,prefs,jobs,profile,cv,spaces,_=f
    return prepare_profile_shortlist(
        pid,preferences_repository=prefs,job_repository=jobs,
        profile_repository=profile,cv_repository=cv,workspace_repository=spaces,
    )


def test_explicit_approved_it_target_automatically_builds_only_the_matched_private_draft():
    fx = fixture()
    outcome = run_local(fx)
    assert outcome.status == "prepared"
    assert outcome.created == 1
    assert outcome.checked == 1
    assert outcome.public_counts()["employer_actions_performed"] is False
    assert outcome.public_counts()["provider_calls"] == 0
    assert all("example.fi" not in str(value) for value in outcome.public_counts().values())
    spaces = fx[5].list(fx[0])
    assert len(spaces) == 1
    assert spaces[0].role_title == "Junior Data Analyst"
    assert spaces[0].status == "draft"
    assert spaces[0].to_dict()["authority"]["may_submit_to_employer"] is False
    again = run_local(fx)
    assert again.created == 0 and again.already_prepared == 1
    assert len(fx[5].list(fx[0])) == 1


def test_general_mode_unapproved_evidence_and_optout_never_create():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,settings=fx
    prefs.save(pid,{**settings,"auto_draft_enabled":False},expected_revision=1)
    assert run_local(fx).status=="disabled"
    with pytest.raises(SearchPreferenceError):
        prefs.save(pid,{**settings,"mode":"general"},expected_revision=2)
    with pytest.raises(SearchPreferenceError):
        prefs.save(pid,{**settings,"auto_draft_enabled":1},expected_revision=2)
    prefs.save(pid,{**settings,"mode":"general","auto_draft_enabled":False},expected_revision=2)
    assert run_local(fx).status=="disabled"
    prefs.save(pid,settings,expected_revision=3)
    empty=MemoryProfileRepository(profile_id=pid)
    result=prepare_profile_shortlist(pid,preferences_repository=prefs,
        job_repository=jobs,profile_repository=empty,
        cv_repository=cv,workspace_repository=spaces)
    assert result.status=="needs_approved_profile"
    assert spaces.list(pid)==[]


def test_revoked_optin_between_scoring_and_creation_stops_all_writes():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,settings=fx
    original=prefs.auto_draft_guard
    from contextlib import contextmanager
    @contextmanager
    def revoke_before_guard(profile_id,revision):
        prefs.save(pid,{**settings,"auto_draft_enabled":False},expected_revision=revision)
        with original(profile_id,revision) as allowed:
            yield allowed
    prefs.auto_draft_guard=revoke_before_guard
    result=run_local(fx)
    assert result.stopped_on_opt_out is True
    assert result.created==0
    assert spaces.list(pid)==[]


def test_expired_posting_and_https_safety_never_create_offsite_application():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,_=fx
    good=next(j for j in jobs.values() if j.job.role_title=="Junior Data Analyst")
    jobs.mark_closed(good.canonical_key)
    outcome=run_local(fx)
    assert outcome.created==0
    for url in (
        "http://careers.example.fi/job/100",
        "https://localhost/jobs/123",
        "https://person:secret@careers.example.fi/jobs/1",
        "https://careers.example.fi:444/jobs/123",
    ):
        j=candidate("Junior Data Analyst",url=url)
        assert prepare_profile_shortlist(
            pid,preferences_repository=prefs,
            job_repository=MemoryJobRepositoryWith(j),
            profile_repository=profile,cv_repository=cv,
            workspace_repository=spaces,
        ).created==0


class MemoryJobRepositoryWith(MemoryJobRepository):
    def __init__(self, job):
        super().__init__()
        self.upsert(job)


def test_incomplete_approved_skills_are_not_upgraded_to_high_fit():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,_=fx
    weak=MemoryProfileRepository(profile_id=pid)
    weak.upsert_fact(ProfileFact("skill","Python","user-entered",approved=True))
    result=prepare_profile_shortlist(
        pid,preferences_repository=prefs,job_repository=jobs,
        profile_repository=weak,cv_repository=cv,workspace_repository=spaces,
    )
    assert result.status=="prepared"
    assert result.created==0
    assert spaces.list(pid)==[]


def test_mismatched_profile_id_does_not_cross_account_or_copy_cv():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,_=fx
    other = MemoryProfileRepository(profile_id="other-user")
    other.upsert_fact(ProfileFact("skill","Python","user-entered",approved=True))
    result=prepare_profile_shortlist(
        pid,preferences_repository=prefs,job_repository=jobs,
        profile_repository=other,cv_repository=cv,workspace_repository=spaces,
    )
    assert result.status=="owner_mismatch"
    assert spaces.list(pid)==[]


DSN=os.getenv("SMARTPLOY_TEST_DATABASE_URL","")


@pytest.mark.skipif(not DSN,reason="requires real PostgreSQL")
def test_actual_postgres_only_lists_active_opted_in_accounts_and_persists_one_draft():
    from psycopg import connect
    PostgresJobRepository(DSN).migrate()
    unique=uuid4().hex
    identities=PostgresIdentityRepository(DSN)
    owner=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://synthetic.example.invalid",
        subject="auto-draft-"+unique,email="auto@example.invalid",auth_source="oidc",
    ))
    other=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://synthetic.example.invalid",
        subject="not-opted-"+unique,email="auto@example.invalid",auth_source="oidc",
    ))
    prefs=PostgresSearchPreferenceRepository(DSN)
    jobs=PostgresJobRepository(DSN)
    profiles=PostgresProfileRepository(DSN,profile_id=owner.profile_id)
    spaces=PostgresWorkspaceRepository(DSN)
    cv=PostgresCVRepository(DSN)
    job=candidate("Junior Data Analyst",url="https://careers.example.fi/jobs/"+unique)
    try:
        for skill in ("Python", "SQL", "data analysis"):
            profiles.upsert_fact(ProfileFact("skill",skill,"user-entered",approved=True))
        jobs.upsert(job)
        config={"mode":"personalized","roles":["Data Analyst"],
                "auto_draft_enabled":True}
        saved=prefs.save(owner.profile_id,config,expected_revision=0)
        prefs.save(other.profile_id,{**config,"auto_draft_enabled":False},expected_revision=0)
        listed=prefs.list_auto_draft_profiles(limit=500)
        assert owner.profile_id in listed
        assert other.profile_id not in listed
        first=prepare_profile_shortlist(
            owner.profile_id,preferences_repository=prefs,job_repository=jobs,
            profile_repository=profiles,cv_repository=cv,workspace_repository=spaces,
            candidates=[job],
        )
        assert first.created>=1 and first.public_counts()["provider_calls"]==0
        assert spaces.get(owner.profile_id,spaces.list(owner.profile_id)[0].workspace_id)
        assert spaces.list(other.profile_id)==[]
        assert prepare_profile_shortlist(
            owner.profile_id,preferences_repository=prefs,job_repository=jobs,
            profile_repository=profiles,cv_repository=cv,workspace_repository=spaces,
            candidates=[job],
        ).created==0
        with prefs.auto_draft_guard(owner.profile_id,saved.revision) as allowed:
            assert allowed
        prefs.save(owner.profile_id,{**config,"auto_draft_enabled":False},
                   expected_revision=saved.revision)
        with prefs.auto_draft_guard(owner.profile_id,saved.revision) as allowed:
            assert not allowed
        assert owner.profile_id not in prefs.list_auto_draft_profiles(limit=500)
        assert prepare_profile_shortlist(
            owner.profile_id,preferences_repository=prefs,job_repository=jobs,
            profile_repository=profiles,cv_repository=cv,workspace_repository=spaces,
            candidates=[job],
        ).created==0
    finally:
        with connect(DSN) as conn:
            with conn.cursor() as cur:
                for pid in (owner.profile_id,other.profile_id):
                    cur.execute("DELETE FROM smartploy_application_workspaces WHERE profile_id=%s",(pid,))
                    cur.execute("DELETE FROM smartploy_search_preferences WHERE profile_id=%s",(pid,))
                    cur.execute("DELETE FROM smartploy_profile_facts WHERE profile_id=%s",(pid,))

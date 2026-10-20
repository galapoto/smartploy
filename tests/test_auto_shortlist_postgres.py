"""Real PostgreSQL + private OIDC acceptance for account opt-in auto-IT drafting.

All applicant identities/jobs are fictional. No LLM/employer external calls.
"""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import os

import pytest
from fastapi.testclient import TestClient
from psycopg import connect

from smartploy.api import create_app
from smartploy.account_erasure import PostgresAccountErasureRepository, inspect_quarantined_account
from smartploy.auto_shortlist import (
    AutoShortlistDenied, PostgresAutoShortlistRepository, run_local_shortlist,
)
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.profile import ProfileFact
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.search_preference_storage import PostgresSearchPreferenceRepository
from smartploy.storage import PostgresJobRepository
from smartploy.application_workspace_storage import PostgresWorkspaceRepository


DSN=os.getenv("SMARTPLOY_TEST_DATABASE_URL","")
pytestmark=pytest.mark.skipif(not DSN,reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture
def world(monkeypatch):
    jobs=PostgresJobRepository(DSN)
    jobs.migrate()
    nonce=uuid4().hex
    identities=PostgresIdentityRepository(DSN)
    a=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid",subject="shortlist-a-"+nonce,
        email="shared@example.invalid",auth_source="oidc",
    ))
    b=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid",subject="shortlist-b-"+nonce,
        email="shared@example.invalid",auth_source="oidc",
    ))
    policy=SourcePolicy("manual-import","Manual","manual",("manual",))
    candidates=[]
    for index,(title,location) in enumerate((
        ("Junior Data Analyst","Helsinki"),
        ("Senior Data Analyst","Helsinki"),
        ("Junior Software Tester","Turku"),
    )):
        url=f"https://jobs.example.invalid/{nonce}/{index}"
        observed=normalize_observation(
            SourceObservation(
                source_id="manual-import",source_mode="manual",source_url=url,
                raw_text=title+" SQL career posting",
                observed_at="2026-10-20T10:00:00+00:00",
                payload={"company":"Synthetic Company Oy","role_title":title,
                    "location":location,"language":"English","work_mode":"hybrid",
                    "description":"Python SQL analytics and testing",
                    "application_url":url},
            ),policy,
        )
        assert observed.candidate
        candidates.append(jobs.upsert(observed.candidate))
    preferences=PostgresSearchPreferenceRepository(DSN)
    preferences.save(a.profile_id,{
        "mode":"personalized","roles":["Data Analyst"],
        "locations":["Helsinki"],"languages":["english"],
        "work_modes":["hybrid"],"seniority":"entry","skills":["Python"],
    },expected_revision=0)
    PostgresProfileRepository(DSN,profile_id=a.profile_id).upsert_fact(
        ProfileFact("skill","Python","user-reviewed",approved=True)
    )
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL",DSN)
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT","production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE","oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED","false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN","https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS","smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER","https://sso.example.invalid")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID","fixture")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI","https://smartploy.obumai.com/auth/callback")
    monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI","https://smartploy.obumai.com/auth/logged-out")
    sessions=MemorySessionRepository()
    token={}
    for binding,subject in ((a,"a"),(b,"b")):
        token[subject]=sessions.create(
            user_id=binding.user_id,
            principal=AuthenticatedPrincipal(
                issuer="https://sso.example.invalid",
                subject="shortlist-"+subject+"-"+nonce,
                email="shared@example.invalid",auth_source="oidc",
            ),provider_session_id="synthetic-"+subject,ttl_seconds=3600,
        ).token
    api=TestClient(create_app(
        identity_repository=identities,session_repository=sessions,oidc_client=object(),
    ),base_url="https://smartploy.obumai.com")
    api.cookies.set(SESSION_COOKIE_NAME,token["a"])
    headers={
        "Origin":"https://smartploy.obumai.com",
        "Sec-Fetch-Site":"same-origin",
        "X-Smartploy-Expected-User-Id":a.user_id,
    }
    yield a,b,candidates,api,headers,token
    with connect(DSN) as conn:
        conn.execute(
            """DELETE FROM smartploy_obumai_erasure_obligations
               WHERE request_id IN (
                 SELECT request_id FROM smartploy_account_erasure_requests
                 WHERE user_id IN (%s,%s))""",(a.user_id,b.user_id)
        )
        conn.execute(
            "DELETE FROM smartploy_account_erasure_requests WHERE user_id IN (%s,%s)",
            (a.user_id,b.user_id),
        )
        for table in (
            "smartploy_auto_shortlist_settings","smartploy_search_preferences",
            "smartploy_application_workspaces","smartploy_profile_facts",
        ):
            conn.execute(f"DELETE FROM {table} WHERE profile_id IN (%s,%s)",(a.profile_id,b.profile_id))
        for item in candidates:
            conn.execute("DELETE FROM smartploy_jobs WHERE canonical_key=%s",(item.canonical_key,))
        for table in ("smartploy_user_identities","smartploy_user_profiles","smartploy_users"):
            conn.execute(f"DELETE FROM {table} WHERE user_id IN (%s,%s)",(a.user_id,b.user_id))


def test_verified_owner_enables_local_automatic_it_drafts_and_reloads(world):
    a,b,jobs,api,headers,tokens=world
    assert api.get("/api/v1/auto-shortlist").json()["enabled"] is False
    payload={
        "enabled":True,"minimum_score":75,"max_per_cycle":3,
        "expected_revision":0,"acknowledge_local_drafts_only":True
    }
    assert api.put("/api/v1/auto-shortlist",json=payload).status_code==403
    assert api.put("/api/v1/auto-shortlist",headers=headers,json={
        **payload,"acknowledge_local_drafts_only":False
    }).status_code==422
    result=api.put("/api/v1/auto-shortlist",headers=headers,json=payload)
    assert result.status_code==200,result.text
    assert result.json()["revision"]==1
    assert result.json()["automatic_employer_submission"] is False
    assert result.json()["external_ai_processing"] is False
    response=api.post("/api/v1/auto-shortlist/run-now",headers=headers)
    assert response.status_code==200,response.text
    assert response.json()["created"]==1
    assert response.json()["employer_submissions"]==0
    saved=PostgresWorkspaceRepository(DSN).list(a.profile_id)
    assert len(saved)==1
    assert saved[0].role_title=="Junior Data Analyst"
    assert saved[0].status=="draft"
    assert "[Explain why" in saved[0].cover_letter_text
    assert "Python" in saved[0].cv_text
    assert api.post("/api/v1/auto-shortlist/run-now",headers=headers).json()["created"]==0
    assert PostgresAutoShortlistRepository(DSN).get(a.profile_id).last_created==0
    assert len(PostgresWorkspaceRepository(DSN).list(a.profile_id))==1
    # Separate account with identical email cannot see, grant or use A's opt-in.
    api.cookies.set(SESSION_COOKIE_NAME,tokens["b"])
    assert api.get("/api/v1/auto-shortlist").json()["enabled"] is False
    assert api.post("/api/v1/auto-shortlist/run-now",headers=headers).status_code==409
    assert PostgresWorkspaceRepository(DSN).list(b.profile_id)==[]
    api.cookies.set(SESSION_COOKIE_NAME,tokens["a"])


def test_revocation_and_quarantine_stop_unattended_local_work(world):
    a,b,jobs,api,headers,tokens=world
    ledger=PostgresAutoShortlistRepository(DSN)
    initial=ledger.save(a.profile_id,enabled=True,minimum_score=75,
                        max_per_cycle=1,expected_revision=0)
    assert initial.revision==1
    assert a.profile_id in ledger.enabled_profiles()
    disabled=ledger.save(a.profile_id,enabled=False,minimum_score=75,
                         max_per_cycle=1,expected_revision=1)
    assert not disabled.enabled
    with pytest.raises(AutoShortlistDenied):
        run_local_shortlist(DSN,a.profile_id)
    assert a.profile_id not in ledger.enabled_profiles()
    enabled=ledger.save(a.profile_id,enabled=True,minimum_score=75,
                        max_per_cycle=1,expected_revision=2)
    assert enabled.enabled
    quarantine=PostgresAccountErasureRepository(DSN).quarantine(a.user_id,a.profile_id)
    assert quarantine.processing_disabled if hasattr(quarantine,"processing_disabled") else quarantine.status=="quarantined"
    assert not ledger.get(a.profile_id).enabled
    assert a.profile_id not in ledger.enabled_profiles()
    assert "smartploy_auto_shortlist_settings" not in inspect_quarantined_account(
        DSN,a.user_id,a.profile_id
    ).unknown_owner_tables
    with pytest.raises(AutoShortlistDenied):
        run_local_shortlist(DSN,a.profile_id)


def test_concurrent_worker_cycles_create_no_duplicate_drafts(world):
    a,b,jobs,api,headers,tokens=world
    ledger=PostgresAutoShortlistRepository(DSN)
    ledger.save(a.profile_id,enabled=True,minimum_score=75,
                max_per_cycle=3,expected_revision=0)
    def attempt(_):
        try:
            return run_local_shortlist(DSN,a.profile_id)["created"]
        except AutoShortlistDenied:
            return 0
    with ThreadPoolExecutor(max_workers=6) as executor:
        created=list(executor.map(attempt,range(6)))
    assert sum(created)==1
    assert len(PostgresWorkspaceRepository(DSN).list(a.profile_id))==1

"""Authenticated end-to-end IT job match -> draft. Synthetic; no employer calls."""
from __future__ import annotations

from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.domain import SourceObservation,SourcePolicy,normalize_observation
from smartploy.identity import AuthenticatedPrincipal,MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository,SESSION_COOKIE_NAME
from smartploy.profile import ProfileFact
from smartploy.service import SmartployService

ORIGIN="https://smartploy.obumai.com"
ISSUER="https://auth.example.invalid"


def scenario(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT","production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE","oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED","false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN",ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS","smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER",ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID","test-client")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI",ORIGIN+"/auth/callback")
    monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",ORIGIN+"/auth/logged-out")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL",raising=False)

    identities=MemoryIdentityRepository()
    sessions=MemorySessionRepository()
    service=SmartployService()
    app=create_app(
        service,identity_repository=identities,session_repository=sessions,oidc_client=object()
    )
    api=TestClient(app,base_url=ORIGIN)
    users=[]
    for subject in ("one","two"):
        principal=AuthenticatedPrincipal(
            issuer=ISSUER,subject="autodraft-"+subject,email="shared@example.invalid",
            auth_source="oidc",
        )
        binding=identities.resolve_or_create(principal)
        token=sessions.create(
            user_id=binding.user_id,principal=principal,
            provider_session_id="fixture-"+subject,ttl_seconds=3600,
        ).token
        users.append((binding,token))
    api.cookies.set(SESSION_COOKIE_NAME,users[0][1])
    job=normalize_observation(
        SourceObservation(
            source_id="manual-import",source_mode="manual",
            source_url="https://careers.example.invalid/it/data-analyst",
            observed_at="2026-10-20T13:00:00+00:00",
            raw_text="Junior Data Analyst SQL Python Helsinki",
            payload={
                "company":"Example IT Ltd","role_title":"Junior Data Analyst",
                "location":"Helsinki","work_mode":"remote",
                "description":"SQL and Python dashboards",
                "application_url":"https://careers.example.invalid/it/data-analyst",
            },
        ),
        SourcePolicy("manual-import","Manual","manual",("manual",)),
    ).candidate
    assert job
    service.repository.upsert(job)
    return api,app,users


def headers(user_id):
    return {
        "Origin":ORIGIN,"Sec-Fetch-Site":"same-origin",
        "X-Smartploy-Expected-User-Id":user_id,
    }


def test_owner_auth_preferences_optin_immediate_scan_and_same_email_isolation(monkeypatch):
    api,app,users=scenario(monkeypatch)
    owner=users[0][0]
    initial=api.get("/api/v1/autodraft")
    assert initial.status_code==200
    assert initial.json()["enabled"] is False
    assert initial.json()["automatic_employer_submission_authorized"] is False
    assert "no-store" in initial.headers["cache-control"]
    settings={
        "enabled":True,"minimum_score":75,"max_per_cycle":5,"expected_revision":0,
        "acknowledge_review_before_any_employer_submission":True,
    }
    denied=api.put("/api/v1/autodraft",json=settings,headers=headers(owner.user_id))
    assert denied.status_code==409  # no personalized user targets
    targets=api.put("/api/v1/search-preferences",headers=headers(owner.user_id),json={
        "mode":"personalized","roles":["Data Analyst"],
        "locations":["Helsinki"],"languages":[],
        "work_modes":[],"keywords":[],"skills":[],"seniority":"entry",
        "expected_revision":0,
    })
    assert targets.status_code==200,targets.text
    # Reuse verified owner-scoped profile facts, never upload unknown facts.
    owner_tenant=app.state.tenant_services[owner.profile_id]
    owner_tenant.profile_repository.upsert_fact(
        ProfileFact("skill","SQL","user-entered",approved=True)
    )
    saved=api.put("/api/v1/autodraft",json=settings,headers=headers(owner.user_id))
    assert saved.status_code==200,saved.text
    assert saved.json()["revision"]==1
    scanned=api.post("/api/v1/autodraft/run",headers=headers(owner.user_id))
    assert scanned.status_code==200,scanned.text
    assert scanned.json()["created_count"]==1
    assert scanned.json()["external_actions_performed"] is False
    assert scanned.json()["employer_applications_submitted"]==0
    assert scanned.json()["external_ai_calls"]==0
    again=api.post("/api/v1/autodraft/run",headers=headers(owner.user_id))
    assert again.status_code==200
    assert again.json()["created_count"]==0
    assert again.json()["existing_count"]==1
    workspaces=api.get("/api/v1/application-workspaces").json()["workspaces"]
    assert len(workspaces)==1
    assert workspaces[0]["status"]=="draft"
    assert workspaces[0]["authority"]["may_submit_to_employer"] is False

    # Different principal with IDENTICAL email cannot see owner A.
    api.cookies.set(SESSION_COOKIE_NAME,users[1][1])
    other=api.get("/api/v1/autodraft")
    assert other.status_code==200 and not other.json()["enabled"]
    assert api.get("/api/v1/application-workspaces").json()["workspaces"]==[]
    assert api.post("/api/v1/autodraft/run",headers=headers(users[1][0].user_id)).status_code==409
    assert api.put("/api/v1/autodraft",json=settings,headers=headers(owner.user_id)).status_code==409


def test_autodraft_mutation_requires_firstparty_origin_and_verified_current_owner(monkeypatch):
    api,app,users=scenario(monkeypatch)
    owner=users[0][0]
    cfg={
        "enabled":True,"minimum_score":75,"max_per_cycle":5,"expected_revision":0,
        "acknowledge_review_before_any_employer_submission":True,
    }
    for hs in (
        {},{"Origin":"https://other.invalid"},
        {"Origin":ORIGIN},{"Origin":"chrome-extension://fake"},
        {**headers(owner.user_id),"Sec-Fetch-Site":"cross-site"},
    ):
        assert api.put("/api/v1/autodraft",json=cfg,headers=hs).status_code==403
        assert api.post("/api/v1/autodraft/run",headers=hs).status_code==403
    assert api.put("/api/v1/autodraft",json={
        **cfg,"acknowledge_review_before_any_employer_submission":False,
    },headers=headers(owner.user_id)).status_code==422
    api.cookies.clear()
    assert api.get("/api/v1/autodraft").status_code==401
    assert api.put("/api/v1/autodraft",json=cfg,headers=headers(owner.user_id)).status_code==401

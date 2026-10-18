"""SP15b: new employer claim status is signed-in/read-only and fails closed.

All identities and employers in these tests are synthetic. No job applications.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


ORIGIN = "https://smartploy.obumai.com"
ISSUER = "https://auth.example.invalid"
PATH = "/api/v1/application-workspaces/kit-" + "a" * 30 + "/employer-attempt"


def client_for_owner(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out",
    )
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    principal = AuthenticatedPrincipal(
        issuer=ISSUER, subject="synthetic-claim-a",
        email="shared@example.invalid", auth_source="oidc",
    )
    binding = identities.resolve_or_create(principal)
    record = sessions.create(
        user_id=binding.user_id, principal=principal,
        provider_session_id="fixture", ttl_seconds=3600,
    )
    app = create_app(
        SmartployService(), identity_repository=identities,
        session_repository=sessions, oidc_client=object(),
    )
    client = TestClient(app, base_url=ORIGIN)
    client.cookies.set(SESSION_COOKIE_NAME, record.token)
    return client


def test_authenticated_read_fails_closed_when_durable_db_missing(monkeypatch):
    api = client_for_owner(monkeypatch)
    answer = api.get(PATH)
    assert answer.status_code == 503, answer.text
    assert "ledger" in answer.text.lower()
    assert "no-store" in answer.headers["cache-control"]


def test_cross_origin_and_extension_reads_cannot_access_status(monkeypatch):
    api = client_for_owner(monkeypatch)
    for headers in (
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "chrome-extension://synthetic-extension"},
        {"Origin": "https://evil.example.invalid"},
    ):
        answer = api.get(PATH, headers=headers)
        assert answer.status_code == 403, (headers, answer.text)
        assert "no-store" in answer.headers["cache-control"]


def test_anonymous_or_auth_disabled_client_cannot_inspect_claims(monkeypatch):
    api = client_for_owner(monkeypatch)
    api.cookies.clear()
    answer = api.get(PATH)
    assert answer.status_code == 401

    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "test")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "disabled")
    fixture = TestClient(create_app(SmartployService()), base_url=ORIGIN)
    denied = fixture.get(PATH)
    assert denied.status_code == 403


def test_status_has_no_writable_employer_attempt_endpoint(monkeypatch):
    api = client_for_owner(monkeypatch)
    attempt = api.post(PATH, json={
        "final_user_approval": True, "employer_submission_permitted": True,
    }, headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"})
    assert attempt.status_code == 405


def test_review_intent_api_never_allows_unauthenticated_or_nonorigin_creation(monkeypatch):
    api=client_for_owner(monkeypatch)
    url=PATH.replace("/employer-attempt","/submit-review-intent")
    body={
        "expected_revision":1,
        "expected_document_sha256":"a"*64,"expected_cv_pdf_sha256":"b"*64,
        "confirm_reviewed_application":True,"acknowledge_manual_only":True,
    }
    api.cookies.clear()
    assert api.post(url,json=body,headers={"Origin":ORIGIN}).status_code==401
    api=client_for_owner(monkeypatch)
    assert api.post(url,json=body).status_code==403
    assert api.post(url,json=body,headers={
        "Origin":"https://other.obumai.com","Sec-Fetch-Site":"same-site",
    }).status_code==403
    assert api.post(url,json=body,headers={
        "Origin":ORIGIN,"Sec-Fetch-Site":"same-origin",
    }).status_code==403  # no verified account precondition header
    verified_user = api.get("/api/v1/session").json()["user_id"]
    assert api.post(url,json={**body,"confirm_reviewed_application":False},headers={
        "Origin":ORIGIN,"Sec-Fetch-Site":"same-origin",
        "X-Smartploy-Expected-User-Id":verified_user,
    }).status_code==422


def test_review_intent_api_raises_503_when_postgres_is_not_configured(monkeypatch):
    api=client_for_owner(monkeypatch)
    url=PATH.replace("/employer-attempt","/submit-review-intent")
    assert api.get(url).status_code==503
    payload={
        "expected_revision":1,"expected_document_sha256":"a"*64,
        "expected_cv_pdf_sha256":"b"*64,
        "confirm_reviewed_application":True,"acknowledge_manual_only":True,
    }
    identity=api.get("/api/v1/session").json()
    headers={"Origin":ORIGIN,"Sec-Fetch-Site":"same-origin",
             "X-Smartploy-Expected-User-Id":identity["user_id"]}
    assert api.post(url,json=payload,headers=headers).status_code==503
    assert api.delete(url,headers=headers).status_code==503


def test_browser_verification_endpoint_is_not_extension_accessible(monkeypatch):
    api=client_for_owner(monkeypatch)
    url=PATH.replace("/employer-attempt","/verify-reviewed-packet")
    body={
        "expected_revision":1,"expected_document_sha256":"a"*64,
        "expected_cv_pdf_sha256":"b"*64,
        "expected_fields_sha256":"c"*64,
        "expected_application_url_sha256":"d"*64,
        "expected_cv_pdf_size":87522,
    }
    account=api.get("/api/v1/session").json()["user_id"]
    good={"Origin":ORIGIN,"Sec-Fetch-Site":"same-origin",
          "X-Smartploy-Expected-User-Id":account}
    assert api.post(url,json=body).status_code==403
    assert api.post(url,json=body,headers={
        **good,"Origin":"chrome-extension://synthetic"
    }).status_code==403
    assert api.post(url,json=body,headers={
        **good,"Sec-Fetch-Site":"cross-site"
    }).status_code==403
    assert api.post(url,json={**body,"expected_cv_pdf_sha256":"notsha"},
                    headers=good).status_code==422
    assert api.post(url,json=body,headers=good).status_code==503
    api.cookies.clear()
    assert api.post(url,json=body,headers=good).status_code==401



def test_private_final_action_readiness_never_issues_employer_submit_authority(monkeypatch):
    api=client_for_owner(monkeypatch)
    path=PATH.replace("/employer-attempt","/final-action-readiness")
    assert api.get(path).status_code==503
    assert api.post(path,json={
        "confirm_final_submit":True,"employer_permission":True,
    }).status_code in (403,405)
    assert api.put(path,json={}).status_code in (403,405)
    api.cookies.clear()
    assert api.get(path).status_code==401
    api=client_for_owner(monkeypatch)
    assert api.get(path,headers={"Sec-Fetch-Site":"cross-site"}).status_code==403
    assert api.get(path,headers={"Origin":"chrome-extension://synthetic"}).status_code==403
    assert api.get(path,headers={"Origin":"https://evil.invalid"}).status_code==403

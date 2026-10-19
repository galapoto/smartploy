"""SP15f official Lever partner API: real wire contracts, no real employer calls."""
from __future__ import annotations

import json

import httpx
import pytest

from smartploy.lever_partner_submit import (
    LeverPartnerRegistry, LeverPartnerTransport,
    LeverPartnerUnavailable, LeverPartnerUncertain,
)

URL="https://jobs.lever.co/synthetic-partner/posting123/apply"
KEY_ENV="SMARTPLOY_LEVER_PARTNER_KEY_SYNTHETIC"
FIELDS={
    "full_name":"Synthetic Applicant",
    "email":"user@example.invalid",
    "phone":"+358000000000",
    "linkedin":"https://www.linkedin.com/in/synthetic",
    "github":"https://github.com/synthetic",
    "cover_letter":"I personally reviewed this synthetic SQL application and cover letter.",
}
PDF=b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"
CONFIG={
    "synthetic-partner/posting123":{
        "region":"global","form_review_sha256":"d"*64,
        "api_key_env":KEY_ENV,
        "standard_form_only_reviewed":True,
        "consent_policy_reviewed":True,
    }
}

def registry(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_LEVER_PARTNER_JOBS_JSON",json.dumps(CONFIG))
    monkeypatch.setenv(KEY_ENV,"synthetic-owned-by-employer-secret-123456")
    return LeverPartnerRegistry.from_env()


def test_partner_config_is_exact_user_inaccessible_and_default_denies(monkeypatch):
    monkeypatch.delenv("SMARTPLOY_LEVER_PARTNER_JOBS_JSON",raising=False)
    assert not LeverPartnerRegistry.from_env().public_readiness(URL)["partner_api_configured"]
    configured=registry(monkeypatch)
    assert configured.match(URL).region=="global"
    public=configured.public_readiness(URL)
    assert public["partner_api_configured"] is True
    assert "synthetic-owned-by-employer" not in str(public)
    for url in (
        "https://jobs.lever.co/synthetic-partner/another/apply",
        "http://jobs.lever.co/synthetic-partner/posting123/apply",
        "https://jobs.lever.co/synthetic-partner/posting123.evil/apply",
        "https://jobs.eu.lever.co/synthetic-partner/posting123/apply",
        "https://evil.invalid/synthetic-partner/posting123/apply",
        "https://jobs.lever.co/synthetic-partner/posting123/apply?redirect=evil",
    ):
        with pytest.raises(LeverPartnerUnavailable):
            configured.match(url)


@pytest.mark.parametrize("mutate",[
    lambda d: d["synthetic-partner/posting123"].update(standard_form_only_reviewed=False),
    lambda d: d["synthetic-partner/posting123"].update(consent_policy_reviewed=False),
    lambda d: d["synthetic-partner/posting123"].update(api_key_env="UNSAFE"),
    lambda d: d["synthetic-partner/posting123"].update(form_review_sha256="bad"),
    lambda d: d["synthetic-partner/posting123"].update(region="unknown"),
])
def test_invalid_partner_form_or_secret_settings_fail_at_boot(monkeypatch,mutate):
    data=json.loads(json.dumps(CONFIG))
    mutate(data)
    monkeypatch.setenv("SMARTPLOY_LEVER_PARTNER_JOBS_JSON",json.dumps(data))
    with pytest.raises(ValueError):
        LeverPartnerRegistry.from_env()


def test_full_official_multipart_partner_application_acknowledged_once(monkeypatch):
    posting=registry(monkeypatch).match(URL)
    requests=[]
    def handler(req):
        requests.append(req)
        assert req.url.scheme=="https"
        assert req.url.host=="api.lever.co"
        assert req.url.path==posting.api_path
        if req.method=="GET":
            assert req.url.params["mode"]=="json"
            assert "key" not in req.url.params
            return httpx.Response(200,json={
                "id":"posting123","applyUrl":URL,
                "hostedUrl":"https://jobs.lever.co/synthetic-partner/posting123"
            })
        assert req.method=="POST"
        assert req.url.params["key"]==posting.key()
        body=req.content
        for label in (b'name="resume"',b"%PDF-1.4",b'name="name"',
                      b"Synthetic Applicant",b'name="comments"',b"synthetic SQL",
                      b'name="email"',b"user@example.invalid"):
            # Case sensitive data is preserved, but no body or API key is logged.
            if label==b"synthetic SQL":
                continue
            assert label in body
        assert b'name="consent[marketing]"' not in body
        assert b'name="silent"' in body
        return httpx.Response(200,json={"ok":True,"applicationId":"application-synthetic-123456"})
    result=LeverPartnerTransport(httpx.MockTransport(handler)).send(
        posting,application_url=URL,fields=FIELDS,pdf=PDF
    )
    assert result.public_status()["provider_application_acknowledged"] is True
    assert result.public_status()["provider_application_id"]=="application-synthetic-123456"
    assert result.public_status()["employer_hiring_decision_verified"] is False
    assert [req.method for req in requests]==["GET","POST"]


@pytest.mark.parametrize("status,body",[
    (429,{"ok":False,"error":"rate_limited"}),(500,{"ok":False}),
    (307,{"ok":True}),(200,{"ok":False}),
    (200,{"ok":True,"applicationId":"bad\nid"}),
])
def test_nonconfirmed_post_response_never_triggers_automatic_retry(monkeypatch,status,body):
    posting=registry(monkeypatch).match(URL)
    actions=[]
    def handler(request):
        actions.append(request.method)
        if request.method=="GET":
            return httpx.Response(200,json={"id":posting.posting_id,"applyUrl":URL})
        return httpx.Response(status,json=body,headers={"Location":"https://evil.invalid"})
    with pytest.raises(LeverPartnerUncertain):
        LeverPartnerTransport(httpx.MockTransport(handler)).send(
            posting,application_url=URL,fields=FIELDS,pdf=PDF
        )
    assert actions==["GET","POST"]


def test_stale_or_mismatched_posting_never_receives_applicant_pii(monkeypatch):
    posting=registry(monkeypatch).match(URL)
    actions=[]
    def handler(req):
        actions.append(req.method)
        return httpx.Response(200,json={
            "id":"another","applyUrl":"https://evil.invalid/unknown"
        })
    with pytest.raises(LeverPartnerUncertain):
        LeverPartnerTransport(httpx.MockTransport(handler)).send(
            posting,application_url=URL,fields=FIELDS,pdf=PDF
        )
    assert actions==["GET"]


def test_provider_key_never_appears_in_public_api_readiness(monkeypatch):
    posting=registry(monkeypatch).match(URL)
    for invalid in ("missing","short", "x\nY"):
        monkeypatch.setenv(KEY_ENV,invalid)
        with pytest.raises(LeverPartnerUnavailable):
            posting.key()
    monkeypatch.setenv(KEY_ENV,"synthetic-owned-by-employer-secret-123456")
    assert posting.key().startswith("synthetic-")

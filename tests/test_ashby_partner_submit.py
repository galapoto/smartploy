"""SP51: official Ashby API mocked partner wire contract; ZERO employer traffic."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import httpx
import pytest

from smartploy.ashby_partner_submit import (
    AshbyPartnerRegistry, AshbyPartnerTransport,
    AshbyPartnerUnavailable, AshbyPartnerUncertain,
)

URL = "https://jobs.ashbyhq.com/synthetic-org/junior-qa-analyst"
POSTING_ID = "e9ed20fd-d45f-4aad-8a00-a19bfba0083e"
FORM_ID = "7a3d9986-a88a-49f4-b363-8da21b893e30"
APPLICATION_ID = "e9ed20fd-d45f-4aad-8a00-a19bfba0083e"
KEY_ENV = "SMARTPLOY_ASHBY_PARTNER_KEY_SYNTHETIC"
SECRET = "synthetic-employer-issued-ashby-key-987654"
PDF = b"%PDF-1.4\n1 0 obj <<>> endobj\n%%EOF\n"
FIELDS = {
    "full_name": "Synthetic Applicant", "email": "person@example.invalid",
    "phone": "+358000000000", "cover_letter": "This is a deliberately reviewed " +
        "synthetic cover letter for the matching current job, with no sensitive data.",
}
FORM = {"sections": [{"fields": [
    {"isRequired": True, "field": {
        "id": "1", "path": "_systemfield_name", "type": "String",
    }},
    {"isRequired": True, "field": {
        "id": "2", "path": "_systemfield_email", "type": "Email",
    }},
    {"isRequired": True, "field": {
        "id": "3", "path": "_systemfield_resume", "type": "File",
    }},
    {"isRequired": False, "field": {
        "id": "4", "path": "_systemfield_cover_letter", "type": "LongText",
    }},
]}]}


def form_sha(form=FORM):
    return sha256(json.dumps(
        form, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def config(form=FORM):
    return {
        "synthetic-org/junior-qa-analyst": {
            "posting_id": POSTING_ID,
            "form_review_sha256": form_sha(form),
            "api_key_env": KEY_ENV,
            "standard_form_only_reviewed": True,
            "consent_policy_reviewed": True,
            "survey_forms_absent_reviewed": True,
        }
    }


def registry(monkeypatch, form=FORM):
    monkeypatch.setenv("SMARTPLOY_ASHBY_PARTNER_POSTINGS_JSON", json.dumps(config(form)))
    monkeypatch.setenv(KEY_ENV, SECRET)
    return AshbyPartnerRegistry.from_env()


def posting_response(form=FORM):
    return {
        "success": True,
        "results": {
            "id": POSTING_ID, "status": "Published", "isListed": True,
            "applyLink": URL, "applicationFormDefinition": deepcopy(form),
            "surveyFormDefinitions": [],
        },
    }


def submit_response(form=FORM):
    return {
        "success": True,
        "results": {
            "formMessages": {"blocked": False},
            "submittedFormInstance": {
                "id": FORM_ID, "formDefinition": deepcopy(form),
                "submittedValues": {
                    "_systemfield_name": FIELDS["full_name"],
                    "_systemfield_email": FIELDS["email"],
                },
            },
        },
    }


def valid_mock(requests, *, info=None, submitted=None, lookup=None):
    def handle(req):
        requests.append(req)
        assert req.url.scheme == "https"
        assert req.url.host == "api.ashbyhq.com"
        assert req.headers["authorization"].startswith("Basic ")
        assert SECRET.encode() not in req.content
        assert req.method == "POST"
        if req.url.path == "/jobPosting.info":
            data = json.loads(req.content)
            assert data == {
                "jobPostingId": POSTING_ID, "includeUnpublishedJobPostings": False,
            }
            assert b"Synthetic Applicant" not in req.content
            assert b"%PDF" not in req.content
            return httpx.Response(200, json=posting_response() if info is None else info)
        if req.url.path == "/applicationForm.submit":
            body = req.content
            assert b'name="resume_1"' in body
            assert PDF in body
            assert b'name="applicationForm"' in body
            assert b'_systemfield_resume' in body
            assert b'_systemfield_name' in body
            assert b'_systemfield_email' in body
            assert b'_systemfield_cover_letter' in body
            assert b'Synthetic Applicant' in body
            assert b'name="allowSubmissionForUnpublishedJobPosting"' in body
            assert b'\r\n\r\nfalse\r\n' in body
            assert b'\r\n\r\ntrue\r\n' not in body
            assert b'data_compliance' not in body
            assert b'surveySubmission.create' not in body
            return httpx.Response(200, json=submit_response() if submitted is None else submitted)
        if req.url.path == "/application.info":
            assert json.loads(req.content) == {
                "submittedFormInstanceId": FORM_ID,
            }
            return httpx.Response(
                200, json={
                    "success": True, "results": {"id": APPLICATION_ID},
                } if lookup is None else lookup,
            )
        raise AssertionError("Unapproved Ashby endpoint")
    return httpx.MockTransport(handle)


def test_disabled_config_never_grants_submit_capability(monkeypatch):
    monkeypatch.delenv("SMARTPLOY_ASHBY_PARTNER_POSTINGS_JSON", raising=False)
    disabled = AshbyPartnerRegistry.from_env()
    assert disabled.public_readiness(URL) == {
        "partner_api_configured": False, "provider": "",
        "standard_form_reviewed": False,
        "partner_submission_authorized": False,
        "employer_action_performed": False,
    }
    with pytest.raises(AshbyPartnerUnavailable):
        disabled.match(URL)


def test_strict_exact_host_job_and_employer_only_credential(monkeypatch):
    approved = registry(monkeypatch)
    found = approved.match(URL + "/application")
    assert found.posting_id == POSTING_ID
    assert found.key() == SECRET
    assert approved.public_readiness(URL)["partner_api_configured"] is True
    assert SECRET not in str(approved.public_readiness(URL))
    assert "employer_submission_performed" not in approved.public_readiness(URL)
    for raw in (
        "https://jobs.ashbyhq.com/synthetic-org/other-job",
        "https://jobs.ashbyhq.com/synthetic-org/junior-qa-analyst.evil",
        "https://jobs.ashbyhq.com/another-org/junior-qa-analyst",
        "https://evil.invalid/synthetic-org/junior-qa-analyst",
        "https://jobs.ashbyhq.com.evil.invalid/synthetic-org/junior-qa-analyst",
        "http://jobs.ashbyhq.com/synthetic-org/junior-qa-analyst",
        URL + "?redirect=https://evil.invalid",
        URL + "#a",
        URL + "/other",
        "https://candidate@jobs.ashbyhq.com/synthetic-org/junior-qa-analyst",
    ):
        with pytest.raises(AshbyPartnerUnavailable):
            approved.match(raw)


@pytest.mark.parametrize("field,value", [
    ("posting_id", "not-uuid"),
    ("form_review_sha256", "no"),
    ("api_key_env", "INVALID_ENV_NAME"),
    ("standard_form_only_reviewed", False),
    ("consent_policy_reviewed", False),
    ("survey_forms_absent_reviewed", False),
])
def test_unreviewed_posting_configuration_fails_boot(monkeypatch, field, value):
    changed = config()
    changed["synthetic-org/junior-qa-analyst"][field] = value
    monkeypatch.setenv("SMARTPLOY_ASHBY_PARTNER_POSTINGS_JSON", json.dumps(changed))
    with pytest.raises(ValueError):
        AshbyPartnerRegistry.from_env()


@pytest.mark.parametrize("bad", ["missing", "short", "x\nY"])
def test_no_valid_employer_key_no_partner_access(monkeypatch, bad):
    approved = registry(monkeypatch)
    monkeypatch.setenv(KEY_ENV, bad)
    with pytest.raises(AshbyPartnerUnavailable):
        approved.match(URL)


def test_exact_verified_form_then_one_multipart_submit_and_official_application_lookup(monkeypatch):
    posting = registry(monkeypatch).match(URL)
    requests = []
    ack = AshbyPartnerTransport(valid_mock(requests)).send_after_external_claim(
        posting, application_url=URL, fields=FIELDS, pdf=PDF,
    )
    assert [req.url.path for req in requests] == [
        "/jobPosting.info", "/applicationForm.submit", "/application.info",
    ]
    assert ack.public_status() == {
        "provider": "ashby",
        "provider_application_id": APPLICATION_ID,
        "provider_form_submission_id": FORM_ID,
        "provider_application_acknowledged": True,
        "employer_hiring_decision_verified": False,
        "automatic_retry_authorized": False,
    }
    assert SECRET not in str(ack)


@pytest.mark.parametrize("change", [
    lambda d: d.update(id="another"),
    lambda d: d.update(status="Unpublished"),
    lambda d: d.update(isListed=False),
    lambda d: d.update(applyLink="https://jobs.ashbyhq.com/other-org/other-post"),
    lambda d: d.update(surveyFormDefinitions=[{"name": "required survey"}]),
    lambda d: d.update(applicationFormDefinition={"sections": []}),
])
def test_stale_unpublished_or_survey_job_never_receives_cv(monkeypatch, change):
    posting = registry(monkeypatch).match(URL)
    info = posting_response()
    change(info["results"])
    actions = []
    with pytest.raises(AshbyPartnerUnavailable):
        AshbyPartnerTransport(
            valid_mock(actions, info=info),
        ).send_after_external_claim(
            posting, application_url=URL, fields=FIELDS, pdf=PDF,
        )
    assert [req.url.path for req in actions] == ["/jobPosting.info"]


def test_employer_adds_optional_custom_question_before_send_blocks_every_upload(monkeypatch):
    posting = registry(monkeypatch).match(URL)
    edited = deepcopy(FORM)
    edited["sections"][0]["fields"].append({
        "isRequired": False,
        "field": {"path": "question_999", "type": "String"},
    })
    info = posting_response(edited)
    actions = []
    with pytest.raises(AshbyPartnerUnavailable):
        AshbyPartnerTransport(
            valid_mock(actions, info=info),
        ).send_after_external_claim(
            posting, application_url=URL, fields=FIELDS, pdf=PDF,
        )
    assert len(actions) == 1


@pytest.mark.parametrize("body", [
    {"success": False, "errors": [{"message": "test rejection"}]},
    {"success": True, "results": {
        "formMessages": {"blocked": True},
        "submittedFormInstance": {
            "id": FORM_ID, "formDefinition": FORM,
            "submittedValues": {
                "_systemfield_name": FIELDS["full_name"],
                "_systemfield_email": FIELDS["email"],
            },
        },
    }},
    {"success": True, "results": {
        "formMessages": {"blocked": False},
        "submittedFormInstance": {"id": "not-uuid", "formDefinition": FORM},
    }},
    {"success": True, "results": {
        "formMessages": {"blocked": False},
        "submittedFormInstance": {
            "id": FORM_ID, "formDefinition": FORM,
            "submittedValues": {"_systemfield_name": "OTHER", "_systemfield_email": FIELDS["email"]},
        },
    }},
])
def test_untrusted_or_blocked_submit_response_is_uncertain_never_retried(monkeypatch, body):
    posting = registry(monkeypatch).match(URL)
    requests = []
    with pytest.raises(AshbyPartnerUncertain):
        AshbyPartnerTransport(
            valid_mock(requests, submitted=body),
        ).send_after_external_claim(
            posting, application_url=URL, fields=FIELDS, pdf=PDF,
        )
    assert [req.url.path for req in requests] == [
        "/jobPosting.info", "/applicationForm.submit",
    ]


def test_form_accepted_but_application_info_not_verified_requires_reconciliation(monkeypatch):
    posting = registry(monkeypatch).match(URL)
    requests = []
    with pytest.raises(AshbyPartnerUncertain):
        AshbyPartnerTransport(
            valid_mock(requests, lookup={"success": False}),
        ).send_after_external_claim(
            posting, application_url=URL, fields=FIELDS, pdf=PDF,
        )
    assert [req.url.path for req in requests] == [
        "/jobPosting.info", "/applicationForm.submit", "/application.info",
    ]


def test_ambiguous_timeout_never_submits_a_second_application(monkeypatch):
    posting = registry(monkeypatch).match(URL)
    actions = []
    def handler(request):
        actions.append(request.url.path)
        if request.url.path == "/jobPosting.info":
            return httpx.Response(200, json=posting_response())
        if request.url.path == "/applicationForm.submit":
            raise httpx.ReadTimeout("synthetic employer timeout")
        raise AssertionError("Unexpected repeat after uncertain submission")
    with pytest.raises(AshbyPartnerUncertain) as error:
        AshbyPartnerTransport(httpx.MockTransport(handler)).send_after_external_claim(
            posting, application_url=URL, fields=FIELDS, pdf=PDF,
        )
    assert error.value.code == "timeout"
    assert actions == ["/jobPosting.info", "/applicationForm.submit"]


@pytest.mark.parametrize("fields,pdf", [
    ({**FIELDS, "full_name": ""}, PDF),
    ({**FIELDS, "email": "invalid"}, PDF),
    (FIELDS, b"not a pdf"),
    (FIELDS, b"%PDF-not-complete"),
])
def test_invalid_reviewed_fields_or_pdf_fail_before_issuing_api_requests(
    monkeypatch, fields, pdf,
):
    posting = registry(monkeypatch).match(URL)
    requests = []
    with pytest.raises(AshbyPartnerUnavailable):
        AshbyPartnerTransport(valid_mock(requests)).send_after_external_claim(
            posting, application_url=URL, fields=fields, pdf=pdf,
        )
    assert not requests

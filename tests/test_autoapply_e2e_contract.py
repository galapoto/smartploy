"""SP46 real-boundary AutoApply end-to-end ACCEPTANCE CONTRACT.

A single test crosses official-source snapshot -> signed-in CV upload ->
approved facts / user opt-in -> actual Postgres draft + one Agent Zero ->
reviewed deterministic CV PDF -> independent simulated employer rights ->
explicit first-party approval -> actual FastAPI Lever adapter multipart
-> provider-shaped ACK OR uncertain -> immutable receipt/attempt ->
agent reconciliation. It uses a STRICTLY LOCAL httpx.MockTransport, never
contacts a real employer, and never represents synthetic ACKs as live proof.

Contract is executable with:
  pytest -q tests/test_autoapply_e2e_contract.py
Requires the real isolated SMARTPLOY_TEST_DATABASE_URL and migrations.
"""
from __future__ import annotations

from base64 import b64encode
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from uuid import uuid4
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient
from psycopg import connect

from smartploy.api import create_app
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.employer_automation_rights import employer_job_key
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.lever_partner_submit import LeverPartnerTransport
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DSN, reason="SP46 requires an isolated migrated PostgreSQL test database"
)
ORIGIN = "https://smartploy.komplyint.fi"
ISSUER = "https://sso.example.invalid"
SECRET_ENV = "SMARTPLOY_LEVER_PARTNER_KEY_SP46_CONTRACT"
SECRET = "synthetic-employer-key-never-valid"
SITE = "syntheticcontract"


def _synthetic_cv() -> str:
    """Text-based DOCX through the SAME real CV import parser, not a fake CV."""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        '<w:p><w:r><w:t>Synthetic Applicant - Junior Data Analyst</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Approved skills: Python, SQL and data analysis'
        '</w:t></w:r></w:p></w:body></w:document>'
    )
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
    return b64encode(output.getvalue()).decode("ascii")


@pytest.fixture
def contract(monkeypatch):
    """Production-shape OIDC account + two users, original Postgres stores.

    No production credentials, live employer, real CV or external service.
    The source is inserted through the original worker's approved normalized
    direct-ATS source model; user API ingestion is intentionally NOT granted.
    """
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    role = f"Junior Data Analyst Contract {nonce[:12]}"
    url = f"https://jobs.lever.co/{SITE}/{nonce}/apply"
    source_id = "lever-global-syntheticcontract-" + nonce[:12]
    normalized = normalize_observation(
        SourceObservation(
            source_id=source_id, source_mode="api", source_url=url,
            raw_text=role + " Python SQL data analysis",
            observed_at=datetime.now(timezone.utc).replace(
                microsecond=0
            ).isoformat(),
            payload={
                "company": "Synthetic Contract Employer " + nonce[:12],
                "role_title": role,
                "description": (
                    "Junior data analysis and SQL reporting; Python, SQL, "
                    "data analysis, no restricted screening questions."
                ),
                "location": "Helsinki",
                "language": "English",
                "application_url": url,
                "requirements": ["Python", "SQL"],
            },
        ),
        SourcePolicy(
            source_id, "Synthetic reviewed direct ATS",
            "direct_employer_ats", ("api",),
        ),
    )
    assert normalized.candidate is not None
    job = normalized.candidate
    PostgresJobRepository(DSN).upsert(job)

    ids = PostgresIdentityRepository(DSN)
    owner = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer=ISSUER, subject="sp46-owner-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    stranger = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer=ISSUER, subject="sp46-stranger-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    sessions = MemorySessionRepository()
    tokens = {}
    for binding, name in ((owner, "owner"), (stranger, "stranger")):
        identity = AuthenticatedPrincipal(
            issuer=ISSUER, subject="sp46-" + name + "-" + nonce,
            email="same@example.invalid", auth_source="oidc",
        )
        tokens[name] = sessions.create(
            user_id=binding.user_id, principal=identity,
            provider_session_id="sp46-" + name, ttl_seconds=3600,
        ).token

    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", DSN)
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.komplyint.fi")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic-sp46")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
    monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out")
    monkeypatch.setenv(SECRET_ENV, SECRET)
    monkeypatch.setenv("SMARTPLOY_LEVER_PARTNER_JOBS_JSON", json.dumps({
        SITE + "/" + nonce: {
            "region": "global", "api_key_env": SECRET_ENV,
            "form_review_sha256": "a" * 64,
            "standard_form_only_reviewed": True,
            "consent_policy_reviewed": True,
        },
    }))
    app = create_app(
        identity_repository=ids, session_repository=sessions,
        oidc_client=object(),
    )
    api = TestClient(app, base_url=ORIGIN)
    api.cookies.set(SESSION_COOKIE_NAME, tokens["owner"])
    owner_headers = {
        "Origin": ORIGIN, "Sec-Fetch-Site": "same-origin",
        "X-Smartploy-Expected-User-Id": owner.user_id,
    }
    # Keep one approved real normalized job and two synthetic identities.
    # Even the test harness starts WITHOUT permission for a final employer
    # POST; scenario setup must add the independent rights row separately.
    try:
        yield {
            "api": api, "app": app, "owner": owner,
            "stranger": stranger, "tokens": tokens,
            "headers": owner_headers, "nonce": nonce,
            "job": job, "url": url,
            "rights_key": employer_job_key(url),
        }
    finally:
        # Isolated test DB cleanup. Sticky employer attempts stay durable DURING
        # each test, but are removed afterward in dependency-safe order.
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_partner_application_receipts WHERE user_id=%s",
                (owner.user_id,),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_final_approvals WHERE user_id=%s",
                (owner.user_id,),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_submit_claims WHERE user_id=%s",
                (owner.user_id,),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_review_intents WHERE user_id=%s",
                (owner.user_id,),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_automation_rights WHERE employer_job_key_sha256=%s",
                (employer_job_key(url),),
            )
            # Cascades original Agent Zero and timeline in migration 025.
            conn.execute(
                "DELETE FROM smartploy_application_workspaces WHERE profile_id=%s",
                (owner.profile_id,),
            )
            for table in (
                "smartploy_cv_files", "smartploy_search_preferences",
                "smartploy_profile_facts",
            ):
                conn.execute(
                    f"DELETE FROM {table} WHERE profile_id=%s",
                    (owner.profile_id,),
                )
            conn.execute(
                "DELETE FROM smartploy_jobs WHERE canonical_key=%s",
                (job.canonical_key,),
            )


def _require_ok(response):
    assert response.status_code in (200, 201), (
        f"{response.request.method} {response.request.url.path}: "
        f"{response.status_code} {response.text[:400]}"
    )
    return response.json()


def _add_exact_partner_rights(case):
    # Not an app API, never granted by reading a public ATS source or by AI.
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_employer_automation_rights
               (employer_job_key_sha256,action_scope,permission_basis,
                permission_evidence_sha256,terms_evidence_sha256,
                reviewed_by,independently_approved_by,
                reviewed_at,expires_at,state)
               VALUES (%s,'partner_lever_postings_api_submit',
                       'documented_partner_integration',%s,%s,
                       'independent-reviewer-1','independent-reviewer-2',
                       now()-interval '1 day',now()+interval '1 day','approved')""",
            (case["rights_key"], "c" * 64, "d" * 64),
        )


@pytest.mark.parametrize("outcome", ["acknowledged", "provider_uncertain", "no_employer_rights"])
def test_sp46_autoapply_e2e_contract_exact_user_job_and_outcome(contract, outcome):
    case = contract
    api, app = case["api"], case["app"]
    headers, owner = case["headers"], case["owner"]
    job, nonce, url = case["job"], case["nonce"], case["url"]
    calls: list[str] = []

    def employer(request: httpx.Request) -> httpx.Response:
        # This is the ONLY "employer" in the acceptance test. It is a local
        # httpx transport, never an Internet, employer, or applicant endpoint.
        assert request.url.host == "api.lever.co"
        assert request.url.scheme == "https"
        calls.append(request.method)
        if request.method == "GET":
            assert request.url.params.get("mode") == "json"
            return httpx.Response(200, json={"id": nonce, "applyUrl": url})
        assert request.method == "POST"
        assert request.url.params["key"] == SECRET
        assert b'name="resume"' in request.content
        assert b"%PDF-" in request.content
        assert b"Synthetic Applicant" in request.content
        if outcome == "provider_uncertain":
            return httpx.Response(429, json={"error": "test rate limit"})
        return httpx.Response(
            200, json={"ok": True, "applicationId": "sp46-test-" + nonce}
        )
    app.state.partner_lever_transport = LeverPartnerTransport(httpx.MockTransport(employer))

    # 1. First-party OIDC user, real document parser and explicit account facts.
    identity = _require_ok(api.get("/api/v1/session"))
    assert identity["authenticated"] and identity["user_id"] == owner.user_id
    assert api.get("/api/v1/profile/cv").json()["present"] is False
    uploaded = _require_ok(api.post(
        "/api/v1/profile/cv",
        json={"filename": "synthetic.docx", "content_base64": _synthetic_cv()},
        headers=headers,
    ))
    assert uploaded["present"] and uploaded["text_extracted"]
    assert "Approved skills: Python" in uploaded["text_preview"]
    for kind, value in (
        ("identity", "Synthetic Applicant"), ("email", "same@example.invalid"),
        ("skill", "Python"), ("skill", "SQL"),
        ("skill", "data analysis"),
    ):
        _require_ok(api.post("/api/v1/profile/facts", json={
            "fact_type": kind, "value": value, "approved": True,
        }, headers=headers))

    # 2. Owner opts in to reviewable local AutoApply drafts AND a private
    # per-application agent. This does NOT grant final employer transfer.
    prefs = _require_ok(api.get("/api/v1/search-preferences"))
    assert prefs["completed"] is False
    settings = _require_ok(api.put("/api/v1/search-preferences",json={
        "mode": "personalized",
        "roles": [f"Data Analyst Contract {nonce[:12]}"],
        "locations": ["Helsinki"], "languages": [],
        "auto_draft_enabled": True, "auto_agent_tracking_enabled": True,
        "expected_revision": prefs["revision"],
    },headers=headers))
    assert settings["auto_draft_enabled"] is True
    assert settings["auto_agent_tracking_enabled"] is True
    matched = _require_ok(api.get("/api/v1/profile/cv/matches"))
    assert matched.get("match_mode") != "no_cv"

    # 3. Trusted source-current Finnish vacancy advances to EXACTLY ONE
    # private draft and persistent Agent Zero. A second scan is idempotent.
    first = _require_ok(api.post("/api/v1/auto-draft/prepare",headers=headers))
    assert first["created"] == 1, first
    assert first["agents_started"] == 1, first
    assert first["provider_calls"] == 0
    assert first["employer_actions_performed"] is False
    assert first["automatic_submission_authorized"] is False
    again = _require_ok(api.post("/api/v1/auto-draft/prepare",headers=headers))
    assert again["created"] == 0 and again["already_prepared"] >= 1
    assert again["agents_started"] == 0 and again["agents_already_present"] >= 1
    assert calls == []

    owned = _require_ok(api.get("/api/v1/application-workspaces"))["workspaces"]
    candidates = [w for w in owned if w["canonical_key"] == job.canonical_key]
    assert len(candidates) == 1
    draft = candidates[0]
    assert draft["status"] == "draft"
    assert draft["authority"]["may_submit_to_employer"] is False
    wid = draft["workspace_id"]
    path = f"/api/v1/application-workspaces/{wid}"
    agent = _require_ok(api.get(path + "/agent"))
    assert agent["present"] is True
    assert agent["agent"]["external_actions_authorized"] is False
    agent_id = agent["agent"]["agent_id"]
    assert len(app.state.application_agent_repository.events(owner.profile_id, agent_id)) == 1

    # 4. Applicant explicitly saves/reads the reviewed truthful CV/letter.
    saved = _require_ok(api.put(path,headers=headers,json={
        "expected_revision": draft["revision"],
        "cv_text": (
            "Synthetic Applicant\nJunior Data Analyst\n"
            "Approved Python SQL data analysis experience."
        ),
        "cover_letter_text": (
            "Dear hiring team, I reviewed this synthetic junior data analyst "
            "application and my approved Python and SQL qualifications. "
            "Kind regards, Synthetic Applicant."
        ),
    }))["workspace"]
    assert saved["revision"] == draft["revision"] + 1
    download = api.get(path + "/download/cv/pdf")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")
    assert "no-store" in download.headers["cache-control"]

    # 5. No partner rights -> no final transfer, even with a configured key.
    before = _require_ok(api.get(path + "/partner-lever-readiness"))
    assert before["partner_api_configured"] is True
    assert before["independent_partner_rights_reviewed"] is False
    assert before["eligible_for_explicit_partner_submit"] is False
    assert before["unattended_auto_apply_enabled"] is False
    assert calls == []
    if outcome != "no_employer_rights":
        _add_exact_partner_rights(case)
    authorized = _require_ok(api.get(path + "/partner-lever-readiness"))
    assert authorized["independent_partner_rights_reviewed"] == (
        outcome != "no_employer_rights"
    )

    # 6. Exact signed-in review intent and second explicit user approval.
    # Readiness evidence has no CV or identity contact data and is nonbearer.
    evidence = authorized["review_evidence"]
    if outcome == "no_employer_rights":
        assert evidence is None
        blocked = api.post(path + "/partner-lever-apply",headers=headers,json={
            "expected_revision": saved["revision"],
            "expected_document_sha256": "a" * 64,
            "expected_cv_pdf_sha256": "b" * 64,
            "expected_fields_sha256": "c" * 64,
            "expected_cv_pdf_size": 1024,
            "explicit_final_user_approval": True,
            "approve_employer_data_transfer": True,
            "affirm_reviewed_employer_form": True,
        })
        assert blocked.status_code == 409
        assert calls == []
        assert _require_ok(api.get(path))["workspace"]["status"] == "draft"
        return

    assert evidence["workspace_id"] == wid
    assert evidence["revision"] == saved["revision"]
    assert "Synthetic Applicant" not in json.dumps(evidence)
    assert "same@example.invalid" not in json.dumps(evidence)
    intent = {
        "expected_revision": saved["revision"],
        "expected_document_sha256": evidence["document_sha256"],
        "expected_cv_pdf_sha256": evidence["cv_pdf_sha256"],
        "confirm_reviewed_application": True,
        "acknowledge_manual_only": True,
    }
    accepted = _require_ok(api.post(
        path + "/submit-review-intent",json=intent,headers=headers
    ))
    assert accepted["review_recorded"] is True
    payload = {
        "expected_revision": saved["revision"],
        "expected_document_sha256": evidence["document_sha256"],
        "expected_cv_pdf_sha256": evidence["cv_pdf_sha256"],
        "expected_fields_sha256": evidence["approved_fields_sha256"],
        "expected_cv_pdf_size": evidence["cv_pdf_size"],
        "explicit_final_user_approval": True,
        "approve_employer_data_transfer": True,
        "affirm_reviewed_employer_form": True,
    }

    # A different OIDC SUBJECT with the SAME display email can never read
    # this owner's candidate, documents, final readiness or provider ACK.
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["stranger"])
    assert api.get(path).status_code == 404
    assert api.get(path + "/partner-lever-readiness").status_code == 404
    assert api.get(path + "/agent").json()["present"] is False
    assert api.post(
        path + "/partner-lever-apply",json=payload,headers=headers,
    ).status_code in {403, 404, 409}  # Existing owner-preflight conflict also denies safely.
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["owner"])
    assert calls == []

    # No automatic submit without a FRESH final applicant interaction.
    wrong = api.post(path + "/partner-lever-apply",json={
        **payload, "explicit_final_user_approval": False,
    },headers=headers)
    assert wrong.status_code == 422
    assert calls == []

    # 7. One approved HTTP request -> fixed Lever host, one synthetic
    # multipart POST with the approved PDF. The claim is committed first.
    result = api.post(path + "/partner-lever-apply",json=payload,headers=headers)
    assert result.status_code == (200 if outcome == "acknowledged" else 202)
    assert calls == ["GET", "POST"]
    assert "no-store" in result.headers["cache-control"]
    assert SECRET not in result.text
    assert "same@example.invalid" not in result.text

    # 8. Distinguish provider-issued ID from an uncertain attempt; either
    # way, a second button click / device / worker must NEVER POST again.
    receipt_response = _require_ok(api.get(path + "/partner-lever-receipt"))
    updated = _require_ok(api.get(path))["workspace"]
    attempt = _require_ok(api.get(path + "/employer-attempt"))
    assert attempt["previous_attempt_reserved"] is True
    replay = api.post(path + "/partner-lever-apply",json=payload,headers=headers)
    assert replay.status_code == 409
    assert calls == ["GET", "POST"]

    agent_repo = app.state.application_agent_repository
    if outcome == "acknowledged":
        assert result.json()["state"] == "provider_acknowledged"
        assert result.json()["provider_application_id"] == "sp46-test-" + nonce
        assert receipt_response["present"] is True
        assert receipt_response["receipt"]["provider_application_acknowledged"] is True
        assert updated["status"] == "provider_acknowledged"
        assert updated["authority"]["has_external_submission_proof"] is True
        assert updated["authority"]["may_edit"] is False
        assert agent_repo.reconcile_workspace_updates(profile_id=owner.profile_id, agent_id=agent_id) == 1
        assert agent_repo.get(owner.profile_id,agent_id)["observed_workspace_status"] == (
            "provider_acknowledged"
        )
        events = agent_repo.events(owner.profile_id,agent_id)
        assert [event["event_type"] for event in events] == [
            "case_created", "application_provider_acknowledged",
        ]
        assert all(event["external_actions_performed"] == 0 for event in events)
    else:
        assert result.json()["state"] == "outcome_uncertain"
        assert result.json()["automatic_retry_authorized"] is False
        assert result.json()["requires_human_reconciliation"] is True
        assert receipt_response["present"] is False
        assert updated["status"] == "draft"
        assert updated["authority"]["has_external_submission_proof"] is False
        assert agent_repo.reconcile_workspace_updates(profile_id=owner.profile_id, agent_id=agent_id) == 0
        assert len(agent_repo.events(owner.profile_id,agent_id)) == 1

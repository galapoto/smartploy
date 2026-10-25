"""SP26 one-use browser final claim: real Postgres and OIDC, no employer traffic.

End-to-end verification of original review + two-person rights +
server-atomic one-attempt reservation. This test never clicks an external page.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import connect

from smartploy.api import create_app
from smartploy.application_workspace import new_workspace
from smartploy.application_workspace_storage import PostgresWorkspaceRepository
from smartploy.browser_handoff import make_browser_packet
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.employer_automation_rights import employer_job_key
from smartploy.employer_submit_claim_storage import PostgresEmployerSubmitClaimRepository
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.profile import ProfileFact
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SmartPloy PostgreSQL CI required")


@pytest.fixture
def reviewed_case(monkeypatch):
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    origin = "https://smartploy.komplyint.fi"
    url = f"https://jobs.lever.co/synthetic/{nonce}/apply"
    issuer = "https://sso.example.invalid"
    outcomes = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url=url, raw_text="Synthetic junior IT data analyst",
            payload={
                "role_title": "Junior Data Analyst",
                "company": "Synthetic Reviewed Employer",
                "description": "Approved Python SQL analytical work",
                "location": "Helsinki",
                "application_url": url,
            },
            observed_at="2026-10-23T07:00:00+00:00",
        ),
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    )
    assert outcomes.candidate is not None
    job = outcomes.candidate
    principal_a = AuthenticatedPrincipal(
        issuer=issuer, subject="browser-final-a-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    )
    principal_b = AuthenticatedPrincipal(
        issuer=issuer, subject="browser-final-b-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    )
    identities = PostgresIdentityRepository(DSN)
    a, b = identities.resolve_or_create(principal_a), identities.resolve_or_create(principal_b)
    profile = PostgresProfileRepository(DSN, profile_id=a.profile_id)
    for kind, value in (
        ("identity", "Synthetic Applicant"),
        ("email", "candidate@example.invalid"),
        ("skill", "Python SQL"),
    ):
        profile.upsert_fact(ProfileFact(kind, value, "user-entered", approved=True))
    jobs = PostgresJobRepository(DSN)
    workspaces = PostgresWorkspaceRepository(DSN)
    work = None
    try:
        jobs.upsert(job)
        work = new_workspace(
            job, profile.profile(),
            source_cv_text="Synthetic Applicant\nPython SQL and analytical experience",
        )
        work = replace(
            work,
            cover_letter_text=(
                "Dear hiring team, I have reviewed every claim in my application. "
                "My Python SQL and data-analysis experience meets this fictional role. "
                "Kind regards, Synthetic Applicant."
            ),
        )
        assert workspaces.create_or_get(work)[1] is True
        packet = make_browser_packet(work, job, profile.profile())

        monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
        monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
        monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", origin)
        monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.komplyint.fi")
        monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", issuer)
        monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic")
        monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", origin + "/auth/callback")
        monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", origin + "/auth/logged-out")
        monkeypatch.setenv("SMARTPLOY_DATABASE_URL", DSN)
        monkeypatch.setenv("SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED", "true")
        sessions = MemorySessionRepository()
        tokens = {}
        for name, binding, principal in (("a", a, principal_a), ("b", b, principal_b)):
            tokens[name] = sessions.create(
                user_id=binding.user_id, principal=principal,
                provider_session_id="synthetic-" + name, ttl_seconds=3600,
            ).token
        api = TestClient(
            create_app(
                identity_repository=identities, session_repository=sessions,
                oidc_client=object(),
            ),
            base_url=origin,
        )
        api.cookies.set(SESSION_COOKIE_NAME, tokens["a"])
        headers = {
            "Origin": origin, "Sec-Fetch-Site": "same-origin",
            "X-Smartploy-Expected-User-Id": a.user_id,
        }
        review_route = f"/api/v1/application-workspaces/{work.workspace_id}/submit-review-intent"
        claim_route = f"/api/v1/application-workspaces/{work.workspace_id}/browser-final-attempt"
        body = {
            "expected_revision": work.revision,
            "expected_document_sha256": packet["document_sha256"],
            "expected_cv_pdf_sha256": packet["cv_pdf_sha256"],
            "expected_fields_sha256": packet["approved_fields_sha256"],
            "expected_application_url_sha256":
                sha256(packet["application_url"].encode("utf-8")).hexdigest(),
            "expected_cv_pdf_size": packet["cv_pdf_size"],
            "confirm_one_job_final_click": True,
            "acknowledge_external_employer_transfer": True,
            "acknowledge_no_automatic_retry": True,
        }
        review_body = {
            "expected_revision": work.revision,
            "expected_document_sha256": packet["document_sha256"],
            "expected_cv_pdf_sha256": packet["cv_pdf_sha256"],
            "confirm_reviewed_application": True,
            "acknowledge_manual_only": True,
        }
        yield {
            "api": api, "a": a, "b": b, "tokens": tokens, "work": work,
            "packet": packet, "headers": headers, "body": body,
            "review_body": review_body, "review_route": review_route,
            "claim_route": claim_route, "url": url,
        }
    finally:
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_employer_final_approvals WHERE user_id IN (%s,%s)",
                (a.user_id,b.user_id),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_automation_rights WHERE employer_job_key_sha256=%s",
                (employer_job_key(url),),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_review_intents WHERE user_id IN (%s,%s)",
                (a.user_id,b.user_id),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_submit_claims WHERE user_id IN (%s,%s)",
                (a.user_id,b.user_id),
            )
        if work:
            # A reconciled browser observation has a separate private ledger;
            # clean it before removing this synthetic application workspace.
            with connect(DSN) as conn:
                conn.execute(
                    "DELETE FROM smartploy_browser_receipts WHERE profile_id=%s AND workspace_id=%s",
                    (a.profile_id, work.workspace_id),
                )
            workspaces.delete(a.profile_id, work.workspace_id)
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_profile_facts WHERE profile_id=%s",
                (a.profile_id,),
            )
            conn.execute(
                "DELETE FROM smartploy_jobs WHERE canonical_key=%s",
                (job.canonical_key,),
            )
            for table in ("smartploy_user_identities", "smartploy_user_profiles", "smartploy_users"):
                conn.execute(
                    f"DELETE FROM {table} WHERE user_id IN (%s,%s)",
                    (a.user_id,b.user_id),
                )


def authorize_review_and_employer(case):
    api = case["api"]
    review = api.post(
        case["review_route"], json=case["review_body"], headers=case["headers"],
    )
    assert review.status_code == 200, review.text
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_employer_automation_rights
               (employer_job_key_sha256,permission_basis,permission_evidence_sha256,
                terms_evidence_sha256,reviewed_by,independently_approved_by,
                reviewed_at,expires_at,state)
               VALUES (%s,'explicit_employer_authorization',%s,%s,
                'auditor-a-123','auditor-b-456',now()-interval '1 day',
                now()+interval '1 day','approved')""",
            (employer_job_key(case["url"]), "e" * 64, "f" * 64),
        )


def test_production_feature_switch_denies_unapproved_browser_claim(reviewed_case):
    case = reviewed_case
    api, route = case["api"], case["claim_route"]
    # Admin-level flag is an independent circuit breaker, not a CV preference.
    api.app.state.browser_final_enabled = False
    r = api.post(route, json=case["body"], headers=case["headers"])
    assert r.status_code == 403
    assert PostgresEmployerSubmitClaimRepository(DSN).get(
        case["a"], case["work"].canonical_key,
    ) is None


def test_exact_oidc_review_two_person_rights_reserves_once_without_employer_send(reviewed_case):
    case = reviewed_case
    api, route = case["api"], case["claim_route"]
    headers = case["headers"]
    assert api.post(route, json=case["body"], headers=headers).status_code == 409
    authorize_review_and_employer(case)
    # Two-account/Origin/duplicate defenses are tested *before* consuming claim.
    for changed in (
        {"expected_cv_pdf_sha256": "0" * 64},
        {"expected_fields_sha256": "0" * 64},
        {"expected_application_url_sha256": "0" * 64},
        {"expected_cv_pdf_size": case["body"]["expected_cv_pdf_size"] + 1},
        {"acknowledge_no_automatic_retry": False},
    ):
        item = api.post(route, json={**case["body"], **changed}, headers=headers)
        assert item.status_code in {409, 422}, (changed,item.text)
    assert api.post(
        route, json=case["body"],
        headers={**headers, "Origin": "https://attacker.invalid"},
    ).status_code == 403
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["b"])
    assert api.post(route, json=case["body"], headers=headers).status_code == 409
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["a"])
    first = api.post(route, json=case["body"], headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["claim_reserved"] is True
    assert body["one_job_browser_click_permitted"] is True
    assert body["external_actions_performed"] is False
    assert body["provider_acknowledged"] is False
    assert body["automatic_retry_authorized"] is False
    assert body["claim_id"].startswith("employer-claim-")
    assert "no-store" in first.headers["cache-control"]
    assert case["url"] not in first.text
    assert "candidate@example.invalid" not in first.text
    prior = PostgresEmployerSubmitClaimRepository(DSN).get(
        case["a"], case["work"].canonical_key,
    )
    assert prior is not None
    assert prior.claim_id == body["claim_id"]
    assert prior.state == "reserved_unverified"
    assert api.post(route, json=case["body"], headers=headers).status_code == 409
    assert api.post(
        case["review_route"],json=case["review_body"],headers=headers,
    ).status_code == 409
    # A claimed browser click never increments a verified provider ACK count.
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM smartploy_partner_application_receipts WHERE profile_id=%s",
                (case["a"].profile_id,),
            )
            assert cur.fetchone()[0] == 0


def test_reserved_browser_attempt_reconciles_observed_receipt_then_owner_report(reviewed_case):
    """SP31: finish a previously claimed application, never send the same job twice.

    Uses the real OIDC / PostgreSQL HTTP routes, but only a synthetic employer
    job and a fake on-page observation. No external employer request is made.
    """
    case = reviewed_case
    api = case["api"]
    workspace = case["work"]
    path = f"/api/v1/application-workspaces/{workspace.workspace_id}"
    headers = case["headers"]
    authorize_review_and_employer(case)
    reserved = api.post(case["claim_route"], json=case["body"], headers=headers)
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["provider_acknowledged"] is False

    # Reuse the original transactional PostgreSQL claim guard: no CV or
    # letter change is permitted while an employer attempt remains reserved.
    altered = api.put(path, json={
        "expected_revision": workspace.revision,
        "cv_text": workspace.cv_text + "\\nUnreviewed later edits",
        "cover_letter_text": workspace.cover_letter_text,
    }, headers=headers)
    assert altered.status_code == 409, altered.text
    assert "reserved" in altered.text.lower()

    # Merely consuming a browser claim is not proof of a completed send.
    before_receipt = api.post(
        path + "/report-applied", json={
            "expected_revision": workspace.revision,
            "confirmed_external_application": True,
            "reference": "SYNTHETIC-ACK-1234",
        }, headers=headers,
    )
    assert before_receipt.status_code == 409
    assert api.get(path).json()["workspace"]["status"] == "draft"

    observed = {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": workspace.workspace_id,
        "document_revision": workspace.revision,
        "document_sha256": case["packet"]["document_sha256"],
        "application_url": workspace.application_url,
        "confirmation_page_url": case["url"].replace("/apply", "/confirmation")
            + "?private_query=never_store",
        "reference": "SYNTHETIC-ACK-1234",
        "confirmation_page_sha256": "b" * 64,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_visible": True,
    }
    # The claimed employer job still permits evidence-only reconciliation.
    receipt = api.post(
        path + "/browser-receipt",
        json={"confirm_user_observed": True, "receipt": observed},
        headers=headers,
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["receipt"]["status"] == "browser_observed_unverified"
    assert receipt.json()["external_confirmation_verified"] is False
    assert receipt.json()["receipt"]["actually_submitted_count_changed"] is False

    # Same visible email, but a different OIDC subject cannot read this record.
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["b"])
    assert api.get(path + "/browser-receipt").status_code == 404
    assert api.post(
        path + "/report-applied", json={
            "expected_revision": workspace.revision,
            "confirmed_external_application": True,
            "reference": "SYNTHETIC-ACK-1234",
        }, headers=headers,
    ).status_code in {403, 404, 409}
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["a"])

    # Owner explicitly reports a confirmed delivery. This updates ONLY the
    # local application workspace, never a provider-issued acknowledgment.
    report = api.post(
        path + "/report-applied", json={
            "expected_revision": workspace.revision,
            "confirmed_external_application": True,
            "reference": "SYNTHETIC-ACK-1234",
        }, headers=headers,
    )
    assert report.status_code == 200, report.text
    assert report.json()["workspace"]["status"] == "self_reported_applied"
    assert report.json()["external_confirmation_verified"] is False
    saved = api.get(path, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["workspace"]["status"] == "self_reported_applied"
    assert api.get(path + "/browser-receipt").json()["present"] is True
    assert api.post(case["claim_route"], json=case["body"], headers=headers).status_code == 409
    # Prior attempt remains in the durable cross-device ledger, not released
    # by importing an observation or by reporting the applicant's outcome.
    claim = PostgresEmployerSubmitClaimRepository(DSN).get(
        case["a"], workspace.canonical_key,
    )
    assert claim is not None and claim.claim_id == reserved.json()["claim_id"]
    with connect(DSN) as conn:
        row = conn.execute(
            "SELECT count(*) FROM smartploy_partner_application_receipts WHERE profile_id=%s",
            (case["a"].profile_id,),
        ).fetchone()
        assert row and row[0] == 0


def test_sp32_explicit_autoapply_queue_creates_one_private_agent_per_selected_job(reviewed_case):
    """AutoApply opt-in binds a logical case without another user click or send.

    Uses the original signed-in OIDC and real Postgres fixture, a synthetic job
    and zero employer traffic. Legacy manual/assisted POST stays unchanged.
    """
    case = reviewed_case
    api, work, headers = case["api"], case["work"], case["headers"]
    start = f"/api/v1/jobs/{work.canonical_key}/application-workspace"
    route = f"/api/v1/application-workspaces/{work.workspace_id}/agent"
    repo = api.app.state.application_agent_repository

    # Manual/assisted prepares documents but never silently starts an agent.
    old_client = api.post(start, headers=headers)
    assert old_client.status_code == 200, old_client.text
    assert old_client.json()["created"] is False
    assert "agent_tracking" not in old_client.json()
    assert api.get(route).json()["present"] is False

    payload = {
        "start_private_agent": True,
        "confirm_in_app_tracking_only": True,
    }
    missing_consent = api.post(start, json={
        "start_private_agent": True,
        "confirm_in_app_tracking_only": False,
    }, headers=headers)
    assert missing_consent.status_code == 422
    assert repo.get_for_workspace(case["a"].profile_id, work.workspace_id) is None
    assert api.post(start, json={
        **payload, "external_send": True,
    }, headers=headers).status_code == 422
    assert api.post(start, json={
        "start_private_agent": "true",
        "confirm_in_app_tracking_only": True,
    }, headers=headers).status_code == 422
    assert api.post(start, json=payload, headers={
        **headers, "Origin": "https://hostile.example.invalid",
    }).status_code == 403
    assert api.post(start, json=payload, headers={
        **headers, "Sec-Fetch-Site": "cross-site",
    }).status_code == 403

    started = api.post(start, json=payload, headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["workspace"]["workspace_id"] == work.workspace_id
    tracking = started.json()["agent_tracking"]
    assert tracking == {
        "requested": True, "state": "active", "created": True,
        "external_actions_performed": 0, "worker_wake_verified": False,
    }
    original = api.get(route).json()
    assert original["present"] is True
    assert original["agent"]["workspace_id"] == work.workspace_id
    assert original["agent"]["external_actions_authorized"] is False
    assert len(repo.events(case["a"].profile_id, original["agent"]["agent_id"])) == 1

    # Batch retries and repeated selections reuse the same durable identity.
    again = api.post(start, json=payload, headers=headers)
    assert again.status_code == 200
    assert again.json()["agent_tracking"]["created"] is False
    assert api.get(route).json()["agent"]["agent_id"] == original["agent"]["agent_id"]
    assert len(repo.events(case["a"].profile_id, original["agent"]["agent_id"])) == 1
    assert api.get(
        f"/api/v1/application-workspaces/{work.workspace_id}/employer-attempt",
        headers=headers,
    ).json()["previous_attempt_reserved"] is False

    # Same display email does not identify the same OIDC subject or case.
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["b"])
    assert api.get(route).json()["present"] is False
    assert api.post(start, json=payload, headers=headers).status_code in {403, 409}
    api.cookies.set(SESSION_COOKIE_NAME, case["tokens"]["a"])

    # Agent storage failure does not discard a successfully saved workspace.
    api.app.state.application_agent_repository = None
    unavailable = api.post(start, json=payload, headers=headers)
    assert unavailable.status_code == 200
    assert unavailable.json()["agent_tracking"]["state"] == "unavailable"
    assert unavailable.json()["agent_tracking"]["worker_wake_verified"] is False
    assert unavailable.json()["workspace"]["workspace_id"] == work.workspace_id

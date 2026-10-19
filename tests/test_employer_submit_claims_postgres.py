"""SP15a real PostgreSQL race/ownership/erasure tests. Synthetic only.

No browser or employer requests are sent by these tests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json

import httpx
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg.types.json import Jsonb

from smartploy.api import create_app
from smartploy.application_workspace import new_workspace
from smartploy.application_workspace_storage import PostgresWorkspaceRepository
from smartploy.browser_handoff import approved_fields_sha256, make_browser_packet
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import ProfileFact
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService
from smartploy.account_erasure import (
    PostgresAccountErasureRepository, inspect_quarantined_account,
)
from smartploy.employer_submit_claim_storage import (
    EmployerSubmitClaimDenied, PostgresEmployerSubmitClaimRepository,
)
from smartploy.employer_review_intent_storage import (
    EmployerReviewIntentDenied, PostgresEmployerReviewIntentRepository,
)
from smartploy.employer_automation_rights import (
    PostgresEmployerAutomationRightsRepository, employer_job_key,
)
from smartploy.employer_final_action_gate import (
    EmployerFinalActionDenied, PostgresEmployerFinalActionGate,
)
from smartploy.lever_partner_submit import LeverPartnerTransport, PostgresPartnerApplicationReceipts
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture
def scoped():
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    job_key = "employer-job-" + nonce
    url = "https://jobs.lever.co/testorg/" + nonce
    fingerprint = sha256(("job:" + nonce).encode()).hexdigest()
    letter = "Dear hiring team, I am applying for the advertised role. " + (
        "All statements and contact details must be checked by the applicant."
    )
    ids = PostgresIdentityRepository(DSN)
    a = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid", subject="claim-a-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    b = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid", subject="claim-b-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    wa, wb = "workspace-claim-a-" + nonce, "workspace-claim-b-" + nonce
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_jobs (
                 canonical_key,job_id,company,role_title,candidate,
                 first_seen_at,last_seen_at,source_current
               ) VALUES (%s,%s,'Test Ltd','Engineer',%s,now(),now(),true)""",
            (job_key, "job-" + nonce, Jsonb({
                "description_fingerprint": fingerprint,
                "job": {"application_url": url},
            })),
        )
        for profile_id, workspace_id in ((a.profile_id, wa), (b.profile_id, wb)):
            conn.execute(
                """INSERT INTO smartploy_application_workspaces (
                     workspace_id,profile_id,canonical_key,role_title,company,
                     application_url,cv_text,cover_letter_text,job_fingerprint
                   ) VALUES (%s,%s,%s,'Engineer','Test Ltd',%s,%s,%s,%s)""",
                (
                    workspace_id, profile_id, job_key, url,
                    "Reviewed synthetic resume with sufficient content", letter, fingerprint,
                ),
            )
    ledger = PostgresEmployerSubmitClaimRepository(DSN)

    def reserve(binding=a, workspace_id=wa, revision=1, approved=True, rights=True):
        return PostgresEmployerSubmitClaimRepository(DSN).reserve(
            binding,
            workspace_id=workspace_id,
            expected_revision=revision,
            expected_application_url=url,
            expected_job_fingerprint=fingerprint,
            explicit_final_user_approval=approved,
            employer_submission_permitted=rights,
        )

    yield a, b, wa, wb, job_key, url, fingerprint, letter, ledger, reserve

    with connect(DSN) as conn:
        conn.execute(
            "DELETE FROM smartploy_employer_final_approvals WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_employer_automation_rights WHERE employer_job_key_sha256=%s",
            (employer_job_key(url),),
        )
        conn.execute(
            "DELETE FROM smartploy_profile_facts WHERE profile_id IN (%s,%s)",
            (a.profile_id, b.profile_id),
        )
        conn.execute(
            "DELETE FROM smartploy_employer_review_intents WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_employer_submit_claims WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        conn.execute(
            """DELETE FROM smartploy_obumai_erasure_obligations
               WHERE request_id IN (
                  SELECT request_id FROM smartploy_account_erasure_requests
                  WHERE user_id IN (%s,%s)
               )""", (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_account_erasure_requests WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_browser_receipts WHERE profile_id IN (%s,%s)",
            (a.profile_id, b.profile_id),
        )
        conn.execute(
            "DELETE FROM smartploy_application_workspaces WHERE profile_id IN (%s,%s)",
            (a.profile_id, b.profile_id),
        )
        conn.execute("DELETE FROM smartploy_jobs WHERE canonical_key IN (%s,%s)",
                     (job_key, job_key + "-mirror"))
        for table in ("smartploy_user_identities", "smartploy_user_profiles", "smartploy_users"):
            conn.execute(f"DELETE FROM {table} WHERE user_id IN (%s,%s)", (a.user_id, b.user_id))


def test_8_competing_workers_create_exactly_one_durable_marker(scoped):
    a, b, wa, wb, job_key, url, fp, letter, ledger, reserve = scoped
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(int(inserted) for _, inserted in results) == 1
    assert len({claim.claim_id for claim, _ in results}) == 1
    claim = results[0][0]
    assert claim.state == "reserved_unverified"
    assert claim.document_sha256 == sha256(
        ("Reviewed synthetic resume with sufficient content" + "\0" + letter).encode()
    ).hexdigest()
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a, job_key).claim_id == claim.claim_id
    assert ledger.get(b, job_key) is None
    public = claim.to_review_dict()
    assert public["employer_submission_verified"] is False
    assert public["automatic_retry_authorized"] is False
    assert a.user_id not in str(public) and url not in str(public)


def test_revision_and_workspace_recreation_do_not_issue_second_attempt(scoped):
    a, _, wa, _, job_key, url, fp, letter, ledger, reserve = scoped
    first, created = reserve()
    assert created
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_application_workspaces
               SET revision=2, cv_text='New reviewed CV', updated_at=now()
               WHERE workspace_id=%s""", (wa,),
        )
    with pytest.raises(EmployerSubmitClaimDenied, match="changed"):
        reserve(revision=1)
    second, new = reserve(revision=2)
    assert not new and second.claim_id == first.claim_id
    assert second.document_revision == 1
    with connect(DSN) as conn:
        conn.execute("DELETE FROM smartploy_application_workspaces WHERE workspace_id=%s", (wa,))
        replacement_id = "workspace-replacement-" + uuid4().hex
        conn.execute(
            """INSERT INTO smartploy_application_workspaces (
                 workspace_id,profile_id,canonical_key,role_title,company,
                 application_url,cv_text,cover_letter_text,job_fingerprint
               ) VALUES (%s,%s,%s,'Engineer','Test Ltd',%s,%s,%s,%s)""",
            (replacement_id, a.profile_id, job_key, url, "Recreated reviewed CV", letter, fp),
        )
    again, created = reserve(workspace_id=replacement_id)
    assert not created and again.claim_id == first.claim_id


def test_owner_approval_and_employer_policy_gates(scoped):
    a, b, wa, wb, key, _, _, _, ledger, reserve = scoped
    with pytest.raises(EmployerSubmitClaimDenied, match="approval"):
        reserve(approved=False)
    with pytest.raises(EmployerSubmitClaimDenied, match="approval"):
        reserve(rights=False)
    with pytest.raises(EmployerSubmitClaimDenied, match="workspace"):
        reserve(binding=b, workspace_id=wa)
    with pytest.raises(EmployerSubmitClaimDenied, match="owner|binding|disabled"):
        reserve(binding=replace(a, user_id=b.user_id))
    assert ledger.get(a, key) is None
    own_b, created = reserve(binding=b, workspace_id=wb)
    assert created and own_b.user_id == b.user_id
    assert ledger.get(a, key) is None
    assert ledger.get(b, key).claim_id == own_b.claim_id


def test_stale_posting_document_and_previous_receipt_refused(scoped):
    a, _, wa, _, key, url, fp, _, ledger, reserve = scoped
    with connect(DSN) as conn:
        conn.execute("UPDATE smartploy_jobs SET source_current=false WHERE canonical_key=%s", (key,))
    with pytest.raises(EmployerSubmitClaimDenied, match="no longer current"):
        reserve()
    with connect(DSN) as conn:
        conn.execute("UPDATE smartploy_jobs SET source_current=true WHERE canonical_key=%s", (key,))
        conn.execute(
            "UPDATE smartploy_application_workspaces SET job_fingerprint='changed' WHERE workspace_id=%s",
            (wa,),
        )
    with pytest.raises(EmployerSubmitClaimDenied, match="changed"):
        reserve()
    with connect(DSN) as conn:
        conn.execute(
            "UPDATE smartploy_application_workspaces SET job_fingerprint=%s WHERE workspace_id=%s",
            (fp, wa),
        )
        conn.execute(
            """INSERT INTO smartploy_browser_receipts (
                 profile_id,workspace_id,document_revision,document_sha256,
                 reference,confirmation_page_url,confirmation_page_sha256,
                 observed_at,evidence_digest
               ) VALUES (%s,%s,1,%s,'TST-1234',
                         'https://jobs.lever.co/testorg/confirmation',%s,now(),%s)""",
            (a.profile_id, wa, "b" * 64, "c" * 64, "d" * 64),
        )
    with pytest.raises(EmployerSubmitClaimDenied, match="receipt"):
        reserve()
    assert ledger.get(a, key) is None


def test_uncertain_is_sticky_owner_scoped_and_never_an_automatic_retry(scoped):
    a, b, _, _, key, _, _, _, ledger, reserve = scoped
    item, created = reserve()
    assert created
    with pytest.raises(EmployerSubmitClaimDenied, match="owner"):
        ledger.mark_uncertain(b, item.claim_id, code="timeout")
    with pytest.raises(EmployerSubmitClaimDenied, match="sanitized"):
        ledger.mark_uncertain(a, item.claim_id, code="leak_private_reason")
    uncertain = ledger.mark_uncertain(a, item.claim_id, code="timeout")
    assert uncertain.state == "uncertain"
    assert ledger.mark_uncertain(a, item.claim_id, code="timeout") == uncertain
    with pytest.raises(EmployerSubmitClaimDenied, match="reset|relabeled"):
        ledger.mark_uncertain(a, item.claim_id, code="browser_error")
    again, new = reserve()
    assert not new and again.state == "uncertain"
    assert ledger.get(a, key).claim_id == item.claim_id


def test_two_source_keys_for_same_lever_job_share_one_claim(scoped):
    a, b, wa, wb, key, url, fp, letter, ledger, reserve = scoped
    mirror_key = key + "-mirror"
    mirror_url = url + "/apply?source=other-job-board"
    mirror_ws = "workspace-mirror-" + uuid4().hex
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_jobs (
                 canonical_key,job_id,company,role_title,candidate,
                 first_seen_at,last_seen_at,source_current
               ) VALUES (%s,%s,'Test Ltd','Engineer',%s,now(),now(),true)""",
            (mirror_key, mirror_key, Jsonb({
                "description_fingerprint": fp,
                "job": {"application_url": mirror_url},
            })),
        )
        conn.execute(
            """INSERT INTO smartploy_application_workspaces (
                 workspace_id,profile_id,canonical_key,role_title,company,
                 application_url,cv_text,cover_letter_text,job_fingerprint
               ) VALUES (%s,%s,%s,'Engineer','Test Ltd',%s,%s,%s,%s)""",
            (mirror_ws, a.profile_id, mirror_key, mirror_url,
             "Reviewed synthetic resume", letter, fp),
        )
    first, created = reserve()
    assert created
    second, created = ledger.reserve(
        a, workspace_id=mirror_ws, expected_revision=1,
        expected_application_url=mirror_url, expected_job_fingerprint=fp,
        explicit_final_user_approval=True, employer_submission_permitted=True,
    )
    assert not created and first.claim_id == second.claim_id
    assert first.employer_job_key_sha256 == second.employer_job_key_sha256
    assert ledger.get(a, mirror_key) is None  # original stored source key differs
    assert ledger.get_for_employer_url(a, mirror_url).claim_id == first.claim_id
    assert ledger.get_for_employer_url(b, mirror_url) is None


def test_quarantine_blocks_new_claim_and_inventories_existing_marker(scoped):
    a, b, _, _, key, _, _, _, ledger, reserve = scoped
    claim, new = reserve()
    assert new
    erasure = PostgresAccountErasureRepository(DSN)
    status = erasure.quarantine(a.user_id, a.profile_id)
    assert status.status == "quarantined"
    inventory = inspect_quarantined_account(DSN, a.user_id, a.profile_id)
    assert inventory.counts["employer_submit_claims"] == 1
    assert inventory.unknown_owner_tables == ()
    with pytest.raises(EmployerSubmitClaimDenied, match="disabled|binding"):
        reserve()
    assert ledger.get(a, key).claim_id == claim.claim_id
    assert ledger.get(b, key) is None


def test_signed_in_api_status_is_account_scoped_and_never_submission_authority(scoped, monkeypatch):
    """Real PostgreSQL claim lookup under two different OIDC sessions."""
    a, b, wa, wb, key, _, _, _, ledger, reserve = scoped
    nonce = key.removeprefix("employer-job-")
    origin = "https://smartploy.obumai.com"
    issuer = "https://sso.example.invalid"
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", origin)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", issuer)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", origin + "/auth/callback")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", origin + "/auth/logged-out"
    )
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", DSN)
    sessions = MemorySessionRepository()
    tokens = {}
    for binding, label in ((a, "a"), (b, "b")):
        principal = AuthenticatedPrincipal(
            issuer=issuer, subject="claim-" + label + "-" + nonce,
            email="same@example.invalid", auth_source="oidc",
        )
        tokens[label] = sessions.create(
            user_id=binding.user_id, principal=principal,
            provider_session_id="fixture-" + label, ttl_seconds=3600,
        ).token
    api = TestClient(create_app(
        SmartployService(), identity_repository=PostgresIdentityRepository(DSN),
        session_repository=sessions, oidc_client=object(),
    ), base_url=origin)
    a_path = f"/api/v1/application-workspaces/{wa}/employer-attempt"
    b_path = f"/api/v1/application-workspaces/{wb}/employer-attempt"

    api.cookies.set(SESSION_COOKIE_NAME, tokens["a"])
    before = api.get(a_path)
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "not_reserved"
    assert before.json()["previous_attempt_reserved"] is False
    claim, created = reserve()
    assert created
    after = api.get(a_path)
    assert after.status_code == 200, after.text
    result = after.json()
    assert result["state"] == "reserved_unverified"
    assert result["previous_attempt_reserved"] is True
    assert result["requires_human_reconciliation"] is True
    assert result["automatic_employer_submit_authorized"] is False
    assert result["external_confirmation_verified"] is False
    assert result["cross_device_server_claim_required"] is True
    assert "no-store" in after.headers["cache-control"]
    assert claim.claim_id not in after.text
    assert a.user_id not in after.text
    assert "https://jobs.lever.co" not in after.text

    api.cookies.set(SESSION_COOKIE_NAME, tokens["b"])
    assert api.get(a_path).status_code == 404
    other = api.get(b_path)
    assert other.status_code == 200
    assert other.json()["previous_attempt_reserved"] is False


def test_review_intent_shared_existing_preflight_and_owner_scope(scoped):
    a, b, wa, wb, key, url, fingerprint, letter, _, _ = scoped
    intent_repo = PostgresEmployerReviewIntentRepository(DSN)
    digest = sha256((
        "Reviewed synthetic resume with sufficient content" + "\0" + letter
    ).encode()).hexdigest()

    def prepare(binding=a, workspace_id=wa, revision=1, doc=digest, pdf="e" * 64,
                approved=True, manual=True):
        return PostgresEmployerReviewIntentRepository(DSN).prepare(
            binding, workspace_id=workspace_id, expected_revision=revision,
            expected_application_url=url, expected_job_fingerprint=fingerprint,
            expected_document_sha256=doc, expected_cv_pdf_sha256=pdf,
            explicit_user_review=approved, acknowledge_no_automatic_submit=manual,
        )

    with pytest.raises(EmployerReviewIntentDenied, match="acknowledgements"):
        prepare(approved=False)
    with pytest.raises(EmployerReviewIntentDenied, match="acknowledgements"):
        prepare(manual=False)
    with pytest.raises(EmployerReviewIntentDenied, match="digest"):
        prepare(doc="f" * 64)
    with pytest.raises(EmployerReviewIntentDenied, match="workspace"):
        prepare(binding=b, workspace_id=wa)
    assert intent_repo.get(a, url) is None
    assert intent_repo.get(b, url) is None

    first, inserted = prepare()
    assert inserted
    assert first.state == "pending"
    assert first.document_sha256 == digest
    assert first.cv_pdf_sha256 == "e" * 64
    status = first.public_status(workspace_id=wa, revision=1)
    assert status["review_recorded"] is True
    assert status["automatic_employer_submit_authorized"] is False
    assert status["browser_grant_issued"] is False
    assert status["external_actions_performed"] is False
    assert "usr-" not in str(status) and url not in str(status)
    assert intent_repo.get(b, url) is None
    second, created = prepare()
    assert not created and second.intent_id == first.intent_id
    assert second.created_at == first.created_at

    with ThreadPoolExecutor(max_workers=8) as pool:
        raced = list(pool.map(lambda _: prepare(), range(8)))
    assert sum(int(created) for _, created in raced) == 0
    assert len({intent.intent_id for intent, _ in raced}) == 1

    another, created = prepare(binding=b, workspace_id=wb)
    assert created
    assert another.user_id == b.user_id
    assert intent_repo.get(a, url).intent_id == first.intent_id
    assert intent_repo.get(b, url).intent_id == another.intent_id


def test_review_cancellation_reapproval_and_revision_drift(scoped):
    a, _, wa, _, _, url, fp, letter, _, _ = scoped
    repo = PostgresEmployerReviewIntentRepository(DSN)
    original = sha256(("Reviewed synthetic resume with sufficient content" + "\0" + letter).encode()).hexdigest()

    def prep(rev=1, doc=original):
        return repo.prepare(
            a, workspace_id=wa, expected_revision=rev,
            expected_application_url=url, expected_job_fingerprint=fp,
            expected_document_sha256=doc, expected_cv_pdf_sha256="a"*64,
            explicit_user_review=True, acknowledge_no_automatic_submit=True,
        )

    old, created = prep()
    assert created
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_application_workspaces
               SET revision=2, cv_text='Updated reviewed CV'
               WHERE workspace_id=%s""", (wa,),
        )
    with pytest.raises(EmployerReviewIntentDenied, match="changed"):
        prep()
    new_digest = sha256(("Updated reviewed CV" + "\0" + letter).encode()).hexdigest()
    with pytest.raises(EmployerReviewIntentDenied, match="different review"):
        prep(rev=2, doc=new_digest)
    assert repo.get(a, url).public_status(workspace_id=wa, revision=2)["review_recorded"] is False
    cancelled = repo.cancel(a, application_url=url)
    assert cancelled.state == "cancelled"
    renewed, inserted = prep(rev=2, doc=new_digest)
    assert inserted and renewed.intent_id != old.intent_id
    assert repo.get(a, url).public_status(workspace_id=wa, revision=2)["review_recorded"] is True


def test_review_intent_rejects_existing_employer_submit_claim_and_disabled_account(scoped):
    a, _, wa, _, key, url, fp, letter, _, reserve = scoped
    repo = PostgresEmployerReviewIntentRepository(DSN)
    digest = sha256(("Reviewed synthetic resume with sufficient content"+"\0"+letter).encode()).hexdigest()
    claim, created = reserve()
    assert created
    with pytest.raises(EmployerReviewIntentDenied, match="reconciliation"):
        repo.prepare(
            a, workspace_id=wa, expected_revision=1,
            expected_application_url=url, expected_job_fingerprint=fp,
            expected_document_sha256=digest, expected_cv_pdf_sha256="a"*64,
            explicit_user_review=True, acknowledge_no_automatic_submit=True,
        )
    assert repo.get(a, url) is None
    PostgresAccountErasureRepository(DSN).quarantine(a.user_id, a.profile_id)
    with pytest.raises(EmployerReviewIntentDenied, match="disabled|binding"):
        repo.prepare(
            a, workspace_id=wa, expected_revision=1,
            expected_application_url=url, expected_job_fingerprint=fp,
            expected_document_sha256=digest, expected_cv_pdf_sha256="a"*64,
            explicit_user_review=True, acknowledge_no_automatic_submit=True,
        )


def test_review_intent_included_in_erasure_inventory(scoped):
    a, _, wa, _, _, url, fp, letter, _, _ = scoped
    repo = PostgresEmployerReviewIntentRepository(DSN)
    digest = sha256(("Reviewed synthetic resume with sufficient content"+"\0"+letter).encode()).hexdigest()
    repo.prepare(
        a, workspace_id=wa, expected_revision=1,
        expected_application_url=url, expected_job_fingerprint=fp,
        expected_document_sha256=digest, expected_cv_pdf_sha256="a"*64,
        explicit_user_review=True, acknowledge_no_automatic_submit=True,
    )
    PostgresAccountErasureRepository(DSN).quarantine(a.user_id, a.profile_id)
    inventory = inspect_quarantined_account(DSN, a.user_id, a.profile_id)
    assert inventory.counts["employer_review_intents"] == 1
    assert inventory.unknown_owner_tables == ()


def test_intent_state_does_not_depend_on_cv_text_or_version_in_public_projection(scoped):
    a, _, wa, _, _, url, fp, letter, _, _ = scoped
    repo = PostgresEmployerReviewIntentRepository(DSN)
    digest = sha256(("Reviewed synthetic resume with sufficient content"+"\0"+letter).encode()).hexdigest()
    record, _ = repo.prepare(
        a, workspace_id=wa, expected_revision=1,
        expected_application_url=url, expected_job_fingerprint=fp,
        expected_document_sha256=digest, expected_cv_pdf_sha256="a"*64,
        explicit_user_review=True, acknowledge_no_automatic_submit=True,
    )
    for rev in (1,2,20):
        status=record.public_status(workspace_id=wa,revision=rev)
        assert status["browser_grant_issued"] is False
        assert status["automatic_employer_submit_authorized"] is False
        assert "intent_id" not in status and "document_sha256" not in status
    assert record.public_status(workspace_id=wa,revision=2)["review_recorded"] is False


def test_signed_in_review_http_to_postgres_end_to_end(scoped, monkeypatch):
    """Actual FastAPI + two OIDC users + deterministic reviewed PDF + PostgreSQL."""
    a, b, _, _, scoped_key, _, _, _, _, _ = scoped
    original_nonce = scoped_key.removeprefix("employer-job-")
    job_nonce = uuid4().hex
    origin = "https://smartploy.obumai.com"
    url = f"https://jobs.lever.co/otherorg/{job_nonce}/apply"
    outcome = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url=url, raw_text="Synthetic SQL analytics applicant role",
            payload={
                "role_title":"Junior Analytics Engineer",
                "company":"Synthetic Employer", "description":"SQL analytics",
                "application_url":url, "location":"Helsinki",
            },
            observed_at="2026-10-18T10:00:00+00:00",
        ), SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    )
    assert outcome.candidate is not None
    job = outcome.candidate
    jobs = PostgresJobRepository(DSN)
    profiles = PostgresProfileRepository(DSN, profile_id=a.profile_id)
    workspaces = PostgresWorkspaceRepository(DSN)
    for kind, value in (
        ("identity", "Applicant Synthetic"),
        ("email", "review@example.invalid"),
        ("skill", "Synthetic SQL"),
    ):
        profiles.upsert_fact(ProfileFact(kind, value, "user-entered", approved=True))
    work = None
    try:
        jobs.upsert(job)
        work = new_workspace(
            job, profiles.profile(),
            source_cv_text="Applicant Synthetic\n\nSynthetic SQL experience",
        )
        work = replace(work, cover_letter_text=(
            "Dear hiring team, I am applying for this synthetic analytics job. "
            "My reviewed SQL skills relate to the advertised requirements. "
            "Regards, Applicant Synthetic."
        ))
        assert workspaces.create_or_get(work)[1]
        packet = make_browser_packet(work, job, profiles.profile())

        monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
        monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
        monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", origin)
        monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
        monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", "https://sso.example.invalid")
        monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "fixture")
        monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", origin + "/auth/callback")
        monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", origin + "/auth/logged-out")
        monkeypatch.setenv("SMARTPLOY_DATABASE_URL", DSN)
        sessions = MemorySessionRepository()
        tokens = {}
        for binding, label in ((a, "a"), (b, "b")):
            principal = AuthenticatedPrincipal(
                issuer="https://sso.example.invalid",
                subject=f"claim-{label}-{original_nonce}",
                email="same@example.invalid", auth_source="oidc",
            )
            tokens[label] = sessions.create(
                user_id=binding.user_id, principal=principal,
                provider_session_id="synthetic-" + label, ttl_seconds=3600,
            ).token
        app = create_app(
            identity_repository=PostgresIdentityRepository(DSN),
            session_repository=sessions, oidc_client=object(),
        )
        api = TestClient(app, base_url=origin)
        api.cookies.set(SESSION_COOKIE_NAME, tokens["a"])
        route = f"/api/v1/application-workspaces/{work.workspace_id}/submit-review-intent"
        body = {
            "expected_revision":work.revision,
            "expected_document_sha256":packet["document_sha256"],
            "expected_cv_pdf_sha256":packet["cv_pdf_sha256"],
            "confirm_reviewed_application":True,
            "acknowledge_manual_only":True,
        }
        headers = {
            "Origin":origin, "Sec-Fetch-Site":"same-origin",
            "X-Smartploy-Expected-User-Id":a.user_id,
        }
        verify_route = route.replace("/submit-review-intent", "/verify-reviewed-packet")
        posture_route = route.replace("/submit-review-intent", "/final-action-readiness")
        baseline_posture = api.get(posture_route)
        assert baseline_posture.status_code == 200, baseline_posture.text
        assert baseline_posture.json()["operator_permission_reviewed"] is False
        assert baseline_posture.json()["trusted_one_use_browser_redemption_available"] is False
        assert baseline_posture.json()["final_browser_click_authorized"] is False
        assert "independent_employer_permission_missing" in baseline_posture.json()["blockers"]
        assert api.post(posture_route, json={}).status_code == 403
        assert api.post(posture_route, json={}, headers=headers).status_code == 405
        verification_body = {
            "expected_revision":work.revision,
            "expected_document_sha256":packet["document_sha256"],
            "expected_cv_pdf_sha256":packet["cv_pdf_sha256"],
            "expected_fields_sha256":approved_fields_sha256(packet["fields"]),
            "expected_application_url_sha256":
                sha256(packet["application_url"].encode("utf-8")).hexdigest(),
            "expected_cv_pdf_size":packet["cv_pdf_size"],
        }
        before_approval=api.post(verify_route,json=verification_body,headers=headers)
        assert before_approval.status_code==409
        first_read = api.get(route)
        assert first_read.status_code == 200, first_read.text
        assert first_read.json()["review_state"] == "not_recorded"
        accepted = api.post(route, json=body, headers=headers)
        assert accepted.status_code == 200, accepted.text
        reviewed_posture=api.get(posture_route)
        assert reviewed_posture.status_code==200
        assert reviewed_posture.json()["current_applicant_review_recorded"] is True
        assert reviewed_posture.json()["final_browser_click_authorized"] is False
        assert accepted.json()["review_recorded"] is True
        assert accepted.json()["new_review_recorded"] is True
        assert accepted.json()["automatic_employer_submit_authorized"] is False
        assert accepted.json()["browser_grant_issued"] is False
        verified = api.post(verify_route,json=verification_body,headers=headers)
        assert verified.status_code==200,verified.text
        assert verified.json()["review_verified"] is True
        assert verified.json()["automatic_employer_submit_authorized"] is False
        assert verified.json()["browser_grant_issued"] is False
        assert verified.json()["external_actions_performed"] is False
        assert "user_id" not in verified.text
        assert "cv_pdf_sha256" not in verified.text
        assert url not in verified.text
        assert "no-store" in verified.headers["cache-control"]
        for forged_patch in (
            {"expected_cv_pdf_sha256":"f"*64},
            {"expected_fields_sha256":"f"*64},
            {"expected_application_url_sha256":"e"*64},
            {"expected_cv_pdf_size":packet["cv_pdf_size"]+1},
        ):
            forged=api.post(
                verify_route,json={**verification_body,**forged_patch},headers=headers
            )
            assert forged.status_code==409, (forged_patch,forged.text)
        repeated = api.post(route, json=body, headers=headers)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["new_review_recorded"] is False
        assert "no-store" in api.get(route).headers["cache-control"]
        api.cookies.set(SESSION_COOKIE_NAME, tokens["b"])
        assert api.get(route).status_code == 404
        assert api.get(posture_route).status_code == 404
        other_write = api.post(route, json=body, headers=headers)
        assert other_write.status_code == 409
        assert api.post(verify_route,json=verification_body,headers=headers).status_code==409
        own_headers={**headers,"X-Smartploy-Expected-User-Id":b.user_id}
        assert api.post(verify_route,json=verification_body,headers=own_headers).status_code==404
        api.cookies.set(SESSION_COOKIE_NAME, tokens["a"])
        cancellation = api.delete(route, headers=headers)
        assert cancellation.status_code == 200, cancellation.text
        assert cancellation.json()["review_recorded"] is False
        assert api.get(route).json()["review_state"] == "cancelled"
        assert api.post(verify_route,json=verification_body,headers=headers).status_code==409
    finally:
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_employer_review_intents WHERE user_id=%s",
                (a.user_id,),
            )
        if work is not None:
            workspaces.delete(a.profile_id, work.workspace_id)
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_profile_facts WHERE profile_id=%s",
                (a.profile_id,),
            )
            conn.execute("DELETE FROM smartploy_jobs WHERE canonical_key=%s", (job.canonical_key,))


def test_review_companion_verification_reuses_owner_job_document_and_intent_locks(scoped):
    a, b, wa, wb, key, url, fp, letter, ledger, reserve = scoped
    repo = PostgresEmployerReviewIntentRepository(DSN)
    digest=sha256(("Reviewed synthetic resume with sufficient content"+"\0"+letter).encode()).hexdigest()
    args=dict(
        workspace_id=wa,expected_revision=1,expected_application_url=url,
        expected_job_fingerprint=fp,expected_document_sha256=digest,
        expected_cv_pdf_sha256="f"*64,
    )
    with pytest.raises(EmployerReviewIntentDenied,match="signed-in review"):
        repo.verify_for_companion(a,**args)
    prepared,new=repo.prepare(a,**args,explicit_user_review=True,
        acknowledge_no_automatic_submit=True)
    assert new
    verified=repo.verify_for_companion(a,**args)
    assert verified.intent_id==prepared.intent_id
    assert verified.state=="pending"
    assert verified.public_status(workspace_id=wa,revision=1)["browser_grant_issued"] is False
    with pytest.raises(EmployerReviewIntentDenied,match="workspace"):
        repo.verify_for_companion(b,**args)
    with pytest.raises(EmployerReviewIntentDenied,match="inconsistent"):
        repo.verify_for_companion(a,**{**args,"expected_cv_pdf_sha256":"a"*64})
    repo.cancel(a,application_url=url)
    with pytest.raises(EmployerReviewIntentDenied,match="cancelled"):
        repo.verify_for_companion(a,**args)


def test_review_verification_expiry_and_prior_claim_block_fail_closed(scoped):
    a, _, wa, _, key, url, fp, letter, ledger, reserve = scoped
    repo=PostgresEmployerReviewIntentRepository(DSN)
    digest=sha256(("Reviewed synthetic resume with sufficient content"+"\0"+letter).encode()).hexdigest()
    args=dict(
        workspace_id=wa,expected_revision=1,expected_application_url=url,
        expected_job_fingerprint=fp,expected_document_sha256=digest,
        expected_cv_pdf_sha256="e"*64,
    )
    prepared,_=repo.prepare(a,**args,explicit_user_review=True,
        acknowledge_no_automatic_submit=True)
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_employer_review_intents
               SET created_at=now()-interval '2 hours',
                   expires_at=now()-interval '1 hour'
               WHERE intent_id=%s""",(prepared.intent_id,),
        )
    with pytest.raises(EmployerReviewIntentDenied,match="expired"):
        repo.verify_for_companion(a,**args)
    newer,created=repo.prepare(a,**args,explicit_user_review=True,
        acknowledge_no_automatic_submit=True)
    assert created and newer.intent_id!=prepared.intent_id
    claim,inserted=reserve()
    assert inserted
    with pytest.raises(EmployerReviewIntentDenied,match="reconciliation"):
        repo.verify_for_companion(a,**args)



def final_fixture(scoped, *, who="a", rights=True):
    """Synthetic real PostgreSQL first-party reuse, never provider traffic."""
    a,b,wa,wb,key,url,fp,letter,_,_=scoped
    binding,workspace=(a,wa) if who=="a" else (b,wb)
    store=PostgresProfileRepository(DSN,profile_id=binding.profile_id)
    for kind,value in (
        ("identity","Synthetic Applicant"),
        ("email","same@example.invalid"),
    ):
        store.upsert_fact(ProfileFact(kind,value,"user-entered",approved=True))
    cv="Reviewed synthetic resume with sufficient content"
    digest=sha256((cv+"\0"+letter).encode()).hexdigest()
    pdf="d"*64
    contact={
        "full_name":"Synthetic Applicant","first_name":"Synthetic",
        "last_name":"Applicant","email":"same@example.invalid",
        "phone":"","location":"","linkedin":"","github":"",
        "cover_letter":letter[:10000],
    }
    field_digest=approved_fields_sha256(contact)
    intent_repo=PostgresEmployerReviewIntentRepository(DSN)
    intent,_=intent_repo.prepare(
        binding,workspace_id=workspace,expected_revision=1,
        expected_application_url=url,expected_job_fingerprint=fp,
        expected_document_sha256=digest,expected_cv_pdf_sha256=pdf,
        explicit_user_review=True,acknowledge_no_automatic_submit=True,
    )
    employer_hash=employer_job_key(url)
    if rights:
        with connect(DSN) as conn:
            conn.execute(
                """INSERT INTO smartploy_employer_automation_rights (
                     employer_job_key_sha256, permission_basis,
                     permission_evidence_sha256,terms_evidence_sha256,
                     reviewed_by,independently_approved_by,
                     reviewed_at,expires_at,state
                   ) VALUES (
                     %s,'explicit_employer_authorization',%s,%s,
                     'auditor-A-123','auditor-B-456',
                     now()-interval '1 day',now()+interval '1 day','approved'
                   ) ON CONFLICT (employer_job_key_sha256) DO NOTHING""",
                (employer_hash,"e"*64,"f"*64),
            )
    return binding,dict(
        workspace_id=workspace,expected_revision=1,
        expected_application_url=url,expected_job_fingerprint=fp,
        expected_document_sha256=digest,expected_cv_pdf_sha256=pdf,
        expected_fields_sha256=field_digest,
    )


def test_employer_final_gate_denies_missing_rights_even_for_approved_source(scoped):
    a,args=final_fixture(scoped,rights=False)
    gate=PostgresEmployerFinalActionGate(DSN)
    read=PostgresEmployerAutomationRightsRepository(DSN).inspect(
        args["expected_application_url"]
    )
    assert read["operator_permission_reviewed"] is False
    assert read["final_browser_click_authorized"] is False
    with pytest.raises(EmployerFinalActionDenied,match="permission"):
        gate.approve(
            a,**args,explicit_final_user_approval=True,
            acknowledge_external_employer_transfer=True,
        )
    assert gate.get(a,args["expected_application_url"]) is None
    assert PostgresEmployerSubmitClaimRepository(DSN).get(
        a,scoped[4]
    ) is None


def test_only_two_independent_current_permission_reviewers_can_gate_approval(scoped):
    a,args=final_fixture(scoped)
    url=args["expected_application_url"]
    gate=PostgresEmployerFinalActionGate(DSN)
    posture=PostgresEmployerAutomationRightsRepository(DSN).inspect(url)
    assert posture["operator_permission_reviewed"] is True
    assert posture["permission_basis"]=="explicit_employer_authorization"
    assert posture["final_browser_click_authorized"] is False
    with connect(DSN) as conn:
        with pytest.raises(Exception):
            conn.execute(
                """UPDATE smartploy_employer_automation_rights
                   SET independently_approved_by=reviewed_by
                   WHERE employer_job_key_sha256=%s""",
                (employer_job_key(url),),
            )
    with pytest.raises(EmployerFinalActionDenied,match="Fresh"):
        gate.approve(a,**args,explicit_final_user_approval=False,
            acknowledge_external_employer_transfer=True)
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_employer_automation_rights
               SET state='revoked'
               WHERE employer_job_key_sha256=%s""",
            (employer_job_key(url),),
        )
    with pytest.raises(EmployerFinalActionDenied,match="permission"):
        gate.approve(a,**args,explicit_final_user_approval=True,
            acknowledge_external_employer_transfer=True)
    assert gate.get(a,url) is None


def test_final_approval_requires_reviewed_exact_fields_and_is_nonbearer(scoped):
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    with pytest.raises(EmployerFinalActionDenied,match="contact"):
        gate.approve(a,**{**args,"expected_fields_sha256":"a"*64},
            explicit_final_user_approval=True,
            acknowledge_external_employer_transfer=True)
    first,created=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    assert created and first.state=="approved"
    assert first.expires_at>first.created_at
    status=first.public_status(workspace_id=args["workspace_id"],revision=1)
    assert status["approval_recorded"] is True
    assert status["final_browser_click_authorized"] is False
    assert status["employer_submission_performed"] is False
    assert status["employer_receipt_verified"] is False
    for secret in (a.user_id,a.profile_id,first.approval_id,
                   first.document_sha256,args["expected_application_url"]):
        assert secret not in str(status)
    again,created=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    assert not created and again.approval_id==first.approval_id
    assert gate.get(scoped[1],args["expected_application_url"]) is None


def test_final_approval_cancel_revoke_and_expiration_prevent_consumption(scoped):
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    approved,_=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    gate.cancel(a,args["expected_application_url"])
    with pytest.raises(EmployerFinalActionDenied,match="expired|revoked|consumed"):
        gate.consume_once_for_trusted_adapter(
            a,approval_id=approved.approval_id,**args)
    revived,created=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    assert created and revived.approval_id!=approved.approval_id
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_employer_final_approvals
               SET created_at=now()-interval '2 hours',
                   expires_at=now()-interval '1 hour'
               WHERE approval_id=%s""",
            (revived.approval_id,),
        )
    with pytest.raises(EmployerFinalActionDenied,match="expired|revoked|consumed"):
        gate.consume_once_for_trusted_adapter(
            a,approval_id=revived.approval_id,**args)
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a,scoped[4]) is None


def test_two_device_concurrent_one_shot_claim_uses_original_sp15a_insert(scoped):
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    approval,_=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    def submit():
        try:
            result=PostgresEmployerFinalActionGate(DSN).consume_once_for_trusted_adapter(
                a,approval_id=approval.approval_id,**args)
            return result
        except EmployerFinalActionDenied:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(lambda _:submit(),range(8)))
    successes=[x for x in outcomes if x is not None]
    assert len(successes)==1
    winner=successes[0]
    assert winner.claim.state=="reserved_unverified"
    assert winner.claim.employer_job_key_sha256==employer_job_key(
        args["expected_application_url"]
    )
    assert winner.public_status()["automatic_retry_authorized"] is False
    assert winner.public_status()["final_browser_click_authorized"] is False
    assert winner.public_status()["employer_submission_verified"] is False
    with pytest.raises(EmployerFinalActionDenied,match="consumed|expired|revoked"):
        gate.consume_once_for_trusted_adapter(
            a,approval_id=approval.approval_id,**args)
    current=gate.get(a,args["expected_application_url"])
    assert current.state=="consumed_unverified"
    assert current.approval_id==approval.approval_id
    persisted=PostgresEmployerSubmitClaimRepository(DSN).get(a,scoped[4])
    assert persisted.claim_id==winner.claim.claim_id
    assert persisted.document_sha256==args["expected_document_sha256"]


def test_rights_revoked_after_final_approval_blocks_claim_before_consume(scoped):
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    approval,_=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_employer_automation_rights SET state='revoked'
               WHERE employer_job_key_sha256=%s""",
            (employer_job_key(args["expected_application_url"]),),
        )
    with pytest.raises(EmployerFinalActionDenied,match="permission"):
        gate.consume_once_for_trusted_adapter(a,approval_id=approval.approval_id,**args)
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a,scoped[4]) is None
    assert gate.get(a,args["expected_application_url"]).state=="approved"


def test_approved_contact_change_after_final_approval_fails_before_claim(scoped):
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    approval,_=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_profile_facts SET approved=false
               WHERE profile_id=%s AND fact_type='email'""",(a.profile_id,),
        )
    with pytest.raises(EmployerFinalActionDenied,match="name and email"):
        gate.consume_once_for_trusted_adapter(a,approval_id=approval.approval_id,**args)
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a,scoped[4]) is None


def test_final_approval_inventory_is_account_scoped_after_quarantine(scoped):
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    _,created=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    assert created
    PostgresAccountErasureRepository(DSN).quarantine(a.user_id,a.profile_id)
    inspection=inspect_quarantined_account(DSN,a.user_id,a.profile_id)
    assert inspection.counts["employer_final_approvals"]==1
    assert inspection.unknown_owner_tables==()
    with pytest.raises(EmployerFinalActionDenied,match="disabled|binding"):
        gate.consume_once_for_trusted_adapter(
            a,approval_id=gate.get(a,args["expected_application_url"]).approval_id,
            **args,
        )



def test_final_approval_claim_insertion_crash_rolls_back_both_records(scoped,monkeypatch):
    """No ghost employer action claim if persistence fails BEFORE commit."""
    import smartploy.employer_final_action_gate as action_gate_module

    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    approval,_=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    original=action_gate_module.reserve_employer_claim_locked

    def synthetic_crash_after_insert(*call_args,**kw):
        result=original(*call_args,**kw)
        assert result[1]
        raise RuntimeError("synthetic_crash_before_transaction_commit")

    with monkeypatch.context() as local:
        local.setattr(
            action_gate_module,"reserve_employer_claim_locked",synthetic_crash_after_insert
        )
        with pytest.raises(RuntimeError,match="synthetic_crash"):
            gate.consume_once_for_trusted_adapter(
                a,approval_id=approval.approval_id,**args
            )
    # On an exception the original PostgreSQL transaction is rolled back
    # atomically, so the approval remains usable. No external click occurred.
    assert gate.get(a,args["expected_application_url"]).state=="approved"
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a,scoped[4]) is None
    completed=gate.consume_once_for_trusted_adapter(
        a,approval_id=approval.approval_id,**args
    )
    assert completed.claim.state=="reserved_unverified"
    assert gate.get(a,args["expected_application_url"]).state=="consumed_unverified"


def test_employer_rights_expire_after_final_user_approval_before_consume(scoped):
    """Source acquisition permission cannot substitute for expired automation rights."""
    a,args=final_fixture(scoped)
    gate=PostgresEmployerFinalActionGate(DSN)
    approval,_=gate.approve(a,**args,explicit_final_user_approval=True,
        acknowledge_external_employer_transfer=True)
    with connect(DSN) as conn:
        conn.execute(
            """UPDATE smartploy_employer_automation_rights
               SET expires_at=now()-interval '1 minute'
               WHERE employer_job_key_sha256=%s""",
            (employer_job_key(args["expected_application_url"]),),
        )
    assert not PostgresEmployerAutomationRightsRepository(DSN).inspect(
        args["expected_application_url"]
    )["operator_permission_reviewed"]
    with pytest.raises(EmployerFinalActionDenied,match="permission"):
        gate.consume_once_for_trusted_adapter(a,approval_id=approval.approval_id,**args)
    assert PostgresEmployerSubmitClaimRepository(DSN).get(a,scoped[4]) is None



@pytest.fixture
def signed_in_partner_workflow(scoped, monkeypatch):
    """Reuse real SmartPloy job normalization, OIDC identities, CV PDF and SQL."""
    a,b,_,_,source_key,_,_,_,_,_=scoped
    nonce=uuid4().hex
    site="syntheticpartner"
    origin="https://smartploy.obumai.com"
    url=f"https://jobs.lever.co/{site}/{nonce}/apply"
    seen=normalize_observation(
        SourceObservation(
            source_id="manual-import",source_mode="manual",source_url=url,
            raw_text="Synthetic junior data analyst",
            payload={
                "role_title":"Junior Data Analyst","company":"Synthetic Partner",
                "description":"SQL data quality and business analytics",
                "application_url":url,"location":"Helsinki",
            },
            observed_at="2026-10-18T15:00:00+00:00",
        ),
        SourcePolicy("manual-import","Manual","manual",("manual",)),
    )
    assert seen.candidate
    job=seen.candidate
    jobs=PostgresJobRepository(DSN)
    profiles=PostgresProfileRepository(DSN,profile_id=a.profile_id)
    workspaces=PostgresWorkspaceRepository(DSN)
    for kind,val in (("identity","Synthetic Applicant"),("email","same@example.invalid"),
                     ("skill","Synthetic SQL")):
        profiles.upsert_fact(ProfileFact(kind,val,"user-entered",approved=True))
    jobs.upsert(job)
    workspace=new_workspace(
        job,profiles.profile(),
        source_cv_text="Synthetic Applicant\n\nSQL quality analytics experience"
    )
    workspace=replace(workspace,cover_letter_text=(
        "Dear hiring manager, I am applying for your synthetic data role. "
        "The reviewed SQL experience supports your advertised requirements. "
        "Kind regards, Synthetic Applicant."
    ))
    assert workspaces.create_or_get(workspace)[1]
    packet=make_browser_packet(workspace,job,profiles.profile())
    key=employer_job_key(url)
    partner_key="SMARTPLOY_LEVER_PARTNER_KEY_SYNTHETIC"
    monkeypatch.setenv("SMARTPLOY_LEVER_PARTNER_JOBS_JSON",json.dumps({
        f"{site}/{nonce}":{
            "region":"global","form_review_sha256":"a"*64,
            "api_key_env":partner_key,"standard_form_only_reviewed":True,
            "consent_policy_reviewed":True,
        }
    }))
    monkeypatch.setenv(partner_key,"synthetic-employer-super-admin-key-1234567890")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT","production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE","oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED","false")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN",origin)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS","smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER","https://sso.example.invalid")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID","fixture")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI",origin+"/auth/callback")
    monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",origin+"/auth/logged-out")
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL",DSN)
    sessions=MemorySessionRepository()
    tokens={}
    original_nonce=source_key.removeprefix("employer-job-")
    for binding,label in ((a,"a"),(b,"b")):
        principal=AuthenticatedPrincipal(
            issuer="https://sso.example.invalid",
            subject=f"claim-{label}-{original_nonce}",
            email="same@example.invalid",auth_source="oidc",
        )
        tokens[label]=sessions.create(
            user_id=binding.user_id,principal=principal,
            provider_session_id="synthetic-"+label,ttl_seconds=3600,
        ).token
    app=create_app(
        identity_repository=PostgresIdentityRepository(DSN),
        session_repository=sessions,oidc_client=object(),
    )
    api=TestClient(app,base_url=origin)
    api.cookies.set(SESSION_COOKIE_NAME,tokens["a"])
    route=f"/api/v1/application-workspaces/{workspace.workspace_id}"
    headers={
        "Origin":origin,"Sec-Fetch-Site":"same-origin",
        "X-Smartploy-Expected-User-Id":a.user_id,
    }
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_employer_automation_rights (
                 employer_job_key_sha256,action_scope,permission_basis,
                 permission_evidence_sha256,terms_evidence_sha256,
                 reviewed_by,independently_approved_by,
                 reviewed_at,expires_at,state
               ) VALUES (
                 %s,'partner_lever_postings_api_submit',
                 'documented_partner_integration',%s,%s,
                 'independent-A','independent-B',
                 now()-interval '1 day',now()+interval '1 day','approved')""",
            (key,"a"*64,"b"*64),
        )
    try:
        yield api,app,route,headers,a,b,packet,url,nonce,tokens,key
    finally:
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_partner_application_receipts WHERE user_id=%s",(a.user_id,)
            )
            conn.execute(
                "DELETE FROM smartploy_employer_final_approvals WHERE user_id=%s",(a.user_id,)
            )
            conn.execute(
                "DELETE FROM smartploy_employer_submit_claims WHERE user_id=%s AND employer_job_key_sha256=%s",
                (a.user_id,key),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_review_intents WHERE user_id=%s AND employer_job_key_sha256=%s",
                (a.user_id,key),
            )
            conn.execute(
                "DELETE FROM smartploy_employer_automation_rights WHERE employer_job_key_sha256=%s",
                (key,),
            )
        workspaces.delete(a.profile_id,workspace.workspace_id)
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_profile_facts WHERE profile_id=%s",(a.profile_id,)
            )
            conn.execute("DELETE FROM smartploy_jobs WHERE canonical_key=%s",(job.canonical_key,))


def _partner_review(api,route,headers,packet):
    doc={
        "expected_revision":packet["revision"],
        "expected_document_sha256":packet["document_sha256"],
        "expected_cv_pdf_sha256":packet["cv_pdf_sha256"],
        "confirm_reviewed_application":True,
        "acknowledge_manual_only":True,
    }
    r=api.post(route+"/submit-review-intent",headers=headers,json=doc)
    assert r.status_code==200,r.text


def _partner_submit_payload(packet):
    return {
        "expected_revision":packet["revision"],
        "expected_document_sha256":packet["document_sha256"],
        "expected_cv_pdf_sha256":packet["cv_pdf_sha256"],
        "expected_fields_sha256":packet["approved_fields_sha256"],
        "expected_cv_pdf_size":packet["cv_pdf_size"],
        "explicit_final_user_approval":True,
        "approve_employer_data_transfer":True,
        "affirm_reviewed_employer_form":True,
    }


def test_partner_lever_real_signed_in_provider_acknowledgment_and_cross_device_once(
    signed_in_partner_workflow
):
    api,app,route,headers,a,b,packet,url,nonce,tokens,key=signed_in_partner_workflow
    sent=[]
    def handler(request):
        sent.append(request.method)
        if request.method=="GET":
            return httpx.Response(200,json={"id":nonce,"applyUrl":url})
        assert request.url.host=="api.lever.co"
        assert request.url.params["key"]=="synthetic-employer-super-admin-key-1234567890"
        assert b"%PDF-1.4" in request.content
        assert b"Synthetic Applicant" in request.content
        assert b"name=\"resume\"" in request.content
        return httpx.Response(200,json={"ok":True,"applicationId":"app-1234567890abcdef"})
    app.state.partner_lever_transport=LeverPartnerTransport(httpx.MockTransport(handler))
    ready=api.get(route+"/partner-lever-readiness")
    assert ready.status_code==200,ready.text
    assert ready.json()["eligible_for_explicit_partner_submit"] is False
    assert ready.json()["current_applicant_review_recorded"] is False
    assert ready.json()["independent_partner_rights_reviewed"] is True
    # The server reuses the existing deterministic PDF/contact/letter
    # packet to produce NON-BEARER hashes; no clipboard, PII, API key or
    # external employer request is involved in reading this posture.
    assert ready.json()["review_evidence"] == {
        "workspace_id":packet["workspace_id"],
        "revision":packet["revision"],
        "document_sha256":packet["document_sha256"],
        "cv_pdf_sha256":packet["cv_pdf_sha256"],
        "approved_fields_sha256":packet["approved_fields_sha256"],
        "cv_pdf_size":packet["cv_pdf_size"],
        "expires_at":ready.json()["review_evidence"]["expires_at"],
    }
    assert ready.json()["review_evidence_is_authorization"] is False
    assert "user@example.invalid" not in ready.text
    assert "same@example.invalid" not in ready.text
    assert "Synthetic Applicant" not in ready.text
    assert "super-admin-key" not in ready.text
    assert "no-store" in ready.headers["cache-control"]
    assert sent == []
    payload=_partner_submit_payload(packet)
    assert api.post(route+"/partner-lever-apply",json=payload,headers=headers).status_code==409
    assert sent==[]
    _partner_review(api,route,headers,packet)
    assert api.get(route+"/partner-lever-readiness").json()["eligible_for_explicit_partner_submit"] is True
    first=api.post(route+"/partner-lever-apply",json=payload,headers=headers)
    assert first.status_code==200,first.text
    assert first.json()["state"]=="provider_acknowledged"
    assert first.json()["provider_application_id"]=="app-1234567890abcdef"
    assert first.json()["external_actions_performed"] is True
    assert first.json()["employer_hiring_decision_verified"] is False
    assert sent==["GET","POST"]
    view=api.get(route+"/partner-lever-receipt")
    assert view.status_code==200 and view.json()["present"]
    assert view.json()["receipt"]["provider_application_id"]=="app-1234567890abcdef"
    after=api.get(route+"/partner-lever-readiness").json()
    assert after["provider_acknowledged"] is True
    assert after["prior_employer_attempt"] is True
    assert after["eligible_for_explicit_partner_submit"] is False
    assert after["review_evidence"] is None
    replay=api.post(route+"/partner-lever-apply",json=payload,headers=headers)
    assert replay.status_code==409
    assert sent==["GET","POST"]
    api.cookies.set(SESSION_COOKIE_NAME,tokens["b"])
    assert api.get(route+"/partner-lever-readiness").status_code==404
    assert api.get(route+"/partner-lever-receipt").status_code==404
    assert api.post(route+"/partner-lever-apply",json=payload,headers=headers).status_code==409
    assert sent==["GET","POST"]
    api.cookies.set(SESSION_COOKIE_NAME,tokens["a"])
    assert PostgresPartnerApplicationReceipts(DSN).get(a,url).application_id=="app-1234567890abcdef"


def test_partner_lever_rate_limit_outcome_sticky_and_no_second_post(signed_in_partner_workflow):
    api,app,route,headers,a,b,packet,url,nonce,tokens,key=signed_in_partner_workflow
    methods=[]
    def handler(request):
        methods.append(request.method)
        if request.method=="GET":
            return httpx.Response(200,json={"id":nonce,"applyUrl":url})
        return httpx.Response(429,json={"ok":False,"error":"rate_limited"})
    app.state.partner_lever_transport=LeverPartnerTransport(httpx.MockTransport(handler))
    _partner_review(api,route,headers,packet)
    payload=_partner_submit_payload(packet)
    result=api.post(route+"/partner-lever-apply",json=payload,headers=headers)
    assert result.status_code==202,result.text
    assert result.json()["state"]=="outcome_uncertain"
    assert result.json()["automatic_retry_authorized"] is False
    assert PostgresEmployerSubmitClaimRepository(DSN).get_for_employer_url(a,url).state=="uncertain"
    assert api.get(route+"/partner-lever-receipt").json()["present"] is False
    assert api.post(route+"/partner-lever-apply",json=payload,headers=headers).status_code==409
    assert methods==["GET","POST"]


def test_partner_lever_revoked_permission_and_invalid_consent_cannot_call_api(signed_in_partner_workflow):
    api,app,route,headers,a,b,packet,url,nonce,tokens,key=signed_in_partner_workflow
    requests=[]
    app.state.partner_lever_transport=LeverPartnerTransport(
        httpx.MockTransport(lambda req: requests.append(req) or httpx.Response(200,json={"ok":True}))
    )
    _partner_review(api,route,headers,packet)
    payload=_partner_submit_payload(packet)
    assert api.post(route+"/partner-lever-apply",json={
        **payload,"approve_employer_data_transfer":False,
    },headers=headers).status_code==422
    assert api.post(route+"/partner-lever-apply",json=payload,
        headers={**headers,"Origin":"https://evil.invalid"}).status_code==403
    with connect(DSN) as conn:
        conn.execute("UPDATE smartploy_employer_automation_rights SET state='revoked' WHERE employer_job_key_sha256=%s",
            (key,))
    restricted=api.get(route+"/partner-lever-readiness").json()
    assert restricted["eligible_for_explicit_partner_submit"] is False
    assert restricted["review_evidence"] is None
    assert api.post(route+"/partner-lever-apply",json=payload,headers=headers).status_code==409
    assert requests==[]
    assert PostgresEmployerSubmitClaimRepository(DSN).get_for_employer_url(a,url) is None

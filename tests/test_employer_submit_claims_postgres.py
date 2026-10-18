"""SP15a real PostgreSQL race/ownership/erasure tests. Synthetic only.

No browser or employer requests are sent by these tests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
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

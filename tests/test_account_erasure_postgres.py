"""Verified-account quarantine: atomic denial, no data-false-deletion claims.

These are isolated PostgreSQL tests with synthetic identities and fake
ObumAI remote references. NO external network or employer requests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from threading import Event
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.types.json import Jsonb

from smartploy.application_agents import PostgresApplicationAgentRepository
from smartploy.account_erasure import (
    ErasureIdentityMismatch, PostgresAccountErasureRepository,
    inspect_quarantined_account,
)
from smartploy.ai_processing_consent import (
    ConsentDispatchDenied, ConsentIdentityError, PostgresJobAIConsentRepository,
)
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.domain import canonical_json
from smartploy.obumai_dispatch_storage import PostgresDraftDispatchRepository
from smartploy.preparation_storage import PostgresPreparationRepository, with_runtime
from smartploy.preparations import ApplicationPreparation, PREPARATION_CONTRACT
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


def _sha(v):
    return sha256(canonical_json(v).encode()).hexdigest()


@pytest.fixture
def scoped():
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    ids = PostgresIdentityRepository(DSN)
    issuer = "https://sso.example.invalid"
    subject_a = "erasure-a-" + nonce
    subject_b = "erasure-b-" + nonce
    a = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer=issuer, subject=subject_a, email="sensitive@example.invalid",
        auth_source="oidc",
    ))
    b = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer=issuer, subject=subject_b, email="same@example.invalid",
        auth_source="oidc",
    ))
    consent = PostgresJobAIConsentRepository(DSN)
    key_a, key_b = "job-" + nonce + "-a", "job-" + nonce + "-b"
    jobhash, evidencehash = "a" * 64, "b" * 64
    ga, _ = consent.grant(a, key_a, jobhash, evidencehash)
    gb, _ = consent.grant(b, key_b, jobhash, evidencehash)
    session_sha_a, session_sha_b = "session-a-" + nonce, "session-b-" + nonce
    with connect(DSN) as conn:
        for user, session_hash, subject in (
            (a, session_sha_a, subject_a),
            (b, session_sha_b, subject_b),
        ):
            conn.execute(
                """
                INSERT INTO smartploy_sessions (
                    session_hash, user_id, issuer, subject, email,
                    auth_source, created_at, last_seen_at, expires_at, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, 'oidc', now(), now(),
                    now() + interval '1 day', %s
                )
                """,
                (
                    session_hash, user.user_id, issuer, subject,
                    user.email, Jsonb({"temporary_private": "note"}),
                ),
            )
    yield a, b, ga, gb, consent, key_a, key_b, session_sha_a, session_sha_b
    with connect(DSN) as conn:
        conn.execute(
            """
            DELETE FROM smartploy_obumai_erasure_obligations
            WHERE request_id IN (
                SELECT request_id FROM smartploy_account_erasure_requests
                WHERE user_id IN (%s,%s)
            )
            """, (a.user_id, b.user_id),
        )
        conn.execute(
            "DELETE FROM smartploy_account_erasure_requests WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        for table in (
            "smartploy_browser_receipts", "smartploy_application_workspaces",
            "smartploy_profile_facts", "smartploy_cv_files",
            "smartploy_search_preferences", "smartploy_private_saved_jobs",
            "smartploy_application_preparations", "smartploy_applications",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE profile_id IN (%s,%s)",
                (a.profile_id, b.profile_id),
            )
        conn.execute(
            "DELETE FROM smartploy_jobs WHERE canonical_key IN (%s,%s)",
            ("job-" + nonce + "-a", "job-" + nonce + "-b"),
        )
        for table in (
            "smartploy_obumai_dispatch_attempts",
            "smartploy_obumai_consent_events",
            "smartploy_obumai_consents",
            "smartploy_sessions", "smartploy_user_identities",
            "smartploy_user_profiles", "smartploy_users",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE user_id IN (%s,%s)",
                (a.user_id, b.user_id),
            )


def test_quarantine_revokes_only_owner_sessions_and_consents_and_scrubs_email(scoped):
    a, b, ca, cb, consents, ka, kb, sa, sb = scoped
    quarantine = PostgresAccountErasureRepository(DSN)
    status = quarantine.quarantine(a.user_id, a.profile_id)
    assert status.status == "quarantined"
    assert status.revoked_consents == 1
    assert status.revoked_sessions == 1
    assert status.pending_provider_obligations == 0
    public = status.to_dict()
    assert public["processing_disabled"] is True
    assert public["erasure_completed"] is False
    assert public["local_data_purged"] is False
    assert public["provider_deletion_verified"] is False
    assert a.user_id not in json.dumps(public)
    assert a.email not in json.dumps(public)
    assert public["future_obumai_dispatch_authorized"] is False
    assert not consents.authorized(a, ka, ca.job_snapshot_sha256, ca.evidence_sha256)
    assert consents.authorized(b, kb, cb.job_snapshot_sha256, cb.evidence_sha256)
    assert [e.event_type for e in consents.events(a)] == ["revoked", "granted"]

    with connect(DSN) as conn:
        current = conn.execute(
            "SELECT email,status,metadata FROM smartploy_users WHERE user_id=%s",
            (a.user_id,),
        ).fetchone()
        assert current == ("", "disabled", {})
        own = conn.execute(
            "SELECT revoked_at,email,metadata FROM smartploy_sessions WHERE session_hash=%s",
            (sa,),
        ).fetchone()
        other = conn.execute(
            "SELECT revoked_at,email FROM smartploy_sessions WHERE session_hash=%s",
            (sb,),
        ).fetchone()
        assert own[0] is not None and own[1:] == ("", {})
        assert other == (None, b.email)

    # Ordinary browser identity resolution must never restore the email.
    ids = PostgresIdentityRepository(DSN)
    again = ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://sso.example.invalid",
        subject="erasure-a-" + ka.removeprefix("job-").removesuffix("-a"),
        email="sensitive@example.invalid", auth_source="oidc",
    ))
    assert again.user_id == a.user_id
    restored = ids.get(a.user_id)
    assert restored.status == "disabled" and restored.email == ""
    with pytest.raises(ConsentIdentityError):
        consents.grant(a, ka, ca.job_snapshot_sha256, ca.evidence_sha256)
    with pytest.raises(ValueError, match="Disabled"):
        ids.link_identity(a.user_id, AuthenticatedPrincipal(
            issuer="https://other-sso.example.invalid", subject="alias-a",
        ))
    # Re-run is safe: no second revocation event; same request ID.
    again_quarantined = quarantine.quarantine(a.user_id, a.profile_id)
    assert again_quarantined.request_id == status.request_id
    assert again_quarantined.revoked_consents == 0
    assert again_quarantined.revoked_sessions == 0
    assert len(consents.events(a)) == 2


def test_mismatched_owner_denied_without_mutating_any_account(scoped):
    a, b, _, _, _, _, _, _, _ = scoped
    q = PostgresAccountErasureRepository(DSN)
    with pytest.raises(ErasureIdentityMismatch):
        q.quarantine(a.user_id, b.profile_id)
    with pytest.raises(ErasureIdentityMismatch):
        q.quarantine("invalid-id", b.profile_id)
    assert PostgresIdentityRepository(DSN).get(a.user_id).status == "active"
    assert PostgresIdentityRepository(DSN).get(b.user_id).status == "active"


def test_uncertain_provider_attempt_is_inventoried_never_claimed_deleted(scoped):
    a, b, ca, _, ledger, ka, _, _, _ = scoped
    job = {"job": "synthetic"}
    evidence = {"approved": True}
    package = ApplicationPreparation(
        package_id="prep-erasure-fixture-" + uuid4().hex,
        profile_id=a.profile_id, canonical_key=ka,
        preparation_contract=PREPARATION_CONTRACT,
        job_snapshot_sha256=_sha(job), evidence_sha256=_sha(evidence),
        job_snapshot=job, evidence_snapshot=evidence, score_snapshot={},
    ).normalized()
    grant, _ = ledger.grant(a, ka, package.job_snapshot_sha256, package.evidence_sha256)
    attempts = PostgresDraftDispatchRepository(DSN)
    request = "smartploy:application_package_v1:" + package.package_id
    attempt, created = attempts.reserve(grant, package, request)
    assert created and attempt.state == "sending"
    q = PostgresAccountErasureRepository(DSN)
    quarantined = q.quarantine(a.user_id, a.profile_id)
    assert quarantined.pending_provider_obligations == 1
    obligations = q.list_operator_obligations(quarantined.request_id)
    assert len(obligations) == 1
    assert obligations[0].remote_request_id == request
    assert obligations[0].remote_job_id == ""
    assert obligations[0].state == "requires_provider_followup"
    assert q.quarantine(a.user_id, a.profile_id).pending_provider_obligations == 1
    assert not ledger.authorized(a, ka, grant.job_snapshot_sha256, grant.evidence_sha256)
    assert PostgresIdentityRepository(DSN).get(b.user_id).status == "active"
    assert quarantined.to_dict()["erasure_completed"] is False


def test_quarantine_waits_until_an_in_flight_protected_send_finishes(scoped):
    a, _, grant, _, ledger, key, _, _, _ = scoped
    q = PostgresAccountErasureRepository(DSN)
    entered = Event()
    release = Event()
    started = Event()
    finished = Event()

    def hold_send():
        with ledger.hold_authorized_dispatch(
            a, key, grant.job_snapshot_sha256, grant.evidence_sha256,
        ):
            entered.set()
            assert release.wait(8)

    def close_account():
        started.set()
        answer = q.quarantine(a.user_id, a.profile_id)
        finished.set()
        return answer

    with ThreadPoolExecutor(max_workers=2) as pool:
        send = pool.submit(hold_send)
        assert entered.wait(8)
        closing = pool.submit(close_account)
        try:
            assert started.wait(8)
            assert not finished.wait(0.15), (
                "Quarantine must not commit while a guarded outbound send holds lock"
            )
        finally:
            release.set()
        send.result(timeout=8)
        closed = closing.result(timeout=8)
    assert closed.status == "quarantined"
    assert not ledger.authorized(
        a, key, grant.job_snapshot_sha256, grant.evidence_sha256,
    )
    with pytest.raises((ConsentDispatchDenied, ConsentIdentityError)):
        with ledger.hold_authorized_dispatch(
            a, key, grant.job_snapshot_sha256, grant.evidence_sha256,
        ):
            pytest.fail("Closing an account cannot permit a new dispatch")



def test_private_data_inventory_is_owner_scoped_and_redacted(scoped):
    a, b, _, _, _, _, _, _, _ = scoped
    with connect(DSN) as conn:
        conn.execute(
            """
            INSERT INTO smartploy_profile_facts (
                profile_id, fact_id, fact_type, value, normalized_value, source,
                approved, created_at
            ) VALUES (%s,'fact-private','skill','Sensitive skill','sensitive skill',
                      'synthetic',true,now())
            """, (a.profile_id,),
        )
        conn.execute(
            """
            INSERT INTO smartploy_cv_files (
                profile_id,filename,media_type,content,extracted_text,sha256
            ) VALUES (%s,'private.pdf','application/pdf',%s,
                      'Private CV',%s)
            """, (a.profile_id, b"%PDF-1.4 fixture", "a" * 64),
        )
        conn.execute(
            """
            INSERT INTO smartploy_search_preferences (profile_id,mode,revision)
            VALUES (%s,'personalized',1)
            """, (a.profile_id,),
        )
        conn.execute(
            """
            INSERT INTO smartploy_private_saved_jobs (
                profile_id,saved_job_id,company,role_title,description
            ) VALUES (%s,'saved-fixture','Private Inc','Role','Confidential')
            """, (a.profile_id,),
        )
        conn.execute(
            """
            INSERT INTO smartploy_application_workspaces (
                workspace_id,profile_id,canonical_key,role_title,company,
                cv_text,cover_letter_text,job_fingerprint
            ) VALUES ('workspace-a-fixture',%s,'private-job',
                      'Role','Private Inc','Private CV',
                      'Private letter','fingerprint')
            """, (a.profile_id,),
        )
        conn.execute(
            """
            INSERT INTO smartploy_browser_receipts (
                profile_id,workspace_id,document_revision,document_sha256,
                reference,confirmation_page_url,confirmation_page_sha256,
                observed_at,evidence_digest
            ) VALUES (%s,'workspace-a-fixture',1,%s,
                      'TEST01','https://example.invalid/confirmation',
                      %s,now(),%s)
            """, (a.profile_id, "b" * 64, "c" * 64, "d" * 64),
        )
    with pytest.raises(ErasureIdentityMismatch):
        inspect_quarantined_account(DSN, a.user_id, a.profile_id)
    q = PostgresAccountErasureRepository(DSN)
    state = q.quarantine(a.user_id, a.profile_id)
    inventory = inspect_quarantined_account(DSN, a.user_id, a.profile_id)
    assert inventory.request_id == state.request_id
    assert inventory.counts["identities"] == 1
    assert inventory.counts["sessions"] == 1
    assert inventory.counts["profile_facts"] == 1
    assert inventory.counts["cv_files"] == 1
    assert inventory.counts["search_preferences"] == 1
    assert inventory.counts["private_saved_jobs"] == 1
    assert inventory.counts["application_workspaces"] == 1
    assert inventory.counts["browser_receipts"] == 1
    assert inventory.counts["consents"] == 1
    assert inventory.counts["consent_events"] == 2
    assert inventory.counts["dispatch_attempts"] == 0
    assert inventory.unknown_owner_tables == ()
    report = inventory.to_dict()
    assert report["local_purge_completed"] is False
    assert report["hard_purge_authorized"] is False
    assert report["untracked_remote_history_may_exist"] is True
    serialized = json.dumps(report)
    for secret in (
        a.user_id, a.profile_id, "Sensitive skill", "Private CV",
        "Private Inc", "private.pdf", "sensitive@example.invalid",
    ):
        assert secret not in serialized
    with pytest.raises(ErasureIdentityMismatch):
        inspect_quarantined_account(DSN, b.user_id, b.profile_id)


def test_refresh_excludes_quarantined_owner_without_starving_other_jobs(scoped):
    a, b, _, _, _, ka, kb, _, _ = scoped
    with connect(DSN) as conn:
        for key in (ka, kb):
            conn.execute(
                """
                INSERT INTO smartploy_jobs (
                    canonical_key,job_id,company,role_title,candidate,
                    first_seen_at,last_seen_at,source_current
                ) VALUES (%s,%s,'Fictional Ltd','Synthetic Developer',%s,
                          now(),now(),true)
                """,
                (key, key, Jsonb({})),
            )
    prep = PostgresPreparationRepository(DSN)
    for user, key, timestamp in (
        (a, ka, "2026-10-17T10:00:00+00:00"),
        (b, kb, "2026-10-17T11:00:00+00:00"),
    ):
        job, evidence = {"job": key}, {"profile_id": user.profile_id}
        item = ApplicationPreparation(
            package_id="prep-refresh-" + key,
            profile_id=user.profile_id, canonical_key=key,
            preparation_contract=PREPARATION_CONTRACT,
            job_snapshot_sha256=_sha(job), evidence_sha256=_sha(evidence),
            job_snapshot=job, evidence_snapshot=evidence, score_snapshot={},
            requested_at=timestamp, updated_at=timestamp,
        ).normalized()
        saved, created = prep.create_or_get(item)
        assert created
        prep.save(with_runtime(
            saved, status="queued", obum_job_id="remote-" + key,
            updated_at=timestamp,
        ))
    assert [v.profile_id for v in prep.list_refresh_candidates(limit=2)] == [
        a.profile_id, b.profile_id,
    ]
    q = PostgresAccountErasureRepository(DSN)
    report = q.quarantine(a.user_id, a.profile_id)
    assert report.pending_provider_obligations == 1
    remaining = prep.list_refresh_candidates(limit=2)
    assert [v.profile_id for v in remaining] == [b.profile_id]
    assert remaining[0].obum_job_id == "remote-" + kb
    assert len(q.list_operator_obligations(report.request_id)) == 1


def test_agent_zero_events_are_included_in_account_erasure_inventory(scoped):
    """New owner-scoped tables must not be invisible to privacy operations."""
    a, b, _, _, _, _, _, _, _ = scoped
    workspace_id = "kit-agent-erasure-" + uuid4().hex
    with connect(DSN) as conn:
        conn.execute(
            """INSERT INTO smartploy_application_workspaces
               (workspace_id, profile_id, canonical_key, role_title, company,
                cv_text, cover_letter_text, job_fingerprint)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                workspace_id, a.profile_id, "job-agent-" + uuid4().hex,
                "Junior QA", "Fictional Company", "Approved synthetic CV",
                "Synthetic cover letter", "a" * 64,
            ),
        )
    repo = PostgresApplicationAgentRepository(DSN)
    first, created = repo.create_or_get(a.profile_id, workspace_id)
    assert created and first is not None
    PostgresAccountErasureRepository(DSN).quarantine(a.user_id, a.profile_id)
    inventory = inspect_quarantined_account(DSN, a.user_id, a.profile_id)
    assert inventory.counts["application_agents"] == 1
    assert inventory.counts["application_agent_events"] == 1
    assert inventory.unknown_owner_tables == ()
    assert repo.get(a.profile_id, first["agent_id"]) is None
    assert repo.list(b.profile_id) == []

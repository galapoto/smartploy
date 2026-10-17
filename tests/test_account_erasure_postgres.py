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

from smartploy.account_erasure import (
    ErasureIdentityMismatch, PostgresAccountErasureRepository,
)
from smartploy.ai_processing_consent import (
    ConsentDispatchDenied, ConsentIdentityError, PostgresJobAIConsentRepository,
)
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.obumai_dispatch_storage import PostgresDraftDispatchRepository
from smartploy.preparations import ApplicationPreparation, PREPARATION_CONTRACT
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


def _sha(v):
    return sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()


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
                    user.email, '{"temporary_private": "note"}',
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
        subject=a.user_id.replace("usr-", "nonexistent-subject-"),
        email="sensitive@example.invalid", auth_source="oidc",
    ))
    # A *different* issuer/subject is not an alias and must not revive A.
    assert again.user_id != a.user_id
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

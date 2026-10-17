"""Real transaction-level consent locks; no AI/network/employer action."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import os

import pytest
from psycopg import connect

from smartploy.ai_processing_consent import (
    ConsentDispatchDenied, ConsentIdentityError, PostgresJobAIConsentRepository,
)
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture
def scope():
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    identities = PostgresIdentityRepository(DSN)
    a = identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://auth.example.invalid", subject="guard-a-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    b = identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://auth.example.invalid", subject="guard-b-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    repo = PostgresJobAIConsentRepository(DSN)
    key = "synthetic-job-" + nonce
    yield repo, a, b, key
    with connect(DSN) as conn:
        for table in (
            "smartploy_obumai_consent_events", "smartploy_obumai_consents",
            "smartploy_user_identities", "smartploy_user_profiles",
            "smartploy_users",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE user_id IN (%s, %s)",
                (a.user_id, b.user_id),
            )


def test_guard_denies_missing_other_user_or_stale_hashes(scope):
    repo, a, b, key = scope
    job_sha, evidence_sha = "a" * 64, "b" * 64
    with pytest.raises(ConsentDispatchDenied):
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            pytest.fail("No consent must never enter the dispatch boundary")
    own, _ = repo.grant(a, key, job_sha, evidence_sha)
    assert own.active
    for binding, job, evidence in (
        (b, job_sha, evidence_sha),
        (a, "c" * 64, evidence_sha),
        (a, job_sha, "d" * 64),
    ):
        with pytest.raises(ConsentDispatchDenied):
            with repo.hold_authorized_dispatch(binding, key, job, evidence):
                pytest.fail("Wrong account/snapshot cannot enter dispatch")
    assert [c.consent_id for c in repo.list_active_verified()] == [own.consent_id]
    with connect(DSN) as conn:
        conn.execute(
            "UPDATE smartploy_users SET status = 'disabled' WHERE user_id = %s",
            (a.user_id,),
        )
    assert repo.list_active_verified() == []
    with pytest.raises(ConsentIdentityError):
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            pytest.fail("Disabled account must not enter dispatch")
    with connect(DSN) as conn:
        conn.execute(
            "UPDATE smartploy_users SET status = 'active' WHERE user_id = %s",
            (a.user_id,),
        )
    repo.revoke(a, own.consent_id)
    assert repo.list_active_verified() == []
    with pytest.raises(ConsentDispatchDenied):
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            pytest.fail("Revoked consent must never enter dispatch")


def test_withdrawal_cannot_commit_during_authorized_dispatch(scope):
    repo, a, _, key = scope
    job_sha, evidence_sha = "f" * 64, "e" * 64
    item, _ = repo.grant(a, key, job_sha, evidence_sha)
    entered = Event()
    release = Event()
    revoke_started = Event()
    revoke_finished = Event()

    def guarded_dispatch():
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            entered.set()
            assert release.wait(8), "Synthetic outbound operation did not finish"
        return "finished"

    def withdraw():
        revoke_started.set()
        withdrawn = repo.revoke(a, item.consent_id)
        revoke_finished.set()
        return withdrawn

    with ThreadPoolExecutor(max_workers=2) as pool:
        guarded = pool.submit(guarded_dispatch)
        assert entered.wait(8), "Failed to enter guarded dispatch"
        withdrawing = pool.submit(withdraw)
        try:
            assert revoke_started.wait(8)
            assert not revoke_finished.wait(0.15), (
                "Withdrawal committed before the in-flight guarded action finished"
            )
        finally:
            release.set()
        assert guarded.result(timeout=8) == "finished"
        removed = withdrawing.result(timeout=8)
        assert removed is not None and not removed.active
    with pytest.raises(ConsentDispatchDenied):
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            pytest.fail("Completed withdrawal must prohibit a new send")
    assert [event.event_type for event in repo.events(a)] == ["revoked", "granted"]


def test_regrant_waits_for_guard_and_replaced_revision_denies_old_hash(scope):
    repo, a, _, key = scope
    job_sha, evidence_sha = "1" * 64, "2" * 64
    repo.grant(a, key, job_sha, evidence_sha)
    new_hash = "3" * 64
    started = Event()
    release = Event()

    def protected():
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            started.set()
            assert release.wait(8)

    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(protected)
        assert started.wait(8)
        regrant = pool.submit(repo.grant, a, key, job_sha, new_hash)
        try:
            assert not regrant.done()
        finally:
            release.set()
        old.result(timeout=8)
        replaced, changed = regrant.result(timeout=8)
    assert changed and replaced.revision == 2
    with pytest.raises(ConsentDispatchDenied):
        with repo.hold_authorized_dispatch(a, key, job_sha, evidence_sha):
            pytest.fail("Old evidence hash may not regain authority after regrant")
    with repo.hold_authorized_dispatch(a, key, job_sha, new_hash) as locked:
        assert locked.revision == 2 and locked.evidence_sha256 == new_hash

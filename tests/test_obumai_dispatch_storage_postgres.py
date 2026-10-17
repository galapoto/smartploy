"""Real Postgres: only one attempt may exist even under competing workers.

Synthetic candidates and ids. No ObumAI HTTP calls or employer actions.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from uuid import uuid4

import pytest
from psycopg import connect

from smartploy.ai_processing_consent import PostgresJobAIConsentRepository
from smartploy.domain import canonical_json
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.obumai_dispatch_storage import PostgresDraftDispatchRepository
from smartploy.preparations import ApplicationPreparation, PREPARATION_CONTRACT
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


def _hash(data: dict) -> str:
    return sha256(canonical_json(data).encode("utf-8")).hexdigest()


@pytest.fixture
def scope():
    PostgresJobRepository(DSN).migrate()
    nonce = uuid4().hex
    identities = PostgresIdentityRepository(DSN)
    a = identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://auth.example.invalid", subject="dispatch-a-" + nonce,
        email="shared@example.invalid", auth_source="oidc",
    ))
    b = identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://auth.example.invalid", subject="dispatch-b-" + nonce,
        email="shared@example.invalid", auth_source="oidc",
    ))
    ledger = PostgresJobAIConsentRepository(DSN)
    attempts = PostgresDraftDispatchRepository(DSN)

    def make(binding, suffix=""):
        job = {"job": "synthetic" + suffix}
        evidence = {"profile_id": binding.profile_id, "facts": ["synthetic"]}
        package = ApplicationPreparation(
            package_id="prep-fixture-" + nonce + binding.user_id[-6:] + suffix,
            profile_id=binding.profile_id,
            canonical_key="job-fixture-" + nonce,
            preparation_contract=PREPARATION_CONTRACT,
            job_snapshot_sha256=_hash(job),
            evidence_sha256=_hash(evidence),
            job_snapshot=job,
            evidence_snapshot=evidence,
            score_snapshot={},
        ).normalized()
        consent, _ = ledger.grant(
            binding, package.canonical_key,
            package.job_snapshot_sha256, package.evidence_sha256,
        )
        return package, consent

    yield a, b, ledger, attempts, make
    with connect(DSN) as conn:
        conn.execute(
            "DELETE FROM smartploy_obumai_dispatch_attempts WHERE user_id IN (%s,%s)",
            (a.user_id, b.user_id),
        )
        for table in (
            "smartploy_obumai_consent_events", "smartploy_obumai_consents",
            "smartploy_user_identities", "smartploy_user_profiles", "smartploy_users",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE user_id IN (%s,%s)",
                (a.user_id, b.user_id),
            )


def test_one_at_most_sending_marker_survives_restart_and_regrant(scope):
    a, _, ledger, attempts, make = scope
    package, consent = make(a)
    request_id = "smartploy:application_package_v1:" + package.package_id

    def reserve():
        return PostgresDraftDispatchRepository(DSN).reserve(
            consent, package, request_id,
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: reserve(), range(5)))
    assert sum(1 for _, created in results if created) == 1
    assert {item.state for item, _ in results} == {"sending"}
    assert len({item.package_id for item, _ in results}) == 1
    assert attempts.get(package.package_id, profile_id=a.profile_id).state == "sending"
    assert attempts.get(package.package_id, profile_id="profile-unrelated") is None

    ledger.revoke(a, consent.consent_id)
    renewed, changed = ledger.grant(
        a, package.canonical_key,
        package.job_snapshot_sha256, package.evidence_sha256,
    )
    assert changed and renewed.revision == consent.revision + 2
    again, is_new = PostgresDraftDispatchRepository(DSN).reserve(
        renewed, package, request_id,
    )
    assert not is_new and again.state == "sending"

    uncertain = attempts.mark_uncertain(
        package.package_id, request_id, profile_id=a.profile_id,
        code="remote_error",
    )
    assert uncertain.state == "uncertain"
    assert uncertain.failure_code == "remote_error"
    assert attempts.get(package.package_id, profile_id=a.profile_id).state == "uncertain"
    again, fresh = reserve()
    assert not fresh and again.state == "uncertain"
    with pytest.raises(ValueError, match="uncertain"):
        attempts.acknowledge(
            package.package_id, request_id, "remote-job-1", profile_id=a.profile_id,
        )
    with pytest.raises(ValueError, match="sanitized"):
        attempts.mark_uncertain(
            package.package_id, request_id, profile_id=a.profile_id,
            code="private-password-from-exception",
        )


def test_acknowledgement_is_durable_idempotent_and_account_scoped(scope):
    a, b, _, attempts, make = scope
    package_a, consent_a = make(a)
    package_b, consent_b = make(b)
    key_a = "smartploy:application_package_v1:" + package_a.package_id
    key_b = "smartploy:application_package_v1:" + package_b.package_id
    first, new = attempts.reserve(consent_a, package_a, key_a)
    assert new and first.state == "sending"
    second, new = attempts.reserve(consent_b, package_b, key_b)
    assert new and second.state == "sending"
    assert first.user_id != second.user_id
    with pytest.raises(ValueError, match="identity|match"):
        attempts.reserve(consent_b, package_a, key_b)
    with pytest.raises(ValueError, match="request ID conflicts"):
        changed = ApplicationPreparation(
            **{**package_b.__dict__, "package_id": package_b.package_id + "-new"}
        ).normalized()
        attempts.reserve(consent_b, changed, key_a)

    acknowledged = attempts.acknowledge(
        package_a.package_id, key_a, "remote-fixture-1", profile_id=a.profile_id,
    )
    assert acknowledged.state == "acknowledged"
    assert acknowledged.obum_job_id == "remote-fixture-1"
    repeat = PostgresDraftDispatchRepository(DSN).acknowledge(
        package_a.package_id, key_a, "remote-fixture-1", profile_id=a.profile_id,
    )
    assert repeat.state == "acknowledged"
    with pytest.raises(ValueError, match="changed"):
        attempts.acknowledge(
            package_a.package_id, key_a, "remote-job-different",
            profile_id=a.profile_id,
        )
    after = attempts.mark_uncertain(
        package_a.package_id, key_a, profile_id=a.profile_id,
        code="remote_error",
    )
    assert after.state == "acknowledged"
    assert attempts.get(package_a.package_id, profile_id=b.profile_id) is None
    assert all(
        row.to_review_dict()["automatic_retry_authorized"] is False
        for row in attempts.list_needing_reconciliation()
        if row.package_id == package_a.package_id
    )

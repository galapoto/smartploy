"""PostgreSQL consent survives restart and denies wrong users or stale snapshots."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from psycopg import connect

from smartploy.ai_processing_consent import ConsentIdentityError, PostgresJobAIConsentRepository
from smartploy.identity import (
    AuthenticatedPrincipal, PostgresIdentityRepository, UserProfileBinding,
)
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


def test_postgres_consent_active_identity_revision_and_revoke():
    PostgresJobRepository(DSN).migrate()
    identities = PostgresIdentityRepository(DSN)
    nonce = uuid4().hex
    a = identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://auth.example.invalid", subject="user-a-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    b = identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://auth.example.invalid", subject="user-b-" + nonce,
        email="same@example.invalid", auth_source="oidc",
    ))
    repo = PostgresJobAIConsentRepository(DSN)
    key = "job-" + nonce
    job_hash, facts_hash = "a" * 64, "b" * 64
    try:
        assert not repo.authorized(a, key, job_hash, facts_hash)
        first, changed = repo.grant(a, key, job_hash, facts_hash)
        assert changed and first.revision == 1 and first.active
        assert repo.authorized(a, key, job_hash, facts_hash)
        assert not repo.authorized(b, key, job_hash, facts_hash)
        assert not repo.authorized(a, key, "e" * 64, facts_hash)
        assert not repo.authorized(a, key, job_hash, "f" * 64)
        assert repo.list(b) == [] and repo.events(b) == []
        assert repo.revoke(b, first.consent_id) is None

        same, changed = PostgresJobAIConsentRepository(DSN).grant(
            a, key, job_hash, facts_hash,
        )
        assert not changed and same.revision == 1
        assert len(repo.events(a)) == 1
        newer, changed = repo.grant(a, key, job_hash, "c" * 64)
        assert changed and newer.revision == 2
        assert not repo.authorized(a, key, job_hash, facts_hash)
        assert repo.authorized(a, key, job_hash, "c" * 64)

        mismatched = UserProfileBinding(
            user_id=a.user_id, profile_id=b.profile_id,
            email="same@example.invalid",
        )
        with pytest.raises(ConsentIdentityError):
            repo.grant(mismatched, key, job_hash, "c" * 64)
        assert not repo.authorized(mismatched, key, job_hash, "c" * 64)

        with connect(DSN) as conn:
            conn.execute(
                "UPDATE smartploy_users SET status = 'disabled' WHERE user_id = %s",
                (a.user_id,),
            )
        assert not repo.authorized(a, key, job_hash, "c" * 64)
        with pytest.raises(ConsentIdentityError):
            repo.grant(a, key, job_hash, "c" * 64)
        with connect(DSN) as conn:
            conn.execute(
                "UPDATE smartploy_users SET status = 'active' WHERE user_id = %s",
                (a.user_id,),
            )
        revoked = PostgresJobAIConsentRepository(DSN).revoke(a, first.consent_id)
        assert revoked is not None and revoked.revision == 3
        assert not repo.authorized(a, key, job_hash, "c" * 64)
        assert repo.revoke(a, first.consent_id).revision == 3
        assert [event.event_type for event in repo.events(a)] == [
            "revoked", "granted", "granted",
        ]
        renewed, changed = repo.grant(a, key, job_hash, "c" * 64)
        assert changed and renewed.revision == 4
        assert repo.authorized(a, key, job_hash, "c" * 64)
        assert PostgresJobAIConsentRepository(DSN).list(a)[0] == renewed
    finally:
        # No new FKs to the legacy owner tables; delete synthetic privacy rows.
        with connect(DSN) as conn:
            for table in ("smartploy_obumai_consent_events",
                          "smartploy_obumai_consents",
                          "smartploy_user_identities",
                          "smartploy_user_profiles",
                          "smartploy_users"):
                conn.execute(
                    f"DELETE FROM {table} WHERE user_id IN (%s, %s)",
                    (a.user_id, b.user_id),
                )

"""Per-account PostgreSQL auto-IT-draft permissions, revocation, quarantine."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import pytest
from psycopg import connect

from smartploy.autodraft import AutoDraftConflict,PostgresAutoDraftRepository
from smartploy.account_erasure import (
    PostgresAccountErasureRepository, inspect_quarantined_account,
)
from smartploy.identity import AuthenticatedPrincipal,PostgresIdentityRepository
from smartploy.storage import PostgresJobRepository

DSN=os.getenv("SMARTPLOY_TEST_DATABASE_URL","")
pytestmark=pytest.mark.skipif(not DSN,reason="SMARTPLOY_TEST_DATABASE_URL not configured")


def test_real_postgres_two_users_same_email_revision_race_and_quarantine():
    PostgresJobRepository(DSN).migrate()
    suffix=uuid4().hex
    ids=PostgresIdentityRepository(DSN)
    a=ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://oidc.example.invalid",subject="autodraft-a-"+suffix,
        email="shared@example.invalid",auth_source="oidc",
    ))
    b=ids.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://oidc.example.invalid",subject="autodraft-b-"+suffix,
        email="shared@example.invalid",auth_source="oidc",
    ))
    store=PostgresAutoDraftRepository(DSN)
    try:
        assert store.get(a.user_id,a.profile_id).enabled is False
        first=store.save(a,expected_revision=0,enabled=True,
                         minimum_score=75,max_per_cycle=3)
        assert first.enabled and first.revision==1
        assert store.get(b.user_id,b.profile_id).enabled is False
        assert any(c.user_id==a.user_id for c in store.list_enabled(limit=100))
        # Concurrent settings updates on different browser devices cannot
        # both succeed with the same expected revision.
        def update() -> str:
            try:
                result=store.save(a,expected_revision=1,enabled=False,
                                  minimum_score=80,max_per_cycle=3)
                return "updated-"+str(result.revision)
            except AutoDraftConflict:
                return "revision_conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:update(),range(2)))
        assert sorted(results)==["revision_conflict","updated-2"]
        reenabled=store.save(a,expected_revision=2,enabled=True,
                             minimum_score=75,max_per_cycle=3)
        assert reenabled.enabled
        PostgresAccountErasureRepository(DSN).quarantine(a.user_id,a.profile_id)
        assert store.get(a.user_id,a.profile_id).enabled is False
        assert all(c.user_id!=a.user_id for c in store.list_enabled(limit=100))
        inventory=inspect_quarantined_account(DSN,a.user_id,a.profile_id)
        assert inventory.counts["autodraft_settings"]==1
    finally:
        with connect(DSN) as conn:
            conn.execute(
                "DELETE FROM smartploy_autodraft_settings WHERE user_id IN (%s,%s)",
                (a.user_id,b.user_id),
            )

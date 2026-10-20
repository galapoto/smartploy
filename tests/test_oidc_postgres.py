import asyncio
import os

import pytest
from psycopg import connect

from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.oidc import PostgresOIDCStateCache, PostgresSessionRepository
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def clean_db():
    PostgresJobRepository(DSN).migrate()
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE smartploy_autodraft_settings, smartploy_oidc_state, smartploy_sessions, smartploy_user_profiles, smartploy_user_identities, smartploy_users")
        conn.commit()


def test_postgres_session_stores_hash_not_browser_token(clean_db):
    identities = PostgresIdentityRepository(DSN)
    principal = AuthenticatedPrincipal(
        issuer="https://auth.obumai.com",
        subject="user-subject",
        email="user@example.com",
        auth_source="oidc",
    )
    binding = identities.resolve_or_create(principal)
    sessions = PostgresSessionRepository(DSN)

    issued = sessions.create(
        user_id=binding.user_id,
        principal=principal,
        provider_session_id="provider-session",
        ttl_seconds=3600,
    )
    assert issued.token
    assert sessions.get(issued.token) is not None

    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_hash, issuer, subject, email, metadata FROM smartploy_sessions"
            )
            row = cur.fetchone()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'smartploy_sessions'
                """
            )
            columns = {str(item[0]) for item in cur.fetchall()}

    assert row[0] != issued.token
    assert issued.token not in str(row)
    assert row[1] == "https://auth.obumai.com"
    assert row[2] == "user-subject"
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "id_token" not in columns

    sessions.revoke(issued.token)
    assert sessions.get(issued.token) is None


def test_oidc_state_cache_hashes_state_key_and_expires_server_side(clean_db):
    cache = PostgresOIDCStateCache(DSN)
    key = "_state_obum_identity_public-state-value"
    payload = '{"data":{"code_verifier":"server-secret","nonce":"nonce"}}'

    asyncio.run(cache.set(key, payload, 600))
    assert asyncio.run(cache.get(key)) == payload

    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT cache_key_hash, payload FROM smartploy_oidc_state")
            stored_key, stored_payload = cur.fetchone()

    assert stored_key != key
    assert "public-state-value" not in stored_key
    assert stored_payload == payload

    asyncio.run(cache.delete(key))
    assert asyncio.run(cache.get(key)) is None

"""SP127 offline/privacy and PostgreSQL evidence for opt-in social messaging.

Synthetic subjects share an email but not a stable issuer/subject ID.
Never interpret these as real logged-in-user production acceptance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.service import SmartployService
from smartploy.social_network import (
    MemorySocialRepository, PostgresSocialRepository,
    SocialConflict, SocialError, SocialNotFound,
)
from smartploy.storage import PostgresJobRepository


class SyntheticVerifier:
    def verify(self, token: str) -> AccessPrincipal:
        if token not in {"a", "b", "c"}:
            raise ValueError("Unknown fictional user")
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer="https://example.cloudflareaccess.com",
            subject="social-" + token, email="same@example.invalid",
            audience="smartploy-fixture", issued_at=now,
            expires_at=now + timedelta(minutes=5), key_id="synthetic",
        )


def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv(
        "SMARTPLOY_ACCESS_ISSUER", "https://example.cloudflareaccess.com"
    )
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-fixture")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "same@example.invalid")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    return TestClient(create_app(SmartployService(), access_verifier=SyntheticVerifier()))


def h(account: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": account}


def profile(handle: str, discoverable: bool = True) -> dict[str, object]:
    return {"handle": handle, "display_name": "Fictional " + handle,
            "discoverable": discoverable}


def test_anonymous_denied_and_no_directory_or_email_leaks(monkeypatch):
    api = client(monkeypatch)
    for path in ["/api/v1/social/me", "/api/v1/social/connections",
                 "/api/v1/social/people/fake", "/api/v1/social/messages/fake"]:
        assert api.get(path).status_code == 401
    assert api.put("/api/v1/social/me", json=profile("fictional_a")).status_code == 401
    assert api.post("/api/v1/social/people/fake/follow").status_code == 401
    assert api.post("/api/v1/social/messages/fake", json={"body": "Hi"}).status_code == 401

    assert api.get("/api/v1/social/me", headers=h("a")).json() == {
        "profile": None, "opted_in": False
    }
    assert api.get("/api/v1/social/people/fictional_b", headers=h("a")).status_code == 404
    saved = api.put("/api/v1/social/me", json=profile("fictional_a", False), headers=h("a"))
    assert saved.status_code == 200
    assert saved.headers["cache-control"] == "private, no-store"
    assert saved.json()["opted_in"] is False
    assert api.get("/api/v1/social/people/fictional_a", headers=h("b")).status_code == 404
    assert "@" not in str(saved.json())
    assert "email" not in str(api.get("/api/v1/social/me", headers=h("a")).json())


def test_real_mutual_follow_flow_messages_block_and_isolation(monkeypatch):
    api = client(monkeypatch)
    for account, handle in [("a", "alice_job"), ("b", "bob_job"), ("c", "charlie_job")]:
        resp = api.put("/api/v1/social/me", json=profile(handle), headers=h(account))
        assert resp.status_code == 200, resp.text
    assert api.get("/api/v1/social/people/alice_job", headers=h("c")).status_code == 200
    first = api.post("/api/v1/social/people/bob_job/follow", headers=h("a"))
    assert first.status_code == 200
    assert first.json()["following"] is True
    assert first.json()["follows_you"] is False
    assert api.post("/api/v1/social/messages/bob_job", json={"body": "Hello"}, headers=h("a")).status_code == 404

    assert api.post("/api/v1/social/people/alice_job/follow", headers=h("b")).status_code == 200
    message = api.post(
        "/api/v1/social/messages/bob_job",
        json={"body": "Hello from user A."}, headers=h("a"),
    )
    assert message.status_code == 201, message.text
    assert message.json()["message"]["mine"] is True
    assert "@" not in str(message.json())
    bob = api.get("/api/v1/social/messages/alice_job", headers=h("b"))
    assert bob.status_code == 200
    assert bob.headers["cache-control"] == "private, no-store"
    assert bob.json()["messages"][0]["body"] == "Hello from user A."
    assert bob.json()["messages"][0]["mine"] is False
    assert api.get("/api/v1/social/messages/bob_job", headers=h("c")).status_code == 404
    mutual = api.get("/api/v1/social/connections", headers=h("a")).json()
    assert mutual["following"][0]["mutual"] is True
    assert mutual["private"] is True

    blocked = api.post("/api/v1/social/people/alice_job/block", headers=h("b"))
    assert blocked.status_code == 200 and blocked.json()["blocked"] is True
    assert api.get("/api/v1/social/messages/bob_job", headers=h("a")).status_code == 404
    assert api.post("/api/v1/social/messages/bob_job", json={"body": "Again"}, headers=h("a")).status_code == 404
    assert api.delete("/api/v1/social/people/alice_job/block", headers=h("b")).status_code == 200
    assert api.post("/api/v1/social/people/bob_job/follow", headers=h("a")).status_code == 200
    assert api.post("/api/v1/social/people/alice_job/follow", headers=h("b")).status_code == 200
    assert api.get("/api/v1/social/messages/bob_job", headers=h("a")).status_code == 200
    # Stable server subject keeps conversation history after a handle change.
    assert api.put("/api/v1/social/me", json=profile("renamed_alice"), headers=h("a")).status_code == 200
    history = api.get("/api/v1/social/messages/renamed_alice", headers=h("b"))
    assert history.json()["messages"][0]["body"] == "Hello from user A."


def test_invalid_payloads_reserved_handles_and_expected_account(monkeypatch):
    api = client(monkeypatch)
    for candidate in ["admin", "SMARTPLOY", "_other", "ab", "a" * 25, "bad-handle"]:
        assert api.put("/api/v1/social/me", json=profile(candidate), headers=h("a")).status_code == 422
    assert api.put("/api/v1/social/me", json={**profile("alice123"), "user_id": "usr-b"},
                   headers=h("a")).status_code == 422
    assert api.put("/api/v1/social/me", json=profile("alice123"), headers={
        **h("a"), "X-Smartploy-Expected-User-Id": "usr-wrong",
    }).status_code == 409
    assert api.put("/api/v1/social/me", json=profile("alice123"), headers=h("a")).status_code == 200
    assert api.put("/api/v1/social/me", json=profile("alice123"), headers=h("b")).status_code == 409
    assert api.post("/api/v1/social/people/alice123/follow", headers=h("a")).status_code == 422
    for body in ["", "\x00", "x" * 2001]:
        assert api.post("/api/v1/social/messages/alice123", json={"body": body},
                        headers=h("b")).status_code in (422, 404)


def test_rate_limit_and_no_employer_or_ai_side_effect(monkeypatch):
    api = client(monkeypatch)
    assert api.put("/api/v1/social/me", json=profile("user_a1"), headers=h("a")).status_code == 200
    assert api.put("/api/v1/social/me", json=profile("user_b2"), headers=h("b")).status_code == 200
    assert api.post("/api/v1/social/people/user_b2/follow", headers=h("a")).status_code == 200
    assert api.post("/api/v1/social/people/user_a1/follow", headers=h("b")).status_code == 200
    for n in range(12):
        assert api.post("/api/v1/social/messages/user_b2", json={
            "body": "Fictional message " + str(n),
        }, headers=h("a")).status_code == 201
    assert api.post("/api/v1/social/messages/user_b2",
                    json={"body": "Fictional message 13"},
                    headers=h("a")).status_code == 429
    assert api.get("/api/v1/social/messages/user_a1", headers=h("b")).json()["messages"][-1]["body"] == "Fictional message 11"
    assert api.get("/api/v1/jobs", headers=h("a")).json()["count"] == 0


def test_opt_out_revokes_mutual_connections_and_requires_new_consent():
    repo = MemorySocialRepository()
    repo.save_profile("usr-a", "alice_job", "Fictional Alice", True)
    repo.save_profile("usr-b", "bob_job", "Fictional Bob", True)
    repo.follow("usr-a", "bob_job")
    repo.follow("usr-b", "alice_job")
    assert repo.send("usr-a", "bob_job", "Before hiding")
    repo.save_profile("usr-a", "alice_job", "Fictional Alice", False)
    assert repo.connections("usr-a")["following"] == []
    assert repo.connections("usr-b")["following"] == []
    with pytest.raises(SocialNotFound):
        repo.messages("usr-b", "alice_job")
    repo.save_profile("usr-a", "alice_job", "Fictional Alice", True)
    with pytest.raises(SocialNotFound):
        repo.send("usr-a", "bob_job", "No silent reconnection")


def test_memory_connections_do_not_mislabel_single_follow_as_mutual():
    repo = MemorySocialRepository()
    repo.save_profile("usr-a", "alice_job", "Fictional Alice", True)
    repo.save_profile("usr-b", "bob_job", "Fictional Bob", True)
    repo.follow("usr-a", "bob_job")
    assert repo.connections("usr-b")["followers"][0]["mutual"] is False
    assert repo.connections("usr-a")["following"][0]["mutual"] is False
    repo.follow("usr-b", "alice_job")
    assert repo.connections("usr-b")["followers"][0]["mutual"] is True
    assert repo.connections("usr-a")["following"][0]["mutual"] is True


def test_memory_repo_handles_hidden_profiles_without_disclosure():
    repo = MemorySocialRepository()
    repo.save_profile("usr-a", "privatealice", "Private Alice", False)
    repo.save_profile("usr-b", "publicbob", "Public Bob", True)
    with pytest.raises(SocialNotFound):
        repo.lookup("usr-b", "privatealice")
    with pytest.raises(SocialConflict):
        repo.follow("usr-a", "publicbob")
    with pytest.raises(SocialError):
        repo.save_profile("usr-a", "admin", "Admin Person", True)
    assert repo.me("usr-a")["opted_in"] is False


def test_postgres_social_is_durable_and_message_history_is_owner_scoped():
    dsn = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("Requires SMARTPLOY_TEST_DATABASE_URL")
    PostgresJobRepository(dsn).migrate()
    from psycopg import connect

    a, b, c = ["usr-social-fixture-" + uuid4().hex for _ in range(3)]
    with connect(dsn) as conn, conn.cursor() as cur:
        for user in (a, b, c):
            cur.execute("INSERT INTO smartploy_users(user_id) VALUES(%s)", (user,))
    repo = PostgresSocialRepository(dsn)
    ah, bh, ch = ["social" + uuid4().hex[:13] for _ in range(3)]
    try:
        for user, handle in [(a, ah), (b, bh), (c, ch)]:
            repo.save_profile(user, handle, "Fictional User", True)
        repo.follow(a, bh)
        # A one-way follower is NOT a mutual connection. The followers SQL
        # direction must check the reverse edge, never the same follow.
        one_way = repo.connections(b)
        assert one_way["followers"][0]["handle"] == ah
        assert one_way["followers"][0]["mutual"] is False
        assert repo.connections(a)["following"][0]["mutual"] is False
        with pytest.raises(SocialNotFound):
            repo.send(b, ah, "No reciprocal consent")
        repo.follow(b, ah)
        assert repo.connections(b)["followers"][0]["mutual"] is True
        assert repo.connections(a)["following"][0]["mutual"] is True
        sent = repo.send(a, bh, "Durable private message")
        assert sent["mine"] is True
        again = PostgresSocialRepository(dsn)
        assert again.messages(b, ah)["messages"][0]["body"] == "Durable private message"
        with pytest.raises(SocialNotFound):
            again.messages(c, bh)
        again.block(b, ah)
        with pytest.raises(SocialNotFound):
            repo.send(a, bh, "Denied")
        # Hiding the account must revoke mutual follow rather than leave a
        # latent relationship that reactivates when discoverability returns.
        again.block(b, ah, False)
        again.follow(a, bh)
        again.follow(b, ah)
        again.save_profile(b, bh, "Fictional User", False)
        assert again.connections(a)["following"] == []
        again.save_profile(b, bh, "Fictional User", True)
        with pytest.raises(SocialNotFound):
            repo.send(a, bh, "Not reauthorized")
        assert again.connections(a)["following"] == []
    finally:
        with connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM smartploy_users WHERE user_id = ANY(%s)",
                        ([a, b, c],))

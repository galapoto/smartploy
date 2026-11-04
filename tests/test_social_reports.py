"""SP128: recipient-only reports, operator-only review and durable moderation ledger.

Fictional accounts and messages; no actual user content or external actions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.identity import stable_user_id
from smartploy.service import SmartployService
from smartploy.social_network import (
    DirectMessage, MemorySocialRepository, PostgresSocialRepository,
)
from smartploy.social_reports import (
    DAILY_REPORT_LIMIT, MemorySocialReportRepository,
    PostgresSocialReportRepository, ReportNotFound, ReportRateLimited,
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


def h(account: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": account}


def fixture_app(monkeypatch, operator: str = "") -> TestClient:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER",
                       "https://example.cloudflareaccess.com")
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-fixture")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "same@example.invalid")
    monkeypatch.setenv("SMARTPLOY_OPERATOR_USER_IDS", operator)
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    return TestClient(create_app(SmartployService(), access_verifier=SyntheticVerifier()))


def enabled_profile(handle: str) -> dict[str, object]:
    return {"handle": handle, "display_name": "Fictional " + handle,
            "discoverable": True}


def send_abusive_fixture(api: TestClient) -> str:
    for who, handle in (("a", "alice_job"), ("b", "bob_job"),
                        ("c", "charlie_job")):
        r = api.put("/api/v1/social/me", json=enabled_profile(handle),
                    headers=h(who))
        assert r.status_code == 200, r.text
    assert api.post("/api/v1/social/people/bob_job/follow",
                    headers=h("a")).status_code == 200
    assert api.post("/api/v1/social/people/alice_job/follow",
                    headers=h("b")).status_code == 200
    msg = api.post("/api/v1/social/messages/bob_job",
                   json={"body": "Synthetic suspicious job fee request"},
                   headers=h("a"))
    assert msg.status_code == 201, msg.text
    return msg.json()["message"]["message_id"]


def test_received_message_report_after_block_and_private_history(monkeypatch):
    api = fixture_app(monkeypatch)
    message_id = send_abusive_fixture(api)
    path = "/api/v1/social/reports/messages/" + message_id
    assert api.post(path, json={"reason": "scam"}).status_code == 401
    assert api.post(path, json={"reason": "scam"}, headers=h("a")).status_code == 404
    assert api.post(path, json={"reason": "scam"}, headers=h("c")).status_code == 404
    assert api.post("/api/v1/social/people/alice_job/block",
                    headers=h("b")).status_code == 200
    submitted = api.post(path, json={"reason": "scam",
                                     "note": "Asked me for money"},
                         headers=h("b"))
    assert submitted.status_code == 201, submitted.text
    report = submitted.json()["report"]
    assert submitted.json()["created"] is True
    assert report["reason"] == "scam" and report["state"] == "open"
    assert "@" not in str(report) and "money" not in str(report)
    assert submitted.headers["cache-control"] == "private, no-store"
    assert api.post(path, json={"reason": "spam"}, headers=h("b")).json()[
        "created"] is False
    own = api.get("/api/v1/social/reports/me", headers=h("b")).json()
    assert len(own["reports"]) == 1 and own["reports"][0]["reason"] == "scam"
    assert own["private"] is True
    assert api.get("/api/v1/social/reports/me", headers=h("a")).json()[
        "reports"] == []
    assert api.get("/api/v1/social/moderation/reports",
                   headers=h("b")).status_code == 403
    assert api.post("/api/v1/social/moderation/reports/" +
                    report["report_id"] + "/review", headers=h("b")).status_code == 403
    assert api.get("/api/v1/social/moderation/capabilities",
                   headers=h("b")).json()["operator"] is False


def test_message_report_is_identity_preconditioned_and_bounded(monkeypatch):
    api = fixture_app(monkeypatch)
    message_id = send_abusive_fixture(api)
    path = "/api/v1/social/reports/messages/" + message_id
    assert api.post(path, json={"reason": "scam"}, headers={
        **h("b"), "X-Smartploy-Expected-User-Id": "usr-someone-else"
    }).status_code == 409
    for payload in [
        {"reason": "unknown"}, {"reason": "spam", "note": "A" * 501},
        {"reason": "spam", "note": "\x00"},
        {"reason": "spam", "reporter_id": "usr-a"},
        {"reason": "spam", "message_id": message_id},
    ]:
        assert api.post(path, json=payload, headers=h("b")).status_code == 422
    assert api.post("/api/v1/social/reports/messages/not-an-id",
                    json={"reason": "spam"}, headers=h("b")).status_code == 404


def test_allowlisted_operator_has_review_inbox_and_recorded_disposition(monkeypatch):
    operator_id = stable_user_id("https://example.cloudflareaccess.com", "social-c")
    api = fixture_app(monkeypatch, operator_id)
    msg_id = send_abusive_fixture(api)
    report = api.post("/api/v1/social/reports/messages/" + msg_id,
                      json={"reason": "harassment", "note": "Repeated unwanted pressure"},
                      headers=h("b")).json()["report"]
    assert api.get("/api/v1/social/moderation/capabilities", headers=h("c")
                   ).json()["operator"] is True
    queue = api.get("/api/v1/social/moderation/reports", headers=h("c"))
    assert queue.status_code == 200
    assert queue.headers["cache-control"] == "private, no-store"
    entry = queue.json()["reports"][0]
    assert entry["reported_handle"] == "alice_job"
    assert entry["reporter_handle"] == "bob_job"
    assert "Synthetic suspicious" in entry["message_preview"]
    assert entry["note"] == "Repeated unwanted pressure"
    assert entry["state"] == "open"
    assert "same@example.invalid" not in str(queue.json())
    path = "/api/v1/social/moderation/reports/" + report["report_id"] + "/review"
    assert api.post(path, headers=h("b")).status_code == 403
    res = api.post(path, headers=h("c"))
    assert res.status_code == 200 and res.json()["state"] == "reviewed"
    assert res.json()["reviewed_at"]
    assert api.post(path, headers=h("c")).status_code == 200  # idempotent
    own = api.get("/api/v1/social/reports/me", headers=h("b")).json()
    assert own["reports"][0]["state"] == "reviewed"
    assert api.get("/api/v1/social/moderation/reports",
                   headers=h("a")).status_code == 403
    assert api.get("/api/v1/social/moderation/reports?limit=0",
                   headers=h("c")).status_code == 422
    assert api.post("/api/v1/social/moderation/reports/report-invalid/review",
                    headers=h("c")).status_code == 404


def test_daily_limit_and_idempotence_in_memory():
    social = MemorySocialRepository()
    repo = MemorySocialReportRepository(social)
    now = datetime.now(timezone.utc).isoformat()
    ids = []
    for i in range(DAILY_REPORT_LIMIT + 1):
        msg_id = "msg-" + uuid4().hex
        ids.append(msg_id)
        social._messages.append(DirectMessage(
            msg_id, "usr-sender", "usr-recipient", f"Fictional message {i}", now
        ))
    for msg_id in ids[:DAILY_REPORT_LIMIT]:
        result = repo.submit("usr-recipient", msg_id, "spam")
        assert result["created"] is True
    assert repo.submit("usr-recipient", ids[0], "scam")["created"] is False
    with pytest.raises(ReportRateLimited):
        repo.submit("usr-recipient", ids[-1], "spam")
    with pytest.raises(ReportNotFound):
        repo.submit("usr-sender", ids[-1], "spam")
    assert len(repo.my_reports("usr-recipient")["reports"]) == DAILY_REPORT_LIMIT


def test_postgres_report_persists_and_operator_review_is_private():
    dsn = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("Requires SMARTPLOY_TEST_DATABASE_URL")
    PostgresJobRepository(dsn).migrate()
    from psycopg import connect

    a, b, moderator = ["usr-sp128-" + uuid4().hex for _ in range(3)]
    ah, bh = ["report" + uuid4().hex[:14] for _ in range(2)]
    with connect(dsn) as conn, conn.cursor() as cur:
        for user in (a, b, moderator):
            cur.execute("INSERT INTO smartploy_users(user_id) VALUES(%s)", (user,))
    try:
        social = PostgresSocialRepository(dsn)
        social.save_profile(a, ah, "Fictional Reporter Sender", True)
        social.save_profile(b, bh, "Fictional Reporter Receiver", True)
        social.follow(a, bh)
        social.follow(b, ah)
        sent = social.send(a, bh, "Fictional unsafe offer")
        message_id = sent["message_id"]
        reports = PostgresSocialReportRepository(dsn)
        with pytest.raises(ReportNotFound):
            reports.submit(a, message_id, "scam")
        result = reports.submit(b, message_id, "scam", "Asked for a fee")
        assert result["created"] is True
        report_id = result["report"]["report_id"]
        again = PostgresSocialReportRepository(dsn)
        assert again.submit(b, message_id, "spam")["created"] is False
        social.block(b, ah)
        assert again.my_reports(b)["reports"][0]["report_id"] == report_id
        assert again.my_reports(a)["reports"] == []
        operator_view = again.moderator_queue()["reports"][0]
        assert operator_view["message_preview"] == "Fictional unsafe offer"
        assert operator_view["note"] == "Asked for a fee"
        assert again.mark_reviewed(moderator, report_id)["state"] == "reviewed"
        assert reports.my_reports(b)["reports"][0]["state"] == "reviewed"
    finally:
        with connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM smartploy_users WHERE user_id = ANY(%s)",
                        ([a, b, moderator],))

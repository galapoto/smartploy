"""Synthetic Cloudflare identities share an email but never share consent."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from smartploy.access import AccessPrincipal
from smartploy.api import create_app
from smartploy.domain import SourceObservation, SourcePolicy
from smartploy.identity import AuthenticatedPrincipal
from smartploy.service import SmartployService


class SameEmailVerifier:
    def verify(self, token: str) -> AccessPrincipal:
        if token not in {"a", "b"}:
            raise ValueError("Unknown synthetic user")
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer="https://access.example.invalid",
            subject="synthetic-subject-" + token,
            audience="fixture",
            email="shared@example.invalid",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            key_id="synthetic",
        )


def _client(monkeypatch) -> tuple[TestClient, str, str]:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", "https://access.example.invalid")
    monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "fixture")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "shared@example.invalid")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    service = SmartployService()
    service.register_source(SourcePolicy(
        source_id="synthetic-feed", display_name="Synthetic Feed",
        source_class="company_careers", allowed_modes=("feed",),
    ))

    def add_job(suffix: str, allowed: bool) -> str:
        discovered = service.ingest(SourceObservation(
            source_id="synthetic-feed", source_mode="feed",
            source_url="https://jobs.example.invalid/" + suffix,
            raw_text="Fictional Python engineering job",
            payload={
                "company": "Fictional Employer " + suffix,
                "role_title": "Python Developer",
                "description": "Python engineering",
                "location": "Helsinki", "requirements": ["Python"],
                "external_ai_forwarding_allowed": allowed,
            },
            observed_at="2026-10-17T09:00:00+00:00",
        ))
        assert discovered.candidate is not None
        return discovered.candidate.canonical_key

    allowed = add_job("allowed", True)
    blocked = add_job("blocked", False)
    return TestClient(create_app(service, access_verifier=SameEmailVerifier())), allowed, blocked


def _headers(user: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": user}


def _grant(key: str, consent=True) -> dict:
    return {"canonical_key": key, "acknowledge_obumai_processing": consent}


def _approve_fact(api: TestClient, headers: dict[str, str], kind="skill", value="Python"):
    response = api.post("/api/v1/profile/facts", headers=headers, json={
        "fact_type": kind, "value": value, "approved": True,
    })
    assert response.status_code == 201, response.text


def test_explicit_scoped_consent_is_private_revocable_and_audited(monkeypatch):
    api, key, _ = _client(monkeypatch)
    a, b = _headers("a"), _headers("b")
    base = "/api/v1/ai-processing-consents"
    assert api.get(base).status_code == 401
    assert api.post(base, json=_grant(key)).status_code == 401
    assert api.delete(base + "/missing").status_code == 401
    assert api.post(base, headers=a, json=_grant(key)).status_code == 409
    _approve_fact(api, a)

    for value in [False, "true", 1, None, [], {}]:
        assert api.post(base, headers=a, json=_grant(key, value)).status_code == 422
    assert api.post(base, headers=a, json={
        **_grant(key), "authorize_employer_submission": True,
    }).status_code == 422

    result = api.post(base, headers=a, json=_grant(key))
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "private, no-store"
    rec = result.json()["consent"]
    assert rec["active"] is True and rec["revision"] == 1
    assert rec["mode"] == "unattended" and rec["purpose"] == "application_draft"
    assert result.json()["processing_started"] is False
    assert result.json()["external_actions_authorized"] is False
    assert "user_id" not in rec and "email" not in rec
    again = api.post(base, headers=a, json=_grant(key))
    assert again.status_code == 200
    assert again.json()["created_or_updated"] is False
    assert again.json()["consent"]["revision"] == 1

    mine = api.get(base, headers=a)
    assert mine.status_code == 200 and mine.json()["count"] == 1
    assert mine.json()["unattended_processing_enabled"] is False
    assert api.get(base, headers=b).json()["consents"] == []
    assert api.get(base + "/events", headers=b).json()["events"] == []
    assert api.delete(base + "/" + rec["consent_id"], headers=b).status_code == 404
    revoked = api.delete(base + "/" + rec["consent_id"], headers=a)
    assert revoked.status_code == 200
    assert revoked.json()["consent"]["active"] is False
    assert revoked.json()["consent"]["revision"] == 2
    assert revoked.json()["future_processing_authorized"] is False
    assert api.delete(base + "/" + rec["consent_id"], headers=a).json()[
        "consent"
    ]["revision"] == 2
    events = api.get(base + "/events", headers=a)
    assert events.status_code == 200
    assert events.json()["history_type"] == "consent_grant_and_withdrawal_only"
    assert {row["event_type"] for row in events.json()["events"]} == {
        "granted", "revoked",
    }
    assert events.json()["count"] == 2
    renewed = api.post(base, headers=a, json=_grant(key))
    assert renewed.status_code == 200 and renewed.json()["consent"]["revision"] == 3
    assert api.get(base + "/events", headers=a).json()["count"] == 3


def test_consent_invalidates_changed_evidence_and_restricted_source(monkeypatch):
    api, key, blocked_key = _client(monkeypatch)
    a = _headers("a")
    _approve_fact(api, a)
    repo = api.app.state.processing_consents
    assert api.post("/api/v1/ai-processing-consents", headers=a, json=_grant(
        blocked_key,
    )).status_code == 409
    grant = api.post("/api/v1/ai-processing-consents", headers=a, json=_grant(key))
    assert grant.status_code == 200
    first = grant.json()["consent"]
    binding = api.app.state.identity_repository.resolve_or_create(
        AuthenticatedPrincipal(
            issuer="https://access.example.invalid",
            subject="synthetic-subject-a",
            email="shared@example.invalid", auth_source="cloudflare_access",
        )
    )
    assert repo.authorized(
        binding, key, first["job_snapshot_sha256"], first["evidence_sha256"]
    )
    assert not repo.authorized(
        binding, key, "1" * 64, first["evidence_sha256"]
    )
    assert not repo.authorized(
        binding, key, first["job_snapshot_sha256"], "2" * 64
    )

    _approve_fact(api, a, kind="experience", value="Synthetic Python projects")
    new = api.post("/api/v1/ai-processing-consents", headers=a, json=_grant(key))
    assert new.status_code == 200
    updated = new.json()["consent"]
    assert updated["revision"] == 2
    assert updated["evidence_sha256"] != first["evidence_sha256"]
    assert not repo.authorized(
        binding, key, first["job_snapshot_sha256"], first["evidence_sha256"]
    )
    assert repo.authorized(
        binding, key, updated["job_snapshot_sha256"], updated["evidence_sha256"]
    )
    assert api.get("/api/v1/ai-processing-consents/events", headers=a).json()[
        "count"
    ] == 2


@pytest.mark.parametrize("value", [0, -1, 101])
def test_consent_api_limits_are_bounded(monkeypatch, value):
    api, _, _ = _client(monkeypatch)
    a = _headers("a")
    for path in ("/api/v1/ai-processing-consents", "/api/v1/ai-processing-consents/events"):
        assert api.get(f"{path}?limit={value}", headers=a).status_code == 422

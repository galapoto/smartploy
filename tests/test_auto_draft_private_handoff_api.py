"""SP58: only an authenticated, same-origin owner gets new private kit IDs.

Synthetic account identities; no real job lookup, model, employer or database.
The actual source ranking and Postgres workspace storage have independent
coverage in test_auto_draft_shortlist.py.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.auto_draft_shortlist import AutoDraftSummary
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


API = importlib.import_module("smartploy.api")
ORIGIN = "https://smartploy.komplyint.fi"


def test_sp58_exact_private_review_handoff_cannot_cross_authenticated_owner(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.komplyint.fi")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", "https://auth.komplyint.fi")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic-smartploy-sp58")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
    monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    users = {}
    for label in ("a", "b"):
        principal = AuthenticatedPrincipal(
            issuer="https://auth.komplyint.fi",
            subject="synthetic-private-handoff-" + label,
            email="same-email@example.invalid",
            auth_source="oidc",
        ).normalized()
        binding = identities.resolve_or_create(principal)
        token = sessions.create(
            user_id=binding.user_id,
            principal=principal,
            provider_session_id="synthetic-sp58-" + label,
            ttl_seconds=3600,
        ).token
        users[label] = (binding, token)
    assert users["a"][0].profile_id != users["b"][0].profile_id

    kit_by_profile = {
        users["a"][0].profile_id: "kit-" + "a" * 30,
        users["b"][0].profile_id: "kit-" + "b" * 30,
    }
    engine_calls = []

    def fake_private_engine(profile_id, **kwargs):
        assert kwargs["include_created_workspace_ids"] is True
        engine_calls.append(profile_id)
        return AutoDraftSummary(
            status="prepared", checked=1, eligible=1, created=1,
            created_workspace_ids=(kit_by_profile[profile_id],),
        )

    monkeypatch.setattr(API, "prepare_profile_shortlist", fake_private_engine)
    app = create_app(
        SmartployService(),
        identity_repository=identities, session_repository=sessions,
        oidc_client=object(),
    )
    app.state.search_preferences = SimpleNamespace(get=lambda pid: SimpleNamespace(
        auto_draft_enabled=True, mode="personalized",
    ))

    with TestClient(app, base_url=ORIGIN) as client:
        def post_as(account: str, expected_account: str | None = None, origin: str = ORIGIN):
            binding, token = users[account]
            client.cookies.set(SESSION_COOKIE_NAME, token)
            expected_binding = users[expected_account][0] if expected_account else binding
            return client.post("/api/v1/auto-draft/prepare", headers={
                "Origin": origin,
                "Sec-Fetch-Site": "same-origin",
                "X-Smartploy-Expected-User-Id": expected_binding.user_id,
            }, json={})

        first = post_as("a")
        assert first.status_code == 200, first.text
        assert first.headers["cache-control"] == "private, no-store"
        assert first.json()["created_workspace_ids"] == [kit_by_profile[users["a"][0].profile_id]]
        assert first.json()["automatic_submission_authorized"] is False
        assert first.json()["employer_actions_performed"] is False

        denied = post_as("b", expected_account="a")
        assert denied.status_code == 403
        assert kit_by_profile[users["a"][0].profile_id] not in denied.text
        assert len(engine_calls) == 1

        wrong_origin = post_as("b", origin="https://invalid.example")
        assert wrong_origin.status_code in (403, 400)
        assert len(engine_calls) == 1

        second = post_as("b")
        assert second.status_code == 200, second.text
        assert second.json()["created_workspace_ids"] == [kit_by_profile[users["b"][0].profile_id]]
        assert first.json()["created_workspace_ids"] != second.json()["created_workspace_ids"]
        assert engine_calls == [users["a"][0].profile_id, users["b"][0].profile_id]

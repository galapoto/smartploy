"""SP116 first-party OIDC/private profile API acceptance, synthetic accounts only."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.application_workspace import ApplicationWorkspace
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


ORIGIN = "https://smartploy.komplyint.fi"


def test_sp116_two_oidc_accounts_can_save_profile_questions_but_never_leak(monkeypatch):
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.komplyint.fi")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", "https://identity.example.invalid")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "sp116-oidc-fixture")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
    monkeypatch.setenv(
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out",
    )
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    accounts = {}
    for name in ("a", "b"):
        principal = AuthenticatedPrincipal(
            issuer="https://identity.example.invalid",
            subject="sp116-synthetic-" + name,
            email="same@example.invalid", auth_source="oidc",
        ).normalized()
        binding = identities.resolve_or_create(principal)
        token = sessions.create(
            user_id=binding.user_id, principal=principal,
            provider_session_id="session-sp116-" + name, ttl_seconds=3600,
        ).token
        accounts[name] = (binding, token)
    app = create_app(
        SmartployService(),
        identity_repository=identities,
        session_repository=sessions,
        oidc_client=object(),
    )
    profile_a = accounts["a"][0].profile_id
    workspace = ApplicationWorkspace(
        workspace_id="kit-sp116-private-fixture",
        profile_id=profile_a, canonical_key="sp116-synthetic-draft",
        role_title="Synthetic Junior Analyst", company="Fictional Oy",
        application_url="https://jobs.lever.co/example/synthetic-job",
        cv_text="Fictional synthetic CV", cover_letter_text="Fictional letter",
        source_cv_sha256="a" * 64, approved_evidence_ids=(),
        job_fingerprint="synthetic-non-provider",
        revision=2, status="draft",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    app.state.workspace_repository.create_or_get(workspace)
    with TestClient(app, base_url=ORIGIN) as api:
        def sign_in(name: str):
            binding, token = accounts[name]
            api.cookies.set(SESSION_COOKIE_NAME, token)
            headers = {
                "Origin": ORIGIN, "Sec-Fetch-Site": "same-origin",
                "X-Smartploy-Expected-User-Id": binding.user_id,
            }
            status = api.get("/api/v1/session", headers=headers)
            assert status.status_code == 200
            assert status.json()["user_id"] == binding.user_id
            return headers

        a = sign_in("a")
        initial = api.get("/api/v1/profile/application-questions", headers=a)
        assert initial.status_code == 200
        assert initial.headers["cache-control"] == "private, no-store"
        assert initial.json()["count"] == 0
        assert initial.json()["mode"] == "guided"

        inspection = {
            "workspace_id": workspace.workspace_id, "expected_revision": 2,
            "questions": [
                {"label": "Describe a data project you led",
                 "expected_id": "dataProject",
                 "expected_name": "dataProject", "expected_placeholder": ""},
                {"label": "Do you require visa sponsorship?",
                 "expected_id": "visaStatus",
                 "expected_name": "visaStatus", "expected_placeholder": ""},
            ],
        }
        result = api.post(
            "/api/v1/profile/application-questions/observe",
            headers=a, json=inspection,
        )
        assert result.status_code == 200, result.text
        assert result.json()["remembered_count"] == 1
        assert result.json()["skipped_sensitive_or_duplicate"] == 1
        pending = result.json()["questions"][0]
        assert pending["approved_for_reuse"] is False
        assert pending["answer"] == ""
        assert "visa" not in str(api.get(
            "/api/v1/profile/application-questions", headers=a
        ).json()).lower()

        refused = api.put(
            "/api/v1/profile/application-questions/" + pending["question_key"],
            headers=a, json={
                "answer": "Verified synthetic project", "expected_version": 1,
                "approved_for_reuse": True, "confirm_personally_reviewed": False,
            },
        )
        assert refused.status_code == 422
        approved = api.put(
            "/api/v1/profile/application-questions/" + pending["question_key"],
            headers=a, json={
                "answer": "Verified synthetic project", "expected_version": 1,
                "approved_for_reuse": True, "confirm_personally_reviewed": True,
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["question"]["approved_for_reuse"] is True
        assert approved.json()["question"]["version"] == 2
        assert approved.json()["employer_actions_performed"] == 0

        b = sign_in("b")
        assert api.get(
            "/api/v1/profile/application-questions", headers=b,
        ).json()["questions"] == []
        wrong_owner = api.post(
            "/api/v1/profile/application-questions/observe",
            headers=b, json=inspection,
        )
        assert wrong_owner.status_code == 404
        wrong_save = api.put(
            "/api/v1/profile/application-questions/" + pending["question_key"],
            headers=b, json={
                "answer": "Different user", "expected_version": 2,
                "approved_for_reuse": True, "confirm_personally_reviewed": True,
            },
        )
        assert wrong_save.status_code == 409
        # A's request prepared under A's cookie must be rejected under B's
        # fresh session even though the visible email address is identical.
        old_headers = {**b, "X-Smartploy-Expected-User-Id": a[
            "X-Smartploy-Expected-User-Id"
        ]}
        misbound = api.put(
            "/api/v1/profile/application-mode", headers=old_headers,
            json={"mode": "cv_only"},
        )
        assert misbound.status_code == 409
        assert api.get(
            "/api/v1/profile/application-questions", headers=b,
        ).json()["mode"] == "guided"

        a = sign_in("a")
        cv_only = api.put(
            "/api/v1/profile/application-mode", headers=a,
            json={"mode": "cv_only"},
        )
        assert cv_only.status_code == 200
        assert cv_only.json()["mode"] == "cv_only"
        disabled = api.post(
            "/api/v1/profile/application-questions/observe",
            headers=a, json=inspection,
        )
        assert disabled.status_code == 200
        assert disabled.json()["remembered_count"] == 0
        assert disabled.json()["profile_mode"] == "cv_only"
        assert api.get(
            "/api/v1/profile/application-questions", headers=a,
        ).json()["count"] == 1
        api.put(
            "/api/v1/profile/application-mode", headers=a,
            json={"mode": "guided"},
        )
        deleted = api.delete(
            "/api/v1/profile/application-questions/" + pending["question_key"],
            headers=a,
        )
        assert deleted.status_code == 200 and deleted.json()["deleted"] is True
        assert api.get(
            "/api/v1/profile/application-questions", headers=a,
        ).json()["count"] == 0

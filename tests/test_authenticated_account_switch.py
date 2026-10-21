"""Synthetic two-account cookie/assertion switch regression for private writes.

This tests *two authenticated accounts* (including matching email addresses)
in Cloudflare, OIDC and hybrid modes, not merely an invented bad account ID.
No production accounts, real CV contents, employer submission or external
identity provider is used.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from smartploy.access import AccessPrincipal, AccessVerificationError
from smartploy.api import create_app
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService


ORIGIN = "https://smartploy.obumai.com"
ACCESS_ISSUER = "https://synthetic.cloudflareaccess.com"
OIDC_ISSUER = "https://auth.obumai.com"
SAME_EMAIL = "shared-account@example.invalid"

FACT_A = {"fact_type": "skill", "value": "Fictional Account A Skill", "approved": True}
FACT_B = {"fact_type": "skill", "value": "Fictional Account B Skill", "approved": False}
PRIVATE_JOB = {
    "company": "Fictional Oy",
    "role_title": "Fictional Analyst",
    "location": "Helsinki",
    "description": "A synthetic user-saved opportunity",
    "application_url": "https://jobs.example.invalid/fictional-role",
}


class SyntheticSwitchingAccessVerifier:
    def verify(self, assertion: str) -> AccessPrincipal:
        if assertion not in {"fixture-account-a", "fixture-account-b"}:
            raise AccessVerificationError("invalid_token", "Synthetic assertion denied")
        now = datetime.now(timezone.utc)
        return AccessPrincipal(
            issuer=ACCESS_ISSUER, subject=assertion, email=SAME_EMAIL,
            audience="smartploy-synthetic", key_id="synthetic",
            issued_at=now - timedelta(seconds=5),
            expires_at=now + timedelta(minutes=5),
        )


def configure(monkeypatch, mode: str) -> None:
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", mode)
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "true" if mode != "oidc" else "false")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)

    if mode != "oidc":
        monkeypatch.setenv("SMARTPLOY_ACCESS_ISSUER", ACCESS_ISSUER)
        monkeypatch.setenv("SMARTPLOY_ACCESS_AUDIENCE", "smartploy-synthetic")
        monkeypatch.setenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", SAME_EMAIL)

    if mode != "cloudflare":
        monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", OIDC_ISSUER)
        monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic-smartploy-client")
        monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
        monkeypatch.setenv(
            "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out"
        )


@pytest.mark.parametrize("mode", ["cloudflare", "oidc", "hybrid"])
def test_real_authenticated_account_switch_cannot_apply_old_private_writes(monkeypatch, mode):
    """Cookie/assertion A->B switch cannot mutate B with A's saved precondition."""
    configure(monkeypatch, mode)
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()

    tokens: dict[str, str] = {}
    for label in ("a", "b"):
        # Hybrid A uses a Cloudflare assertion while B has an OIDC cookie.
        if mode == "cloudflare" or (mode == "hybrid" and label == "a"):
            continue
        principal = AuthenticatedPrincipal(
            issuer=OIDC_ISSUER, subject="synthetic-account-" + label,
            email=SAME_EMAIL, auth_source="oidc",
        ).normalized()
        binding = identities.resolve_or_create(principal)
        tokens[label] = sessions.create(
            user_id=binding.user_id,
            principal=principal,
            provider_session_id="synthetic-session-" + label,
            ttl_seconds=3600,
        ).token

    app = create_app(
        SmartployService(),
        identity_repository=identities,
        session_repository=sessions,
        access_verifier=SyntheticSwitchingAccessVerifier() if mode != "oidc" else None,
        oidc_client=object(),
    )

    with TestClient(app, base_url=ORIGIN) as client:
        def as_account(label: str) -> dict[str, str]:
            headers = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
            if mode == "cloudflare":
                headers["Cf-Access-Jwt-Assertion"] = "fixture-account-" + label
            elif mode == "oidc":
                client.cookies.set(SESSION_COOKIE_NAME, tokens[label])
            else:
                # Hybrid must prefer B's valid OIDC cookie to the otherwise
                # valid assertion for A. Removing it returns to A as CF.
                if label == "a":
                    client.cookies.delete(SESSION_COOKIE_NAME) if tokens.get("_set") else None
                    tokens.pop("_set", None)
                else:
                    client.cookies.set(SESSION_COOKIE_NAME, tokens[label])
                    tokens["_set"] = "yes"
                headers["Cf-Access-Jwt-Assertion"] = "fixture-account-a"
            return headers

        def bound(headers: dict[str, str], user_id: str) -> dict[str, str]:
            return {**headers, "X-Smartploy-Expected-User-Id": user_id}

        # Step 1: A has verified credentials and creates private state.
        headers_a = as_account("a")
        session_a = client.get("/api/v1/session", headers=headers_a)
        assert session_a.status_code == 200, session_a.text
        user_a = session_a.json()["user_id"]
        profile_a = session_a.json()["profile_id"]

        fact_a = client.post(
            "/api/v1/profile/facts", headers=bound(headers_a, user_a), json=FACT_A
        )
        assert fact_a.status_code == 201, fact_a.text

        saved_a = client.post(
            "/api/v1/private-jobs", headers=bound(headers_a, user_a), json=PRIVATE_JOB
        )
        assert saved_a.status_code == 201, saved_a.text
        a_preferences = client.get("/api/v1/search-preferences", headers=headers_a).json()
        saved_search_a = client.put(
            "/api/v1/search-preferences", headers=bound(headers_a, user_a),
            json={"mode": "general", "roles": [], "keywords": [],
                  "expected_revision": a_preferences["revision"]},
        )
        assert saved_search_a.status_code == 200, saved_search_a.text

        # Step 2: B logs in with the SAME email, but distinct issuer/subject.
        # The pending A write was already composed with A's verified user_id.
        headers_b = as_account("b")
        session_b = client.get("/api/v1/session", headers=headers_b)
        assert session_b.status_code == 200, session_b.text
        assert session_b.json()["email"] == session_a.json()["email"] == SAME_EMAIL
        user_b = session_b.json()["user_id"]
        assert user_a != user_b
        assert profile_a != session_b.json()["profile_id"]

        b_facts_before = client.get("/api/v1/profile/facts", headers=headers_b).json()
        b_jobs_before = client.get("/api/v1/private-jobs", headers=headers_b).json()
        b_preferences_before = client.get(
            "/api/v1/search-preferences", headers=headers_b
        ).json()
        assert b_facts_before["count"] == b_jobs_before["count"] == 0

        wrong_account_writes = [
            ("POST", "/api/v1/profile/facts", FACT_A),
            ("POST", "/api/v1/private-jobs", PRIVATE_JOB),
            ("PUT", "/api/v1/search-preferences", {
                "mode": "general", "roles": [], "keywords": [],
                "expected_revision": b_preferences_before["revision"],
            }),
            ("POST", "/api/v1/jobs/synthetic-job/application-workspace", None),
            ("DELETE", "/api/v1/profile/cv", None),
        ]
        for method, path, payload in wrong_account_writes:
            result = client.request(
                method, path, headers=bound(headers_b, user_a),
                **({"json": payload} if payload is not None else {}),
            )
            assert result.status_code == 409, (mode, method, path, result.text)
            assert result.json()["error"]["code"] == "account_precondition_failed"
            assert result.headers["cache-control"] == "no-store"

        # None of A's delayed requests was authorized in B's private state.
        assert client.get("/api/v1/profile/facts", headers=headers_b).json() == b_facts_before
        assert client.get("/api/v1/private-jobs", headers=headers_b).json() == b_jobs_before
        assert (
            client.get("/api/v1/search-preferences", headers=headers_b).json()
            == b_preferences_before
        )
        assert client.get("/api/v1/application-workspaces", headers=headers_b).json()[
            "workspaces"
        ] == []

        # Step 3: B's own authenticated, account-bound mutation is permitted.
        added_b = client.post(
            "/api/v1/profile/facts", headers=bound(headers_b, user_b), json=FACT_B
        )
        assert added_b.status_code == 201, added_b.text
        b_facts = client.get("/api/v1/profile/facts", headers=headers_b).json()["facts"]
        assert len(b_facts) == 1 and b_facts[0]["value"] == FACT_B["value"]

        # Step 4: Switch back to A. A's records persist; B's remain separate.
        headers_a = as_account("a")
        returned_a = client.get("/api/v1/session", headers=headers_a).json()
        assert returned_a["user_id"] == user_a
        a_facts = client.get("/api/v1/profile/facts", headers=headers_a).json()["facts"]
        assert len(a_facts) == 1 and a_facts[0]["value"] == FACT_A["value"]
        a_jobs = client.get("/api/v1/private-jobs", headers=headers_a).json()["jobs"]
        assert len(a_jobs) == 1 and a_jobs[0]["company"] == PRIVATE_JOB["company"]
        assert client.get("/api/v1/search-preferences", headers=headers_a).json()[
            "mode"
        ] == "general"


@pytest.mark.parametrize("mode", ["cloudflare", "oidc"])
def test_expected_account_header_does_not_authenticate_anonymous_requests(monkeypatch, mode):
    """A client-controlled user ID cannot replace Cloudflare/OIDC credentials."""
    configure(monkeypatch, mode)
    with TestClient(create_app(
        SmartployService(),
        identity_repository=MemoryIdentityRepository(),
        session_repository=MemorySessionRepository(),
        access_verifier=SyntheticSwitchingAccessVerifier() if mode == "cloudflare" else None,
        oidc_client=object(),
    ), base_url=ORIGIN) as client:
        denied = client.post(
            "/api/v1/profile/facts",
            headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin",
                     "X-Smartploy-Expected-User-Id": "usr-forged-unauthenticated"},
            json=FACT_B,
        )
        assert denied.status_code == 401, denied.text
        assert denied.headers["cache-control"] == "no-store"

"""Real PostgreSQL + OIDC binary-download isolation for the SP101-SP107 RC.

This integration gate uses only synthetic identities/documents. It never
connects to production, contacts an employer or authorizes a submission.
The database's workspace_id PRIMARY KEY differs intentionally from the
in-memory mock: duplicate opaque IDs must be rejected on INSERT.
"""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import os
from uuid import uuid4
from zipfile import ZipFile

from docx import Document
from fastapi.testclient import TestClient
from psycopg import connect, errors
from pypdf import PdfReader
import pytest

from smartploy.api import create_app
from smartploy.application_workspace import ApplicationWorkspace
from smartploy.application_workspace_storage import PostgresWorkspaceRepository
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.oidc import PostgresSessionRepository, SESSION_COOKIE_NAME
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="isolated test PostgreSQL DSN required")

ORIGIN = "https://smartploy.obumai.com"
ISSUER = "https://auth.obumai.com"
EMAIL = "rc-same-email@example.invalid"


def _document(profile_id: str, workspace_id: str, *, label: str, revision: int) -> ApplicationWorkspace:
    return ApplicationWorkspace(
        workspace_id=workspace_id,
        profile_id=profile_id,
        canonical_key="rc-pg-" + workspace_id,
        role_title="Synthetic Data Analyst",
        company="Synthetic Employer Oy",
        application_url="https://jobs.example.invalid/rc-database",
        cv_text=f"SYNTHETIC POSTGRES OWNER {label} CV\nSQL and analysis",
        cover_letter_text=(
            f"SYNTHETIC POSTGRES OWNER {label} LETTER\n"
            "Dear Hiring Team, this is fictional reviewed applicant prose."
        ),
        source_cv_sha256="a" * 64,
        approved_evidence_ids=(),
        job_fingerprint="synthetic-rc-" + workspace_id,
        revision=revision,
        status="draft",
        created_at="2026-11-02T00:00:00+00:00",
        updated_at="2026-11-02T00:00:00+00:00",
    )


def _pdf_text(data: bytes) -> str:
    assert data.startswith(b"%PDF-")
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)


def _docx_text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)


def test_rc_real_postgres_oidc_pdf_and_zip_never_cross_owner(monkeypatch):
    """A and B share an EMAIL but have distinct authenticated OIDC subjects.

    Exercise the actual PostgreSQL repositories and FastAPI PDF + ZIP GETs,
    including exact revision, original standalone downloads, and anonymous
    denial. This proves source behavior only, not live sign-in on OVH.
    """
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "oidc")
    monkeypatch.setenv("SMARTPLOY_ACCESS_ENABLED", "false")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SMARTPLOY_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "synthetic-rc-app")
    monkeypatch.setenv("SMARTPLOY_OIDC_REDIRECT_URI", ORIGIN + "/auth/callback")
    monkeypatch.setenv("SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI", ORIGIN + "/auth/logged-out")
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", DSN)

    PostgresJobRepository(DSN).migrate()
    identity_repository = PostgresIdentityRepository(DSN)
    session_repository = PostgresSessionRepository(DSN)
    workspace_repository = PostgresWorkspaceRepository(DSN)

    marker = uuid4().hex[:18]
    users: list[str] = []
    tokens: dict[str, str] = {}
    profiles: dict[str, str] = {}
    workspace_ids = {
        "A": "kit-rc-pg-" + marker + "-a",
        "B": "kit-rc-pg-" + marker + "-b",
    }
    try:
        for label in ("A", "B"):
            principal = AuthenticatedPrincipal(
                issuer=ISSUER, subject=f"rc-pg-{marker}-{label}",
                email=EMAIL, auth_source="oidc",
            ).normalized()
            bound = identity_repository.resolve_or_create(principal)
            profiles[label] = bound.profile_id
            users.append(bound.user_id)
            tokens[label] = session_repository.create(
                user_id=bound.user_id, principal=principal,
                provider_session_id="rc-pg-" + marker + label,
                ttl_seconds=900,
            ).token
            saved, created = workspace_repository.create_or_get(
                _document(bound.profile_id, workspace_ids[label], label=label, revision=2)
            )
            assert created is True
            assert saved.profile_id == bound.profile_id

        assert len(set(users)) == 2
        assert profiles["A"] != profiles["B"]
        assert workspace_repository.get(profiles["A"], workspace_ids["B"]) is None
        assert workspace_repository.get(profiles["B"], workspace_ids["A"]) is None

        # Production PostgreSQL has workspace_id TEXT PRIMARY KEY, not the
        # duplicate-ID capability of MemoryWorkspaceRepository. Check that
        # a distinct owner cannot insert/reuse a colliding opaque identifier.
        duplicate_id = _document(
            profiles["B"], workspace_ids["A"], label="B", revision=2
        )
        with pytest.raises(errors.UniqueViolation):
            workspace_repository.create_or_get(
                replace(duplicate_id, canonical_key="rc-pg-collision-" + marker)
            )

        app = create_app(
            SmartployService(),
            identity_repository=identity_repository,
            session_repository=session_repository,
            oidc_client=object(),
        )
        assert isinstance(app.state.workspace_repository, PostgresWorkspaceRepository)
        with TestClient(app, base_url=ORIGIN) as client:
            for label in ("A", "B"):
                other = "B" if label == "A" else "A"
                client.cookies.set(SESSION_COOKIE_NAME, tokens[label])
                signed_in = client.get("/api/v1/session")
                assert signed_in.status_code == 200
                assert signed_in.json()["user_id"] == users[("A", "B").index(label)]
                assert signed_in.json()["email"] == EMAIL
                own_id = workspace_ids[label]
                other_id = workspace_ids[other]
                expected = f"SYNTHETIC POSTGRES OWNER {label}"
                forbidden = f"SYNTHETIC POSTGRES OWNER {other}"

                for kind in ("cv", "letter"):
                    preview = client.get(
                        f"/api/v1/application-workspaces/{own_id}/preview/"
                        f"{kind}/pdf?expected_revision=2"
                    )
                    assert preview.status_code == 200, (label, kind, preview.text)
                    assert preview.headers["cache-control"] == "private, no-store"
                    assert preview.headers["content-type"].startswith("application/pdf")
                    assert preview.headers["content-disposition"].startswith("inline;")
                    assert preview.headers["x-content-type-options"] == "nosniff"
                    content = _pdf_text(preview.content)
                    assert expected in content and forbidden not in content

                    # Older standalone downloads use the same owner guard.
                    downloaded = client.get(
                        f"/api/v1/application-workspaces/{own_id}/download/{kind}/docx"
                        "?expected_revision=2"
                    )
                    assert downloaded.status_code == 200
                    text = _docx_text(downloaded.content)
                    assert expected in text and forbidden not in text
                    assert client.get(
                        f"/api/v1/application-workspaces/{own_id}/download/{kind}/docx"
                        "?expected_revision=1"
                    ).status_code == 409

                    assert client.get(
                        f"/api/v1/application-workspaces/{other_id}/preview/"
                        f"{kind}/pdf?expected_revision=2"
                    ).status_code == 404

                package = client.get(
                    f"/api/v1/application-workspaces/{own_id}/download/package.zip"
                    "?expected_revision=2"
                )
                assert package.status_code == 200, (label, package.text)
                assert package.headers["cache-control"] == "private, no-store"
                with ZipFile(BytesIO(package.content)) as bundle:
                    names = bundle.namelist()
                    assert len(names) == 5
                    assert "README-NOT-SUBMITTED.txt" in names
                    for kind in ("cv", "letter"):
                        for format in ("pdf", "docx"):
                            member = next(n for n in names if n.endswith(f"-{kind}.{format}"))
                            text = (
                                _pdf_text(bundle.read(member)) if format == "pdf"
                                else _docx_text(bundle.read(member))
                            )
                            assert expected in text and forbidden not in text
                assert client.get(
                    f"/api/v1/application-workspaces/{own_id}/download/package.zip"
                    "?expected_revision=1"
                ).status_code == 409
                assert client.get(
                    f"/api/v1/application-workspaces/{own_id}/download/package.zip"
                ).status_code == 422
                assert client.get(
                    f"/api/v1/application-workspaces/{other_id}/download/package.zip"
                    "?expected_revision=2"
                ).status_code == 404
                assert client.get(
                    f"/api/v1/application-workspaces/{own_id}/preview/cv/pdf"
                    "?expected_revision=1"
                ).status_code == 409
                assert client.get("/api/v1/applications/summary").json()[
                    "actually_submitted"
                ] == 0

            client.cookies.clear()
            for path in (
                f"/api/v1/application-workspaces/{workspace_ids['A']}/download/package.zip?expected_revision=2",
                f"/api/v1/application-workspaces/{workspace_ids['B']}/preview/cv/pdf?expected_revision=2",
            ):
                denied = client.get(path)
                assert denied.status_code == 401
                assert denied.headers["cache-control"] == "no-store"
    finally:
        # This is a shared CI test PostgreSQL cluster, not a disposable
        # private schema. Remove only synthetic rows created by this test,
        # with no TRUNCATE and no broad deletion of other candidates' data.
        with connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM smartploy_application_workspaces WHERE workspace_id = ANY(%s)",
                    (list(workspace_ids.values()),),
                )
                if users:
                    cur.execute(
                        "DELETE FROM smartploy_users WHERE user_id = ANY(%s)",
                        (users,),
                    )

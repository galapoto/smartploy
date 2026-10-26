"""Browser-observed employer receipts stay private and never prove submission."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os

from fastapi.testclient import TestClient
import pytest

from smartploy.api import create_app
from smartploy.application_workspace import new_workspace
from smartploy.browser_receipt import ReceiptError, validate_browser_receipt
from smartploy.browser_receipt_storage import (
    MemoryBrowserReceiptRepository, PostgresBrowserReceiptRepository, ReceiptConflict,
)
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import AuthenticatedPrincipal, MemoryIdentityRepository
from smartploy.oidc import MemorySessionRepository, SESSION_COOKIE_NAME
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


JOB = "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply"
TIME = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)


def job():
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual", source_url=JOB,
            raw_text="Data analyst with SQL Python at Upright",
            observed_at="2026-10-11T07:00:00+00:00",
            payload={
                "company": "Upright Project", "role_title": "Data Analyst",
                "description": "SQL and Python", "application_url": JOB
            },
        ),
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    )
    assert result.candidate
    return result.candidate


def kit(pid="p1"):
    profile = CandidateProfile(pid, (
        ProfileFact("identity", "Test Candidate", "user-entered", approved=True).normalized(),
    ))
    draft = new_workspace(job(), profile)
    return replace(
        draft, cover_letter_text="Dear Hiring Team,\nI am interested in your analyst role. "
        "My relevant experience is documented in my reviewed CV.\nRegards,\nTest Candidate",
    )


def import_value(w, *, time=TIME):
    return {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": w.workspace_id,
        "document_revision": w.revision,
        "document_sha256": sha256((w.cv_text + "\0" + w.cover_letter_text).encode("utf-8")).hexdigest(),
        "application_url": w.application_url,
        "confirmation_page_url": JOB + "?token=should-not-store#private",
        "reference": "RECEIPT-123456",
        "confirmation_page_sha256": "f" * 64,
        "observed_at": time.isoformat(),
        "confirmed_visible": True,
    }


def test_accept_recent_receipt_but_never_mark_verified():
    w = kit()
    evidence = validate_browser_receipt(w, import_value(w), now=TIME + timedelta(minutes=2))
    payload = evidence.to_dict()
    assert payload["status"] == "browser_observed_unverified"
    assert payload["reference"] == "RECEIPT-123456"
    assert payload["confirmation_page_url"] == JOB
    assert "token=" not in payload["confirmation_page_url"]
    assert payload["independently_verified_by_employer"] is False
    assert payload["actually_submitted_count_changed"] is False
    assert len(payload["evidence_digest"]) == 64


@pytest.mark.parametrize("key,value", [
    ("schema", "unsupported"),
    ("workspace_id", "kit-" + "b" * 30),
    ("document_revision", 99),
    ("document_revision", True),
    ("document_sha256", "a" * 64),
    ("application_url", "https://jobs.lever.co/different/employer/apply"),
    ("confirmation_page_url", "https://evil.example.com/confirmation"),
    ("confirmation_page_url", "http://jobs.lever.co/uprightproject/confirmation"),
    ("confirmation_page_url", "https://jobs.lever.co/another-company/confirmation"),
    ("reference", "invalid reference here"),
    ("confirmation_page_sha256", "x"),
    ("confirmed_visible", False),
])
def test_invalid_employer_receipt_refused(key, value):
    w = kit()
    data = import_value(w)
    data[key] = value
    with pytest.raises(ReceiptError):
        validate_browser_receipt(w, data, now=TIME + timedelta(minutes=2))


def test_stale_future_or_untimed_observation_refused():
    w = kit()
    for stamp in [
        TIME - timedelta(hours=2),
        TIME + timedelta(hours=2),
    ]:
        with pytest.raises(ReceiptError):
            validate_browser_receipt(w, import_value(w, time=stamp), now=TIME)
    row = import_value(w)
    row["observed_at"] = "2026-10-11T09:00:00"  # naive timezone
    with pytest.raises(ReceiptError):
        validate_browser_receipt(w, row, now=TIME)


def test_receipt_must_match_owned_saved_revision_and_current_draft():
    w = kit()
    with pytest.raises(ReceiptError):
        validate_browser_receipt(
            replace(w, status="self_reported_applied"), import_value(w), now=TIME
        )
    changed = replace(w, cv_text=w.cv_text + "\nAdded later")
    with pytest.raises(ReceiptError, match="digest"):
        validate_browser_receipt(changed, import_value(w), now=TIME)


def test_memory_receipt_single_record_conflict_and_ownership():
    repo = MemoryBrowserReceiptRepository()
    w = kit("person-a")
    a = validate_browser_receipt(w, import_value(w), now=TIME)
    assert repo.record(a) == a
    assert repo.record(a) == a
    assert repo.get("person-b", w.workspace_id) is None
    alternative = replace(a, reference="RECEIPT-OTHER", digest="a" * 64)
    with pytest.raises(ReceiptConflict):
        repo.record(alternative)
    assert repo.delete("person-b", w.workspace_id) is False
    assert repo.delete("person-a", w.workspace_id) is True


def test_authenticated_api_receipt_does_not_increment_submitted_count(monkeypatch):
    svc = SmartployService()
    svc.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    api = TestClient(create_app(svc))
    created = api.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "source_url": JOB, "raw_text": "Analyst job",
            "payload": {"company": "Upright Project", "role_title": "Analyst",
                        "description": "SQL", "application_url": JOB}
        }
    })
    assert created.status_code == 200
    key = created.json()["candidate"]["canonical_key"]
    assert api.post("/api/v1/profile/facts", json={
        "fact_type": "identity", "value": "Test Candidate", "approved": True
    }).status_code == 201
    starting = api.post("/api/v1/jobs/" + key + "/application-workspace")
    assert starting.status_code == 200
    w = starting.json()["workspace"]
    assert api.get(f"/api/v1/application-workspaces/{w['workspace_id']}/browser-receipt").json()["present"] is False

    stamp = datetime.now(timezone.utc)
    raw = {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": w["workspace_id"],
        "document_revision": w["revision"],
        "document_sha256": sha256((w["cv_text"] + "\0" + w["cover_letter_text"]).encode()).hexdigest(),
        "application_url": w["application_url"],
        "confirmation_page_url": JOB + "?tracking=hidden",
        "reference": "TEST-RECEIPT-5678",
        "confirmation_page_sha256": "c" * 64,
        "observed_at": stamp.isoformat(),
        "confirmed_visible": True,
    }
    endpoint = f"/api/v1/application-workspaces/{w['workspace_id']}/browser-receipt"
    assert api.post(endpoint, json={"confirm_user_observed": False, "receipt": raw}).status_code == 422
    response = api.post(endpoint, json={"confirm_user_observed": True, "receipt": raw})
    assert response.status_code == 200, response.text
    assert response.json()["receipt"]["status"] == "browser_observed_unverified"
    assert response.json()["external_confirmation_verified"] is False
    assert "tracking=hidden" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert api.post(endpoint, json={"confirm_user_observed": True, "receipt": raw}).status_code == 200
    changed = dict(raw, reference="DIFFERENT-REFERENCE")
    assert api.post(endpoint, json={"confirm_user_observed": True, "receipt": changed}).status_code == 409
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    frozen = api.put(f"/api/v1/application-workspaces/{w['workspace_id']}", json={
        "expected_revision": w["revision"],
        "cv_text": "Altered after submission", "cover_letter_text": "Altered text",
    })
    assert frozen.status_code == 409
    assert api.get(
        f"/api/v1/application-workspaces/{w['workspace_id']}/handoff-readiness"
    ).json()["ready"] is False
    assert api.post(
        f"/api/v1/application-workspaces/{w['workspace_id']}/browser-packet",
        json={"expected_revision": w["revision"], "confirm_private_data_transfer": True},
    ).status_code == 409
    assert api.post(
        f"/api/v1/application-workspaces/{w['workspace_id']}/ai-suggestions",
        json={"expected_revision": w["revision"], "acknowledge_local_ai_processing": True},
    ).status_code == 409
    assert api.delete(f"/api/v1/application-workspaces/{w['workspace_id']}").status_code == 200
    assert api.get(endpoint).status_code == 404


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="requires test PostgreSQL")
def test_postgres_ledger_persistence_and_tenant_separation():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    from smartploy.application_workspace_storage import PostgresWorkspaceRepository

    workspaces = PostgresWorkspaceRepository(dsn)
    w = kit("browser-receipt-persist-test")
    workspaces.delete(w.profile_id, w.workspace_id)
    store = PostgresBrowserReceiptRepository(dsn)
    try:
        record, created = workspaces.create_or_get(w)
        assert created is True
        proof = validate_browser_receipt(record, import_value(record), now=TIME)
        saved = store.record(proof)
        assert saved.digest == proof.digest
        assert store.get("some-other-tenant", record.workspace_id) is None
        assert PostgresBrowserReceiptRepository(dsn).get(w.profile_id, w.workspace_id) == saved
        assert store.record(proof) == saved
    finally:
        workspaces.delete(w.profile_id, w.workspace_id)
    assert store.get(w.profile_id, w.workspace_id) is None


# SP42 — The user submitted to Ashby manually; capture only the visible,
# reference-bearing, *same-job* browser observation. Never an employer ACK.
ASHBY = "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application"


def test_sp42_ashby_reference_observation_is_private_unverified_and_strips_tracking():
    w = replace(kit(), application_url=ASHBY)
    raw = import_value(w)
    raw["confirmation_page_url"] = (
        ASHBY + "/confirmation?tracking=secret#access-token"
    )
    receipt = validate_browser_receipt(w, raw, now=TIME)
    assert receipt.reference == "RECEIPT-123456"
    assert receipt.confirmation_page_url == ASHBY + "/confirmation"
    assert "secret" not in str(receipt.to_dict())
    assert receipt.to_dict()["status"] == "browser_observed_unverified"
    assert receipt.to_dict()["independently_verified_by_employer"] is False
    assert receipt.to_dict()["actually_submitted_count_changed"] is False
    assert len(receipt.to_dict()["evidence_digest"]) == 64


@pytest.mark.parametrize("wrong_page", [
    "https://jobs.ashbyhq.com/synthetic-fi/other-job/application/confirmation",
    "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst-evil/application",
    "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application-other",
    "https://jobs.ashbyhq.com/other-board/junior-data-analyst/application",
    "https://jobs.ashbyhq.com.evil.invalid/synthetic-fi/junior-data-analyst/application",
    "https://jobs.lever.co/synthetic-fi/junior-data-analyst/application",
    "https://evil.invalid/synthetic-fi/junior-data-analyst/application",
    "http://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application",
    "https://user:password@jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application",
])
def test_sp42_ashby_receipt_refuses_cross_job_or_untrusted_host(wrong_page):
    w = replace(kit(), application_url=ASHBY)
    raw = import_value(w)
    raw["confirmation_page_url"] = wrong_page
    with pytest.raises(ReceiptError):
        validate_browser_receipt(w, raw, now=TIME)


def test_sp42_ashby_receipt_never_bypasses_reviewed_revision_or_existing_status():
    w = replace(kit(), application_url=ASHBY)
    raw = import_value(w)
    raw["confirmation_page_url"] = ASHBY
    assert validate_browser_receipt(w, raw, now=TIME).status == "browser_observed_unverified"
    for changed in (
        replace(w, cv_text=w.cv_text + "stale"),
        replace(w, status="self_reported_applied"),
        replace(w, revision=w.revision + 1),
    ):
        with pytest.raises(ReceiptError):
            validate_browser_receipt(changed, raw, now=TIME)


def test_sp42_ashby_private_api_observation_does_not_claim_provider_acknowledgment():
    """Existing owner-bound API persists manual Ashby evidence, no new tables."""
    svc = SmartployService()
    svc.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    api = TestClient(create_app(svc))
    posted = api.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "source_url": ASHBY, "raw_text": "Synthetic IT analyst Helsinki",
            "payload": {
                "company": "Synthetic IT", "role_title": "Junior Data Analyst",
                "description": "SQL Python", "application_url": ASHBY,
                "location": "Helsinki",
            },
        }
    })
    assert posted.status_code == 200, posted.text
    key = posted.json()["candidate"]["canonical_key"]
    assert api.post("/api/v1/profile/facts", json={
        "fact_type": "identity", "value": "Test Candidate", "approved": True,
    }).status_code == 201
    prepared = api.post(f"/api/v1/jobs/{key}/application-workspace")
    assert prepared.status_code == 200, prepared.text
    w = prepared.json()["workspace"]
    now = datetime.now(timezone.utc)
    raw = {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": w["workspace_id"],
        "document_revision": w["revision"],
        "document_sha256": sha256(
            (w["cv_text"] + "\0" + w["cover_letter_text"]).encode()
        ).hexdigest(),
        "application_url": ASHBY,
        "confirmation_page_url": ASHBY + "/confirmation?private=discard#secret",
        "reference": "ASHBY-SYNTH-2026",
        "confirmation_page_sha256": "e" * 64,
        "observed_at": now.isoformat(),
        "confirmed_visible": True,
    }
    endpoint = f'/api/v1/application-workspaces/{w["workspace_id"]}/browser-receipt'
    no_consent = api.post(endpoint, json={
        "confirm_user_observed": False, "receipt": raw,
    })
    assert no_consent.status_code == 422
    stored = api.post(endpoint, json={
        "confirm_user_observed": True, "receipt": raw,
    })
    assert stored.status_code == 200, stored.text
    payload = stored.json()
    assert payload["external_confirmation_verified"] is False
    assert payload["receipt"]["status"] == "browser_observed_unverified"
    assert payload["receipt"]["independently_verified_by_employer"] is False
    assert payload["receipt"]["confirmation_page_url"] == ASHBY + "/confirmation"
    assert "private=discard" not in stored.text
    assert "secret" not in stored.text
    assert api.post(endpoint, json={
        "confirm_user_observed": True, "receipt": raw,
    }).status_code == 200
    sibling = {**raw,
        "confirmation_page_url":
        "https://jobs.ashbyhq.com/synthetic-fi/other-job/application"}
    assert api.post(endpoint, json={
        "confirm_user_observed": True, "receipt": sibling,
    }).status_code == 422
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    assert api.get(endpoint).json()["receipt"]["status"] == "browser_observed_unverified"


# SP47 closes the original Lever tenant-wide attribution hole and adds
# manual hosted-Greenhouse observations through the SAME private store.
LEVER_POSTING = JOB.removesuffix("/apply")
GREENHOUSE = "https://boards.greenhouse.io/synthetic-fi/jobs/123456"
GREENHOUSE_MODERN = GREENHOUSE.replace("boards.greenhouse.io", "job-boards.greenhouse.io")


@pytest.mark.parametrize("posting,confirmation,stored", [
    (JOB, LEVER_POSTING, LEVER_POSTING),
    (JOB, LEVER_POSTING + "/", LEVER_POSTING + "/"),
    (JOB, JOB, JOB),
    (LEVER_POSTING, JOB + "/", JOB + "/"),
    (JOB, JOB + "/confirmation/", JOB + "/confirmation/"),
    (JOB, LEVER_POSTING + "/thanks", LEVER_POSTING + "/thanks"),
    (JOB, LEVER_POSTING + "/thanks/", LEVER_POSTING + "/thanks/"),
    (
        JOB.replace("jobs.lever.co", "jobs.eu.lever.co"),
        JOB.replace("jobs.lever.co", "jobs.eu.lever.co") + "/confirmation",
        JOB.replace("jobs.lever.co", "jobs.eu.lever.co") + "/confirmation",
    ),
    (JOB, JOB.replace("jobs.lever.co", "JOBS.LEVER.CO:443"), JOB),
    (GREENHOUSE, GREENHOUSE, GREENHOUSE),
    (GREENHOUSE, GREENHOUSE_MODERN + "/", GREENHOUSE_MODERN + "/"),
    (GREENHOUSE, GREENHOUSE_MODERN + "/confirmation", GREENHOUSE_MODERN + "/confirmation"),
    (GREENHOUSE_MODERN + "/", GREENHOUSE + "/confirmation/", GREENHOUSE + "/confirmation/"),
    (ASHBY, ASHBY + "/confirmation/done/", ASHBY + "/confirmation/done/"),
])
def test_sp47_manual_confirmation_keeps_exact_job_identity(posting, confirmation, stored):
    workspace = replace(kit(), application_url=posting)
    raw = import_value(workspace)
    raw["confirmation_page_url"] = confirmation + "?private=discard#secret"
    receipt = validate_browser_receipt(workspace, raw, now=TIME)
    assert receipt.confirmation_page_url == stored
    assert receipt.status == "browser_observed_unverified"
    assert receipt.to_dict()["independently_verified_by_employer"] is False
    assert receipt.to_dict()["actually_submitted_count_changed"] is False
    assert "discard" not in str(receipt.to_dict())
    assert "secret" not in str(receipt.to_dict())


@pytest.mark.parametrize("posting,confirmation", [
    # A prior attempt for one job must never make another job's receipt fit.
    (JOB, "https://jobs.lever.co/uprightproject/other-job/apply/confirmation"),
    (JOB, "https://jobs.lever.co/uprightproject/thanks"),
    (JOB, LEVER_POSTING + "-sibling/apply"),
    (JOB, LEVER_POSTING + "/application/confirmation"),
    (JOB, LEVER_POSTING + "/thanks/another-job"),
    (JOB, JOB + "-other"),
    (JOB, JOB.replace("jobs.lever.co", "jobs.eu.lever.co")),
    (GREENHOUSE, GREENHOUSE_MODERN.replace("123456", "1234567")),
    (GREENHOUSE, GREENHOUSE_MODERN.replace("synthetic-fi", "other-board")),
    (GREENHOUSE, "https://job-boards.greenhouse.io/synthetic-fi/confirmation"),
    (GREENHOUSE, GREENHOUSE_MODERN + "/confirmation/other-job"),
    (GREENHOUSE, GREENHOUSE_MODERN + "/apply"),
    (GREENHOUSE, GREENHOUSE_MODERN.replace(".io", ".io.evil.invalid")),
    (ASHBY, ASHBY + "-other"),
    (ASHBY, ASHBY.replace("junior-data-analyst", "different-job")),
    (JOB, JOB.replace("https://", "http://")),
    (GREENHOUSE, GREENHOUSE_MODERN.replace("https://", "https://user:password@")),
    (GREENHOUSE, GREENHOUSE_MODERN.replace(".io", ".io:8443")),
])
def test_sp47_receipt_refuses_sibling_jobs_and_unapproved_confirmation_routes(posting, confirmation):
    workspace = replace(kit(), application_url=posting)
    raw = import_value(workspace)
    raw["confirmation_page_url"] = confirmation
    with pytest.raises(ReceiptError):
        validate_browser_receipt(workspace, raw, now=TIME)


@pytest.mark.parametrize("posting", [JOB, ASHBY, GREENHOUSE])
@pytest.mark.parametrize("malicious_suffix", [
    "/../other-job", "/./confirmation", "/%2e%2e/other-job",
    "/%2Fother-job", "\\confirmation", "//confirmation", "/confirmation\t",
])
def test_sp47_receipt_rejects_paths_that_browser_parsers_can_reinterpret(posting, malicious_suffix):
    workspace = replace(kit(), application_url=posting)
    raw = import_value(workspace)
    raw["confirmation_page_url"] = posting + malicious_suffix
    with pytest.raises(ReceiptError):
        validate_browser_receipt(workspace, raw, now=TIME)


@pytest.mark.parametrize("posting", [JOB, ASHBY, GREENHOUSE])
@pytest.mark.parametrize("suffix", ["?source=altered", "#fragment", "\n"])
def test_sp47_expected_posting_cannot_be_normalized_into_a_different_identity(posting, suffix):
    workspace = replace(kit(), application_url=posting + suffix)
    raw = import_value(workspace)
    raw["confirmation_page_url"] = posting
    with pytest.raises(ReceiptError):
        validate_browser_receipt(workspace, raw, now=TIME)


@pytest.mark.parametrize("posting,confirmation", [
    (JOB, LEVER_POSTING + "/thanks"),
    (GREENHOUSE, GREENHOUSE_MODERN + "/confirmation"),
    (ASHBY, ASHBY + "/confirmation"),
])
def test_sp47_oidc_owner_imports_manual_observation_without_any_automated_attempt(
    monkeypatch, posting, confirmation,
):
    """Original middleware, private workspace and receipt API, two OIDC owners.

    In-memory fixture stores isolate the API boundary. PostgreSQL persistence
    remains covered separately above and in the original E2E contract.
    """
    origin = "https://smartploy.komplyint.fi"
    issuer = "https://synthetic-sso.example.invalid"
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    for name, value in {
        "SMARTPLOY_ENVIRONMENT": "production",
        "SMARTPLOY_AUTH_MODE": "oidc",
        "SMARTPLOY_ACCESS_ENABLED": "false",
        "SMARTPLOY_PUBLIC_ORIGIN": origin,
        "SMARTPLOY_ALLOWED_HOSTS": "smartploy.komplyint.fi",
        "SMARTPLOY_OIDC_ISSUER": issuer,
        "SMARTPLOY_OIDC_CLIENT_ID": "synthetic-sp47",
        "SMARTPLOY_OIDC_REDIRECT_URI": origin + "/auth/callback",
        "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI": origin + "/auth/logged-out",
    }.items():
        monkeypatch.setenv(name, value)
    identities = MemoryIdentityRepository()
    sessions = MemorySessionRepository()
    principals = [AuthenticatedPrincipal(
        issuer=issuer, subject=subject, email="same@example.invalid", auth_source="oidc",
    ) for subject in ("sp47-owner", "sp47-other-owner")]
    owners = [identities.resolve_or_create(principal) for principal in principals]
    tokens = [sessions.create(
        user_id=owner.user_id, principal=principal, ttl_seconds=3600,
    ).token for owner, principal in zip(owners, principals)]
    app = create_app(
        SmartployService(), identity_repository=identities,
        session_repository=sessions, oidc_client=object(),
    )
    # Neither a local attempt marker nor an automated employer claim is a
    # prerequisite for a user's private, explicitly unverified observation.
    assert app.state.employer_claims is None
    assert app.state.employer_rights is None

    def forbidden_send(*args, **kwargs):
        pytest.fail("A manual browser observation must never call an employer")

    monkeypatch.setattr(app.state.partner_lever_transport, "send", forbidden_send)
    workspace = replace(kit(owners[0].profile_id), application_url=posting)
    app.state.workspace_repository.create_or_get(workspace)
    endpoint = f"/api/v1/application-workspaces/{workspace.workspace_id}/browser-receipt"
    api = TestClient(app, base_url=origin)
    assert api.get(endpoint).status_code == 401
    raw = import_value(workspace, time=datetime.now(timezone.utc))
    raw["confirmation_page_url"] = confirmation + "?private=discard#secret"
    headers = {"Origin": origin, "Sec-Fetch-Site": "same-origin",
               "X-Smartploy-Expected-User-Id": owners[0].user_id}
    api.cookies.set(SESSION_COOKIE_NAME, tokens[0])
    assert api.get(endpoint).json()["present"] is False
    assert api.post(endpoint, headers=headers, json={
        "confirm_user_observed": False, "receipt": raw,
    }).status_code == 422
    stale = {**raw, "document_revision": workspace.revision + 1}
    assert api.post(endpoint, headers=headers, json={
        "confirm_user_observed": True, "receipt": stale,
    }).status_code == 422
    payload = {"confirm_user_observed": True, "receipt": raw}
    stored = api.post(endpoint, headers=headers, json=payload)
    assert stored.status_code == 200, stored.text
    result = stored.json()
    assert result["external_confirmation_verified"] is False
    assert result["receipt"]["status"] == "browser_observed_unverified"
    assert result["receipt"]["confirmation_page_url"] == confirmation
    assert result["receipt"]["actually_submitted_count_changed"] is False
    assert stored.headers["cache-control"] == "private, no-store"
    assert api.post(endpoint, headers=headers, json=payload).json() == result
    assert api.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    assert app.state.workspace_repository.get(
        owners[0].profile_id, workspace.workspace_id,
    ).status == "draft"

    # An identical email address does not make another OIDC account the owner.
    api.cookies.set(SESSION_COOKIE_NAME, tokens[1])
    assert api.get(endpoint).status_code == 404
    assert api.post(endpoint, headers={**headers,
        "X-Smartploy-Expected-User-Id": owners[1].user_id,
    }, json=payload).status_code == 404
    api.cookies.set(SESSION_COOKIE_NAME, tokens[0])
    assert api.get(endpoint).json()["receipt"] == result["receipt"]
    assert app.state.employer_claims is None
    assert app.state.employer_rights is None

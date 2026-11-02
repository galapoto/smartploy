"""SP120: user-added job -> own reviewed application -> local browser packet.

All applicant identities, employers, files and URLs are synthetic.
No employer network, submission, AI forwarding or authenticated production use.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from smartploy.application_workspace import WorkspaceError, new_workspace
from smartploy.browser_handoff import _assisted_posting_url, review_handoff
from smartploy.private_saved_jobs import (
    MemoryPrivateSavedJobRepository, PrivateSavedJobError, private_candidate,
)
from test_private_saved_jobs import DATA, headers, private_api


EMPLOYER = "https://careers.example.org/jobs/junior-analyst"
TALENTADORE = "https://ats.talentadore.com/apply/junior-analyst/m6rpoy"


def own_api(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.komplyint.fi")
    return private_api(monkeypatch)


def owner_headers(api, account: str) -> tuple[dict[str, str], str]:
    base = headers(account)
    session = api.get("/api/v1/session", headers=base)
    assert session.status_code == 200, session.text
    data = session.json()
    assert data["authenticated"] is True
    return {
        **base,
        "Origin": "https://smartploy.komplyint.fi",
        "Sec-Fetch-Site": "same-origin",
        "X-Smartploy-Expected-User-Id": data["user_id"],
    }, data["profile_id"]


def put_synthetic_cv(api, profile_id: str) -> None:
    api.app.state.cv_repository.put(
        profile_id, "fictional-analyst.pdf", "application/pdf",
        b"%PDF-1.4\nfictional fixture only\n%%EOF",
        "Fictional Applicant\nSQL and Python analysis at Example Oy.",
    )


def test_sp120_saved_bookmark_can_become_private_assisted_draft_without_shared_ingest(monkeypatch):
    api = own_api(monkeypatch)
    a, profile_id = owner_headers(api, "account-a")
    b, _ = owner_headers(api, "account-b")
    created = api.post("/api/v1/private-jobs", headers=a, json={
        **DATA, "application_url": TALENTADORE,
    })
    assert created.status_code == 201, created.text
    saved_id = created.json()["job"]["saved_job_id"]
    path = f"/api/v1/private-jobs/{saved_id}/application-workspace"

    assert api.post(path, headers=a, json={
        "acknowledge_unverified_employer": True,
    }).status_code == 409  # A CV is actually required.
    put_synthetic_cv(api, profile_id)
    assert api.post(path, headers=a, json={
        "acknowledge_unverified_employer": False,
    }).status_code == 422
    assert api.post(path, headers=headers("account-a"), json={
        "acknowledge_unverified_employer": True,
    }).status_code == 403
    assert api.post(path, headers=b, json={
        "acknowledge_unverified_employer": True,
    }).status_code == 404

    created = api.post(path, headers=a, json={
        "acknowledge_unverified_employer": True,
    })
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["created"] is True
    assert data["source"] == "private_saved_unverified"
    assert data["employer_verified"] is False
    assert data["final_submit_authorized"] is False
    assert data["external_actions_performed"] == 0
    kit = data["workspace"]
    assert kit["status"] == "draft"
    assert kit["application_url"] == TALENTADORE
    assert kit["canonical_key"].startswith("private-saved-")
    assert kit["authority"]["may_submit_to_employer"] is False
    assert kit["source_cv_sha256"]
    assert kit["cv_text"].startswith("Fictional Applicant")

    repeated = api.post(path, headers=a, json={
        "acknowledge_unverified_employer": True,
    })
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] is False
    assert repeated.json()["workspace"]["workspace_id"] == kit["workspace_id"]

    own = api.get("/api/v1/application-workspaces", headers=a)
    other = api.get("/api/v1/application-workspaces", headers=b)
    assert any(i["workspace_id"] == kit["workspace_id"] for i in own.json()["workspaces"])
    assert all(i["workspace_id"] != kit["workspace_id"] for i in other.json()["workspaces"])
    assert api.get("/api/v1/jobs", headers=a).json()["count"] == 0
    assert api.get("/api/v1/jobs", headers=b).json()["count"] == 0

    # An independent partner or browser final-submit permission is NEVER granted.
    assert api.get(
        f"/api/v1/application-workspaces/{kit['workspace_id']}/handoff-readiness",
        headers=a,
    ).json()["ready"] is False


def test_sp120_unlisted_employer_uses_same_owned_reviewed_browser_packet(monkeypatch):
    api = own_api(monkeypatch)
    a, pid = owner_headers(api, "account-a")
    item = api.post("/api/v1/private-jobs", headers=a, json={
        **DATA, "application_url": EMPLOYER,
    }).json()["job"]
    put_synthetic_cv(api, pid)
    for kind, value in (
        ("identity", "Fictional Applicant"),
        ("email", "fictional.applicant@example.org"),
    ):
        r = api.post("/api/v1/profile/facts", headers=a, json={
            "fact_type": kind, "value": value, "approved": True,
        })
        assert r.status_code == 201, r.text
    response = api.post(
        f"/api/v1/private-jobs/{item['saved_job_id']}/application-workspace",
        headers=a, json={"acknowledge_unverified_employer": True},
    )
    assert response.status_code == 200, response.text
    kit = response.json()["workspace"]
    wid = kit["workspace_id"]

    before = api.get(f"/api/v1/application-workspaces/{wid}/handoff-readiness", headers=a)
    assert before.status_code == 200, before.text
    assert before.json()["ready"] is False
    assert before.json()["unverified_private_employer"] is True

    updated = api.put(f"/api/v1/application-workspaces/{wid}", headers=a, json={
        "expected_revision": kit["revision"],
        "cv_text": kit["cv_text"],
        "cover_letter_text": (
            "Dear hiring team,\nI would like to apply for this position. "
            "My application is based on my approved experience with Python and SQL.\n"
            "Kind regards, Fictional Applicant"
        ),
    })
    assert updated.status_code == 200, updated.text
    reviewed = updated.json()["workspace"]
    readiness = api.get(
        f"/api/v1/application-workspaces/{wid}/handoff-readiness", headers=a,
    )
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["ready"] is True, readiness.text
    assert readiness.json()["unverified_private_employer"] is True
    denied = api.post(
        f"/api/v1/application-workspaces/{wid}/browser-packet",
        headers=a, json={"expected_revision": reviewed["revision"],
                         "confirm_private_data_transfer": False},
    )
    assert denied.status_code == 422
    allowed = api.post(
        f"/api/v1/application-workspaces/{wid}/browser-packet",
        headers=a, json={"expected_revision": reviewed["revision"],
                         "confirm_private_data_transfer": True},
    )
    assert allowed.status_code == 200, allowed.text
    packet = allowed.json()["packet"]
    assert packet["application_url"] == EMPLOYER
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert packet["fields"]["full_name"] == "Fictional Applicant"
    assert packet["fields"]["email"] == "fictional.applicant@example.org"
    assert "cv_pdf_sha256" in packet
    assert "original_cv" not in packet
    assert api.get("/api/v1/jobs", headers=a).json()["count"] == 0


@pytest.mark.parametrize("bad", [
    "https://127.0.0.1/jobs/apply", "https://localhost/submit",
    "http://careers.example.org/job", "https://[::1]/apply",
    "https://user:pass@careers.example.org/jobs/apply",
    "https://careers.example.org:8443/jobs/apply",
    "https://ats.talentadore.com/marketing/home",
    "https://careers.example.invalid/role", "javascript:alert(1)",
])
def test_sp120_generic_browser_gate_rejects_unreviewable_employer_hosts(bad):
    from smartploy.browser_handoff import HandoffError
    with pytest.raises(HandoffError):
        _assisted_posting_url(bad)


def test_sp120_private_candidate_is_never_a_current_shared_job():
    repo = MemoryPrivateSavedJobRepository()
    saved = repo.save("profile-a", {**DATA, "application_url": EMPLOYER})
    assert repo.get("profile-a", saved.saved_job_id) == saved
    assert repo.get("profile-b", saved.saved_job_id) is None
    c = private_candidate(saved)
    assert c.source_current is False
    assert c.metadata["private_saved_job"] is True
    assert c.metadata["external_actions_authorized"] is False
    assert c.job.application_url == EMPLOYER
    assert c.canonical_key == "private-saved-" + saved.saved_job_id.removeprefix("saved-")

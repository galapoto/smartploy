"""First-party owner-scoped form handoff packets and outbound action boundaries."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.application_workspace import new_workspace, render_document
from smartploy.browser_handoff import HandoffError, approved_fields_sha256, make_browser_packet, review_handoff
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.service import SmartployService


APPLICATION_URL = "https://jobs.lever.co/uprightproject/d886a2eb-5ba0-4a3c-9e5e-414a4af47f9e/apply"


def candidate():
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url=APPLICATION_URL,
            raw_text="Job advert data analyst at Upright in Helsinki",
            payload={
                "role_title": "Junior Data Analyst",
                "company": "Upright Project",
                "description": "Python, SQL, dashboards",
                "application_url": APPLICATION_URL,
                "location": "Helsinki",
            },
            observed_at="2026-10-11T05:01:00+00:00",
        ),
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    )
    assert result.candidate
    return result.candidate


def profile(pid="person-a"):
    return CandidateProfile(pid, (
        ProfileFact("identity", "Test Candidate", "user-entered", approved=True).normalized(),
        ProfileFact("email", "test.candidate@example.com", "user-entered", approved=True).normalized(),
        ProfileFact("phone", "+358 40 1234567", "user-entered", approved=True).normalized(),
        ProfileFact("linkedin", "https://www.linkedin.com/in/test-candidate", "user-entered", approved=True).normalized(),
        ProfileFact("skill", "Python", "user-entered", approved=True).normalized(),
        ProfileFact("experience", "Secret uploaded CV content must never leave", "user-entered", approved=False).normalized(),
    ))


def ready_workspace():
    p = profile()
    item = new_workspace(candidate(), p, source_cv_text="This is an uploaded CV. Private."),
    # Simulate a deliberate owner save after reviewing the documents.
    return replace(item[0], revision=2, cover_letter_text=(
        "Dear Hiring Team,\n\nI am applying for the Junior Data Analyst role. "
        "I have reviewed the letter and want to discuss my approved Python skills.\n\n"
        "Kind regards,\nTest Candidate"
    ))


def test_structured_contact_facts_require_real_email_phone_and_public_links():
    p = profile()
    assert len(p.approved_facts) == 5
    for name, value in [
        ("email", "nobody-at-example"),
        ("email", "candidate@example\\com"),
        ("phone", "012"),
        ("phone", "not a real number"),
        ("linkedin", "http://linkedin.com/in/person"),
        ("linkedin", "https://evil.com/in/person"),
        ("github", "https://127.0.0.1/admin"),
    ]:
        with pytest.raises(ValueError):
            ProfileFact(name, value, "user-entered", approved=True).normalized()


def test_review_ready_packet_is_bounded_and_never_contains_original_cv():
    item = ready_workspace()
    p = profile()
    now = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
    review = review_handoff(item, candidate(), p)
    assert review["ready"] is True
    assert review["files_attached"] is False
    packet = make_browser_packet(item, candidate(), p, now=now)
    assert packet["application_url"] == APPLICATION_URL
    assert packet["schema"] == "smartploy.browser_handoff.v2"
    first_pdf, mime, filename = render_document(item, kind="cv", file_format="pdf")
    second_pdf, _, _ = render_document(item, kind="cv", file_format="pdf")
    assert mime == "application/pdf" and filename.endswith(".pdf")
    assert first_pdf == second_pdf  # export is byte-for-byte deterministic
    assert packet["cv_pdf_sha256"] == sha256(first_pdf).hexdigest()
    assert packet["cv_pdf_size"] == len(first_pdf) and packet["cv_pdf_size"] > 100
    assert packet["revision"] == item.revision
    assert packet["expires_at"] == (now + timedelta(minutes=15)).isoformat()
    assert packet["fields"]["email"] == "test.candidate@example.com"
    assert packet["fields"]["phone"] == "+358 40 1234567"
    assert packet["fields"]["first_name"] == "Test"
    assert packet["fields"]["last_name"] == "Candidate"
    assert "This is an uploaded CV" not in json.dumps(packet)
    assert "Secret uploaded CV" not in json.dumps(packet)
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert "browser_form_fill_allowed_after_user_click" in packet["privacy"]


def test_missing_contact_or_unreviewed_letter_prevents_handoff():
    item = new_workspace(candidate(), profile())
    initial = review_handoff(item, candidate(), profile())
    assert initial["ready"] is False
    assert any("personally reviewing" in b for b in initial["blockers"])
    with pytest.raises(HandoffError, match="not ready"):
        make_browser_packet(item, candidate(), profile())

    without_email = CandidateProfile("person-a", tuple(
        f for f in profile().facts if f.fact_type != "email"
    ))
    assert not review_handoff(ready_workspace(), candidate(), without_email)["ready"]


@pytest.mark.parametrize("prompt", [
    "[Kerro omin sanoin, miksi tehtävä kiinnostaa.]",
    "[Lisää tehtävään liittyvä kokemus.]",
    "[Oma nimi]",
    "[Täydennä kokemus]",
    "[Kirjoita oma esimerkki]",
    "[Explain why you are interested]",
])
def test_sp38_finnish_and_english_placeholders_block_employer_handoff(prompt):
    item = replace(
        ready_workspace(),
        cover_letter_text=(
            "Hei, olen kiinnostunut tehtävästä. Minulla on Python-osaamista. "
            + prompt +
            " Ystävällisin terveisin, Test Candidate."
        ),
    )
    readiness = review_handoff(item, candidate(), profile())
    assert readiness["ready"] is False
    assert any("placeholders" in text for text in readiness["blockers"])
    with pytest.raises(HandoffError, match="not ready"):
        make_browser_packet(item, candidate(), profile())


def test_sp38_real_finnish_initial_letter_never_counts_as_reviewed_handoff():
    p, job = profile(), candidate()
    initial = new_workspace(
        replace(job, job=replace(job.job, language="Finnish")), p,
    )
    assert initial.cover_letter_text.startswith("Hei rekrytointitiimi")
    assert "[Kerro omin sanoin" not in initial.cover_letter_text
    assert "Python" in initial.cover_letter_text
    readiness = review_handoff(initial, job, p)
    assert readiness["ready"] is False
    assert any("personally reviewing" in text for text in readiness["blockers"])
    # An approved fact and finished prose are NOT permission to bypass review.
    completed = replace(initial, revision=2, cover_letter_text=(
        "Hei rekrytointitiimi,\\n\\n"
        "Haen Junior Data Analyst -tehtävää. Osaamiseni sisältää Pythonin. "
        "Olen perehtynyt työnkuvaan ja tarkistanut väitteeni.\\n\\n"
        "Ystävällisin terveisin, Test Candidate"
    ))
    assert review_handoff(completed, job, p)["ready"] is True


def test_sp85_finished_first_draft_never_enables_browser_handoff_without_review():
    p, job = profile(), candidate()
    fresh = new_workspace(job, p)
    assert fresh.revision == 1
    assert "[" not in fresh.cover_letter_text
    first = review_handoff(fresh, job, p)
    assert first["ready"] is False
    assert first["employer_submission_performed"] is False
    assert any("personally reviewing" in item for item in first["blockers"])
    with pytest.raises(HandoffError, match="not ready"):
        make_browser_packet(fresh, job, p)
    # A deliberate revision-checked applicant save is the minimum review step;
    # it does not permit an employer submit without further independent rights.
    confirmed = replace(fresh, revision=2)
    after = review_handoff(confirmed, job, p)
    assert after["ready"] is True
    assert after["employer_submission_performed"] is False
    packet = make_browser_packet(confirmed, job, p)
    assert packet["revision"] == 2
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False


def test_changed_job_expired_listing_or_url_mismatch_blocks():
    item = ready_workspace()
    assert not review_handoff(item, replace(candidate(), source_current=False), profile())["ready"]
    bad = replace(item, application_url="https://jobs.lever.co/other-company/somewhere/apply")
    assert not review_handoff(bad, candidate(), profile())["ready"]
    wrong_person = profile("person-b")
    with pytest.raises(HandoffError, match="not owned"):
        review_handoff(item, candidate(), wrong_person)
    http_item = replace(item, application_url="http://jobs.lever.co/private/apply")
    assert not review_handoff(http_item, candidate(), profile())["ready"]


def test_browser_api_requires_explicit_confirmation_and_saved_revision():
    service = SmartployService()
    service.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    client = TestClient(create_app(service))
    created = client.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import",
            "source_mode": "manual",
            "raw_text": "Data analyst in Helsinki",
            "source_url": APPLICATION_URL,
            "payload": {
                "company": "Upright Project",
                "role_title": "Junior Data Analyst",
                "description": "Python and SQL dashboards",
                "application_url": APPLICATION_URL
            }
        }
    })
    assert created.status_code == 200, created.text
    key = created.json()["candidate"]["canonical_key"]
    for fact in profile().approved_facts:
        assert client.post("/api/v1/profile/facts", json={
            "fact_type": fact.fact_type, "value": fact.value, "approved": True,
        }).status_code == 201
    starter = client.post("/api/v1/jobs/" + key + "/application-workspace")
    assert starter.status_code == 200, starter.text
    w = starter.json()["workspace"]
    wid = w["workspace_id"]
    untouched = client.get(f"/api/v1/application-workspaces/{wid}/handoff-readiness")
    assert untouched.status_code == 200
    assert untouched.json()["ready"] is False
    assert any("personally reviewing" in x for x in untouched.json()["blockers"])
    changed = client.put("/api/v1/application-workspaces/" + wid, json={
        "expected_revision": w["revision"],
        "cv_text": "Test Candidate\nPython analyst",
        "cover_letter_text": "Dear Hiring Team,\nI am applying for this role. My approved Python skill is relevant.\n\nKind regards,\nTest Candidate"
    })
    assert changed.status_code == 200, changed.text
    w = changed.json()["workspace"]
    read = client.get("/api/v1/application-workspaces/" + wid + "/handoff-readiness")
    assert read.status_code == 200
    assert read.json()["ready"] is True
    target = "/api/v1/application-workspaces/" + wid + "/browser-packet"
    assert client.post(target, json={
        "expected_revision": w["revision"], "confirm_private_data_transfer": False
    }).status_code == 422
    assert client.post(target, json={
        "expected_revision": w["revision"] - 1, "confirm_private_data_transfer": True
    }).status_code == 409
    reply = client.post(target, json={
        "expected_revision": w["revision"], "confirm_private_data_transfer": True
    })
    assert reply.status_code == 200, reply.text
    assert reply.headers["cache-control"] == "private, no-store"
    assert reply.json()["external_actions_performed"] is False
    assert reply.json()["packet"]["fields"]["email"] == "test.candidate@example.com"
    assert client.get("/api/v1/applications/summary").json()["actually_submitted"] == 0
    assert client.delete("/api/v1/application-workspaces/" + wid).status_code == 200
    assert client.post(target, json={
        "expected_revision": w["revision"], "confirm_private_data_transfer": True
    }).status_code == 404


def test_api_missing_contact_remains_blocked():
    service = SmartployService()
    service.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    client = TestClient(create_app(service))
    created = client.post("/api/v1/jobs/ingest", json={
        "observation": {"source_id": "manual-import", "source_mode": "manual",
        "raw_text": "Analyst", "payload": {"company": "Example Oy", "role_title": "Analyst",
            "description": "SQL", "application_url": APPLICATION_URL}}
    })
    key = created.json()["candidate"]["canonical_key"]
    client.post("/api/v1/profile/facts", json={
        "fact_type": "skill", "value": "SQL", "approved": True
    })
    kit = client.post("/api/v1/jobs/" + key + "/application-workspace").json()["workspace"]
    endpoint = "/api/v1/application-workspaces/" + kit["workspace_id"]
    client.put(endpoint, json={
        "expected_revision": 1, "cv_text": "Approved SQL",
        "cover_letter_text": "Dear Hiring Team,\nI am interested in this position and have reviewed this message."
    })
    readiness = client.get(endpoint + "/handoff-readiness").json()
    assert readiness["ready"] is False
    assert any("full-name" in x for x in readiness["blockers"])
    assert any("email" in x for x in readiness["blockers"])
    res = client.post(endpoint + "/browser-packet", json={
        "expected_revision": 2, "confirm_private_data_transfer": True
    })
    assert res.status_code == 409



def test_cross_language_approved_field_fingerprint_is_stable_and_tamper_evident():
    """Reference independently computed using browser-companion review-bridge.mjs."""
    values = {
        "full_name": "Synthetic Applicant",
        "first_name": "Synthetic",
        "last_name": "Applicant",
        "email": "test@example.invalid",
        "phone": "", "location": "", "linkedin": "", "github": "",
        "cover_letter": "I have reviewed every statement in this synthetic cover letter.",
    }
    expected = "135df071b9de4a37fd07681b9a61b09c8e2bfe6bbba4df84108c69168176403c"
    assert approved_fields_sha256(values) == expected
    assert approved_fields_sha256({**values,"email":"other@example.invalid"}) != expected
    with pytest.raises(HandoffError,match="expected approved"):
        approved_fields_sha256({**values,"secret":"do not export"})


# SP41 - read-only Ashby job ingestion now has an OWNER-reviewed form-help path.
ASHBY_FORM = "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application"


def test_sp41_ashby_review_packet_is_fingerprinted_and_final_employer_rights_stay_lever_only():
    from smartploy.browser_handoff import _posting_url, _assisted_posting_url
    from smartploy.employer_automation_rights import EmployerRightsDenied, employer_job_key

    original = candidate()
    posting = replace(original, job=replace(original.job, application_url=ASHBY_FORM))
    workspace = replace(ready_workspace(), application_url=ASHBY_FORM)
    assert _assisted_posting_url(ASHBY_FORM) == ASHBY_FORM
    assert review_handoff(workspace, posting, profile())["ready"] is True
    packet = make_browser_packet(
        workspace, posting, profile(),
        now=datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc),
    )
    assert packet["application_url"] == ASHBY_FORM
    assert packet["fields"]["email"] == "test.candidate@example.com"
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert packet["cv_pdf_sha256"] == sha256(render_document(workspace, kind="cv", file_format="pdf")[0]).hexdigest()
    assert "This is an uploaded CV" not in json.dumps(packet)
    # Preserve the ORIGINAL Lever-only employer submit-rights boundary.
    with pytest.raises(HandoffError):
        _posting_url(ASHBY_FORM)
    with pytest.raises(EmployerRightsDenied):
        employer_job_key(ASHBY_FORM)


@pytest.mark.parametrize("raw", [
    "https://jobs.ashbyhq.com.evil.invalid/synthetic-fi/junior-data-analyst/application",
    "http://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application",
    "https://jobs.ashbyhq.com/other-fi/another-job/application/subform",
    "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/redirect",
    "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application?next=evil",
    "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application#debug",
    "https://someone:password@jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application",
    "https://jobs.ashbyhq.com/synthetic-fi/junior-data-analyst/application@other",
])
def test_sp41_ashby_handoff_rejects_unapproved_host_or_path(raw):
    from smartploy.browser_handoff import _assisted_posting_url
    with pytest.raises(HandoffError):
        _assisted_posting_url(raw)
    workspace = replace(ready_workspace(), application_url=raw)
    posting = replace(candidate(), job=replace(candidate().job, application_url=raw))
    assert review_handoff(workspace, posting, profile())["ready"] is False


def test_sp41_server_ashby_workspace_to_signed_user_review_packet_never_contacts_employer():
    service = SmartployService()
    policy = SourcePolicy("manual-import", "Manual", "manual", ("manual",))
    service.register_source(policy)
    client = TestClient(create_app(service))
    ingested = client.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "source_url": ASHBY_FORM, "raw_text": "Junior Data Analyst at Synthetic Oy",
            "payload": {
                "company": "Synthetic Oy",
                "role_title": "Junior Data Analyst",
                "description": "Python, SQL, analytics",
                "location": "Helsinki",
                "application_url": ASHBY_FORM,
            },
        }
    })
    assert ingested.status_code == 200, ingested.text
    key = ingested.json()["candidate"]["canonical_key"]
    for fact in profile().approved_facts:
        assert client.post("/api/v1/profile/facts", json={
            "fact_type": fact.fact_type, "value": fact.value, "approved": True,
        }).status_code == 201
    created = client.post("/api/v1/jobs/" + key + "/application-workspace")
    assert created.status_code == 200, created.text
    workspace = created.json()["workspace"]
    wid = workspace["workspace_id"]
    edited = client.put("/api/v1/application-workspaces/" + wid, json={
        "expected_revision": workspace["revision"],
        "cv_text": "Reviewed candidate Python CV",
        "cover_letter_text": (
            "Dear Hiring Team, I am interested in this Data Analyst role. "
            "My Python experience statement has been reviewed for accuracy. "
            "Kind regards, Test Candidate."
        ),
    })
    assert edited.status_code == 200, edited.text
    revision = edited.json()["workspace"]["revision"]
    readiness = client.get("/api/v1/application-workspaces/" + wid + "/handoff-readiness")
    assert readiness.status_code == 200 and readiness.json()["ready"] is True
    packet = client.post("/api/v1/application-workspaces/" + wid + "/browser-packet", json={
        "expected_revision": revision, "confirm_private_data_transfer": True,
    })
    assert packet.status_code == 200, packet.text
    assert packet.json()["packet"]["application_url"] == ASHBY_FORM
    assert packet.json()["packet"]["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert packet.json()["external_actions_performed"] is False
    assert client.get("/api/v1/applications/summary").json()["actually_submitted"] == 0


# SP43: already ingested current Finland Greenhouse jobs now have an exact,
# consented owner-reviewed HANDOFF; this does not create employer send rights.
GREENHOUSE_MODERN = "https://job-boards.greenhouse.io/synthetic-it/jobs/123456789"
GREENHOUSE_LEGACY = "https://boards.greenhouse.io/synthetic-it/jobs/123456789"


@pytest.mark.parametrize("hosted", [GREENHOUSE_MODERN, GREENHOUSE_LEGACY])
def test_sp43_greenhouse_review_packet_reuses_existing_owner_cv_and_no_submit(hosted):
    from smartploy.browser_handoff import _posting_url, _assisted_posting_url
    from smartploy.employer_automation_rights import EmployerRightsDenied, employer_job_key

    item = replace(candidate(), job=replace(candidate().job, application_url=hosted))
    workspace = replace(ready_workspace(), application_url=hosted)
    assert _assisted_posting_url(hosted) == hosted
    assert review_handoff(workspace, item, profile())["ready"] is True
    packet = make_browser_packet(
        workspace, item, profile(),
        now=datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc),
    )
    assert packet["application_url"] == hosted
    assert packet["fields"]["email"] == "test.candidate@example.com"
    assert packet["cv_pdf_sha256"] == sha256(
        render_document(workspace, kind="cv", file_format="pdf")[0]
    ).hexdigest()
    assert packet["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert "This is an uploaded CV" not in json.dumps(packet)
    with pytest.raises(HandoffError):
        _posting_url(hosted)
    with pytest.raises(EmployerRightsDenied):
        employer_job_key(hosted)


@pytest.mark.parametrize("untrusted", [
    "https://evil.example/synthetic-it/jobs/123456789",
    "https://job-boards.greenhouse.io.evil.invalid/synthetic-it/jobs/123456789",
    "http://job-boards.greenhouse.io/synthetic-it/jobs/123456789",
    "https://user:secret@job-boards.greenhouse.io/synthetic-it/jobs/123456789",
    "https://job-boards.greenhouse.io/synthetic-it/jobs/123456789?gh_src=unreviewed",
    "https://job-boards.greenhouse.io/synthetic-it/jobs/123456789#secret",
    "https://job-boards.greenhouse.io/synthetic-it/jobs/123456789/submit",
    "https://job-boards.greenhouse.io/synthetic-it/jobs/123456789-extra",
    "https://job-boards.greenhouse.io/synthetic-it/jobs/abc",
    "https://job-boards.greenhouse.io/another/jobs/123456789/redirect",
    "https://job-boards.greenhouse.io/embed/job_app?for=synthetic-it&token=123456789",
    "https://careers.example.com/jobs/123456789",
])
def test_sp43_greenhouse_rejects_untrusted_employer_forms(untrusted):
    from smartploy.browser_handoff import _assisted_posting_url
    with pytest.raises(HandoffError):
        _assisted_posting_url(untrusted)
    workspace = replace(ready_workspace(), application_url=untrusted)
    item = replace(candidate(), job=replace(candidate().job, application_url=untrusted))
    assert review_handoff(workspace, item, profile())["ready"] is False


def test_sp43_greenhouse_owner_application_api_issues_only_review_packet():
    svc = SmartployService()
    svc.register_source(SourcePolicy("manual-import", "Manual", "manual", ("manual",)))
    cli = TestClient(create_app(svc))
    posted = cli.post("/api/v1/jobs/ingest", json={
        "observation": {
            "source_id": "manual-import", "source_mode": "manual",
            "source_url": GREENHOUSE_MODERN,
            "raw_text": "Junior data engineer Helsinki Python SQL",
            "payload": {
                "company": "Synthetic IT", "role_title": "Junior Data Engineer",
                "description": "Python SQL ETL in Finland",
                "application_url": GREENHOUSE_MODERN,
                "location": "Helsinki",
            },
        }
    })
    assert posted.status_code == 200, posted.text
    key = posted.json()["candidate"]["canonical_key"]
    for fact in profile().approved_facts:
        assert cli.post("/api/v1/profile/facts", json={
            "fact_type": fact.fact_type, "value": fact.value, "approved": True,
        }).status_code == 201
    created = cli.post(f"/api/v1/jobs/{key}/application-workspace")
    assert created.status_code == 200, created.text
    workspace = created.json()["workspace"]
    wid = workspace["workspace_id"]
    edited = cli.put(f"/api/v1/application-workspaces/{wid}", json={
        "expected_revision": workspace["revision"],
        "cv_text": "Reviewed candidate SQL Python CV",
        "cover_letter_text": (
            "Dear Hiring Team, I am interested in this role because my "
            "reviewed SQL and Python experience matches it. "
            "Kind regards, Test Candidate."
        ),
    })
    assert edited.status_code == 200, edited.text
    revision = edited.json()["workspace"]["revision"]
    readiness = cli.get(f"/api/v1/application-workspaces/{wid}/handoff-readiness")
    assert readiness.status_code == 200 and readiness.json()["ready"] is True
    packet = cli.post(f"/api/v1/application-workspaces/{wid}/browser-packet",json={
        "expected_revision":revision, "confirm_private_data_transfer":True,
    })
    assert packet.status_code == 200, packet.text
    assert packet.json()["packet"]["application_url"] == GREENHOUSE_MODERN
    assert packet.json()["external_actions_performed"] is False
    assert packet.json()["packet"]["privacy"]["employer_submit_allowed_without_new_approval"] is False
    assert cli.get("/api/v1/applications/summary").json()["actually_submitted"] == 0

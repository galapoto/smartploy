import json

import pytest

from smartploy.application_v2 import (
    V2_DRAFT_SCHEMA,
    V2_PACKAGE_CONTRACT,
    parse_v2_draft,
)
from smartploy.preparations import PreparationResultError
from smartploy.profile import CandidateProfile, ProfileFact


def fixture():
    profile = CandidateProfile(facts=(
        ProfileFact("identity", "Ada Candidate", "approved", approved=True),
        ProfileFact("contact", "ada@example.com", "approved", approved=True, tags=("email",)),
        ProfileFact("skill", "Python", "approved", approved=True),
        ProfileFact("experience", "Data analysis with Python", "approved", approved=True),
    ))
    snapshot = profile.approved_evidence()
    def fact(kind):
        return snapshot["facts"][kind][0]["fact_id"]
    result = {
        "schema": V2_DRAFT_SCHEMA,
        "cv": {
            "headline": "Junior Analyst",
            "professional_summary": {"text": "Python analyst", "evidence_fact_ids": [fact("skill")]},
            "header": [
                {"kind": "name", "text": "Ada Candidate", "evidence_fact_ids": [fact("identity")]},
                {"kind": "email", "text": "ada@example.com", "evidence_fact_ids": [fact("contact")]},
            ],
            "skills": [{"text": "Python", "evidence_fact_ids": [fact("skill")]}],
            "experience": [{"position": {"text": "Data analyst", "evidence_fact_ids": [fact("experience")]}, "bullets": []}],
            "education": [], "certifications": [], "projects": [], "languages": [],
            "do_not_claim": [],
        },
        "cover_letter": {"paragraphs": [{"text": "I work with Python.", "evidence_fact_ids": [fact("skill")]}]},
        "risks": [], "review_checklist": ["Human review required"],
    }
    return snapshot, result


def test_valid_v2_draft_is_evidence_bound():
    snapshot, result = fixture()
    assert parse_v2_draft(json.dumps(result), snapshot) == result
    assert V2_PACKAGE_CONTRACT == "smartploy.application.package.v2"


def test_v2_rejects_unknown_claim_id():
    snapshot, result = fixture()
    result["cv"]["skills"][0]["evidence_fact_ids"] = ["fact-invented"]
    with pytest.raises(PreparationResultError):
        parse_v2_draft(json.dumps(result), snapshot)


def test_v2_rejects_unapproved_contact_or_modified_contact():
    snapshot, result = fixture()
    result["cv"]["header"][1]["text"] = "other@example.com"
    with pytest.raises(PreparationResultError):
        parse_v2_draft(json.dumps(result), snapshot)


def test_v2_rejects_unapproved_identity_type():
    snapshot, result = fixture()
    result["cv"]["header"][0]["evidence_fact_ids"] = [snapshot["facts"]["skill"][0]["fact_id"]]
    with pytest.raises(PreparationResultError):
        parse_v2_draft(json.dumps(result), snapshot)


def test_v2_rejects_claim_without_evidence():
    snapshot, result = fixture()
    result["cover_letter"]["paragraphs"][0]["evidence_fact_ids"] = []
    with pytest.raises(PreparationResultError):
        parse_v2_draft(json.dumps(result), snapshot)


def test_v2_rejects_non_json_and_oversized_payload():
    snapshot, _ = fixture()
    for bad in ("not-json", "[]" , "x" * 256001):
        with pytest.raises(PreparationResultError):
            parse_v2_draft(bad, snapshot)


def test_unapproved_profile_identity_is_never_sent_as_evidence():
    profile = CandidateProfile(facts=(
        ProfileFact("identity", "Approved Name", "verified", approved=True),
        ProfileFact("contact", "unapproved@example.com", "unverified", approved=False),
    ))
    evidence = profile.approved_evidence()
    assert "contact" not in evidence["facts"]
    assert evidence["facts"]["identity"][0]["value"] == "Approved Name"

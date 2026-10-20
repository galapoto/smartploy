"""SP16: reuse established source matching for opt-in LOCAL draft automation."""
from dataclasses import replace
import json

import pytest

from smartploy.auto_shortlist import AutoShortlistDenied, _check_options, shortlist_matches
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.search_preferences import revise_preferences


def vacancy(title: str, *, location="Helsinki", current=True, url=None):
    result = normalize_observation(
        SourceObservation(
            source_id="manual-import",source_mode="manual",
            source_url=url or "https://careers.example.invalid/" + title.replace(" ","-"),
            raw_text=title+" vacancy",observed_at="2026-10-20T10:00:00+00:00",
            payload={
                "company":"Synthetic Careers Oy","role_title":title,
                "description":"Python, SQL, analytics, and evidence-based data work",
                "location":location,"language":"English","work_mode":"hybrid",
                "application_url":url or "https://careers.example.invalid/" + title.replace(" ","-"),
            },
        ),SourcePolicy("manual-import","Manual","manual",("manual",))
    )
    assert result.candidate
    return replace(result.candidate,source_current=current)


def preferences(profile_id="p", *, mode="personalized",seniority="entry"):
    return revise_preferences(profile_id,{
        "mode":mode,"roles":["Data Analyst"],"locations":["Helsinki"],
        "languages":["english"],"work_modes":["hybrid"],
        "skills":["Python"],"seniority":seniority,
    },revision=0)


def test_reuses_original_score_and_current_only_without_qualification_claim():
    matches=shortlist_matches([
        vacancy("Junior Data Analyst"),
        vacancy("Senior Data Analyst"),
        vacancy("Junior Data Analyst",current=False),
        vacancy("Nurse"),
        vacancy("Junior Data Analyst",location="Turku"),
    ],preferences(),minimum_score=75)
    assert len(matches)==1
    assert matches[0].job.role_title=="Junior Data Analyst"


def test_general_unconfigured_and_outside_https_deny_all_unattended_drafts():
    examples=[
        vacancy("Junior Data Analyst",url="http://careers.example.invalid/job"),
        vacancy("Junior Data Analyst",url="https://localhost/123"),
        vacancy("Junior Data Analyst",url="https://user:pass@careers.example.invalid/123"),
    ]
    assert shortlist_matches(examples,preferences(),minimum_score=70)==[]
    assert shortlist_matches([vacancy("Junior Data Analyst")],preferences(mode="general"))==[]


def test_weak_keyword_role_overlap_never_opens_automatic_draft():
    current=vacancy("Marketing Specialist",url="https://jobs.example.invalid/marketing")
    matches=shortlist_matches([current],preferences(),minimum_score=75)
    assert matches==[]


def test_options_reject_nonliteral_or_unsafe_batch_limits():
    for enabled,score,batch in [
        ("true",75,3),(1,75,3),(True,69,3),(True,101,3),
        (True,75,0),(True,75,11),(True,True,2)
    ]:
        with pytest.raises(AutoShortlistDenied):
            _check_options(enabled,score,batch)
    _check_options(True,75,3)


def test_auto_shortlist_has_no_employer_or_llm_imports():
    from pathlib import Path
    code=Path("smartploy/auto_shortlist.py").read_text(encoding="utf-8")
    assert "ObumAIClient" not in code
    assert "sendLeverPartnerApplication" not in code
    assert "consume_once_for_trusted_adapter" not in code
    assert "requests.post" not in code

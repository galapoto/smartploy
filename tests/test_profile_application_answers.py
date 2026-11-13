"""Integration-level evidence for applicant profile-once answer reuse."""
import json

import pytest

from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.profile_application_answers import (
    SCHEMA, approved_answers_for_packet, decode_profile_answer,
    encode_profile_answer,
)


def saved(question: str, answer: str, *, approved: bool = True) -> ProfileFact:
    payload = json.dumps({
        "schema": SCHEMA, "question": question, "answer": answer,
    }, ensure_ascii=False)
    return ProfileFact("application_answer", payload, "user-confirmed",
                       approved=approved).normalized()


def test_application_answers_are_normalized_and_reused_only_when_approved():
    answer = saved("How did you hear about us?", "I found the role on your careers page.")
    second = saved("Which tools have you used?", "Python, SQL and Power BI.")
    pending = saved("What is your preferred working style?", "Hybrid", approved=False)
    p = CandidateProfile("person-one", (
        answer, second, pending,
        ProfileFact("skill", "Python", "user-confirmed", approved=True).normalized()
    ))
    result = approved_answers_for_packet(p)
    assert len(result) == 2
    assert result[0]["question"] == "How did you hear about us?"
    assert result[1]["answer"] == "Python, SQL and Power BI."
    assert "application_answer" not in p.approved_evidence()["facts"]
    assert p.approved_evidence()["facts"]["skill"][0]["value"] == "Python"
    assert "Hybrid" not in json.dumps(result)


def test_application_answers_for_conflicting_revisions_are_not_guessed():
    p = CandidateProfile("one", (
        saved("How did you hear about us?", "Referral"),
        saved("How did you hear about us?", "Job board"),
        saved("Which tool?", "Python"),
    ))
    assert approved_answers_for_packet(p) == [
        {"question": "Which tool?", "answer": "Python"}
    ]


@pytest.mark.parametrize("question,answer", [
    ("Expected salary?", "50000"),
    ("Immigration status", "Approved"),
    ("Describe your experience", "I am female"),
    ("Gender", "Prefer not to say"),
    ("I agree to privacy policy", "Yes"),
    ("What is your disability?", "None"),
    ("", "Any"),
    ("Normal question?", ""),
    ("Q"*151, "Normal"),
    ("Normal question?", "A"*481),
])
def test_sensitive_empty_and_unbounded_answers_cannot_enter_the_profile(question, answer):
    raw = json.dumps({"schema": SCHEMA, "question": question, "answer": answer})
    with pytest.raises(ValueError):
        decode_profile_answer(raw)
    with pytest.raises(ValueError):
        ProfileFact("application_answer", raw, "user-confirmed", approved=True).normalized()


def test_answer_format_does_not_accept_unknown_keys_or_unreviewed_schema():
    for data in [
        {"schema": "other", "question": "Why?", "answer": "Because"},
        {"schema": SCHEMA, "question": "Why?", "answer": "Because", "submit": True},
        {"schema": SCHEMA, "question": 1, "answer": "Because"},
        {"schema": SCHEMA, "question": "Question?", "answer": "Line\nTwo"},
    ]:
        with pytest.raises(ValueError):
            encode_profile_answer(json.dumps(data))

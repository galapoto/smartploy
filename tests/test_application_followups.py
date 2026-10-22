"""SP23 pinned career-ops cadence adaptation and strict in-app-only semantics."""
from datetime import datetime, timedelta, timezone

import pytest

from smartploy.application_followups import (
    DEFAULT_CADENCE, MILESTONE_EVENTS, due_message, followup_draft,
    next_candidate_followup, next_case_due,
)


BASE = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)


def test_exact_pinned_career_ops_applied_policy_and_cold_limit():
    assert DEFAULT_CADENCE["applied_first"] == 7
    assert DEFAULT_CADENCE["applied_subsequent"] == 7
    assert DEFAULT_CADENCE["applied_max_followups"] == 2
    assert next_candidate_followup("none", BASE, None, 0) == BASE + timedelta(days=7)
    first_sent = BASE + timedelta(days=8)
    assert next_candidate_followup("none", BASE, first_sent, 1) == first_sent + timedelta(days=7)
    assert next_candidate_followup("none", BASE, first_sent, 2) is None
    # A cold case can still have a safe in-app status check, NOT a third contact.
    assert next_case_due("none", "self_reported_applied", BASE, 2) == (
        BASE + timedelta(days=14)
    )


def test_recruiter_response_interview_and_offer_cadences():
    assert next_candidate_followup("recruiter_replied", BASE, None, 0) == BASE + timedelta(days=1)
    last_sent = BASE + timedelta(days=2)
    assert next_candidate_followup(
        "recruiter_replied", BASE, last_sent, 1
    ) == last_sent + timedelta(days=3)
    assert next_candidate_followup("interview", BASE, None, 0) == BASE + timedelta(days=1)
    assert next_case_due("offer", "provider_acknowledged", BASE, 0) == (
        BASE + timedelta(days=7)
    )
    assert next_case_due("rejected", "provider_acknowledged", BASE, 0) is None
    assert next_case_due("hired", "self_reported_applied", BASE, 0) is None


def test_no_unsent_draft_can_be_mistaken_for_followup_due():
    event, message = due_message("none", "draft", 0)
    assert event == "review_reminder_due"
    assert "still a draft" in message
    assert next_case_due("none", "draft", BASE, 0) == BASE + timedelta(days=1)
    event, message = due_message("none", "self_reported_applied", 0)
    assert event == "followup_due"
    assert "may be due" in message
    event, message = due_message("none", "self_reported_applied", 2)
    assert event == "review_reminder_due"
    assert "No further outreach" in message
    assert all("send" not in value[0] for value in MILESTONE_EVENTS.values())


def test_draft_has_no_address_claim_or_fabricated_qualifications():
    text = followup_draft(
        "Example Oy", "Junior Data Analyst"
    )
    assert "Example Oy" in text
    assert "Junior Data Analyst" in text
    assert "Python" not in text
    assert "I sent" not in text
    assert "@" not in text
    assert "[Your name]" in text
    with pytest.raises(ValueError):
        next_candidate_followup("none", BASE.replace(tzinfo=None), None, 0)
    with pytest.raises(ValueError):
        next_candidate_followup("none", BASE, None, 3)
    with pytest.raises(ValueError):
        next_candidate_followup("unknown", BASE, None, 0)

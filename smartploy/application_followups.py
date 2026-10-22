"""Candidate-side application follow-up cadence, adapted from career-ops (MIT).

Source: https://github.com/career-ops-hq/career-ops/blob/dff9703a092e2872245aef09b096edcee054ac69/followup-cadence.mjs
Upstream: DEFAULT_CADENCE and computeNextFollowupDate. Copyright (c) 2026
Santiago Fernández de Valderrama. See docs/third_party/CAREER_OPS_MIT_NOTICE.md.

Unlike upstream's markdown-based tracker, SmartPloy uses a durable, owner-bound
Postgres application case. All reminders stay INSIDE SmartPloy. A "sent follow-up"
is a candidate claim, not a delivery receipt or permission to send.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal


# Adapted verbatim from career-ops DEFAULT_CADENCE, with an added conservative
# general-case check after its applied_max_followups threshold.
DEFAULT_CADENCE = {
    "applied_first": 7,
    "applied_subsequent": 7,
    "applied_max_followups": 2,
    "responded_initial": 1,
    "responded_subsequent": 3,
    "interview_thankyou": 1,
}
GENERAL_STATUS_RECHECK_DAYS = 14
DRAFT_REVIEW_DAYS = 1
OFFER_REVIEW_DAYS = 7

Milestone = Literal["none", "recruiter_replied", "interview", "offer", "rejected", "hired"]
SUBMITTED_WORKSPACE_STATUSES = frozenset({"self_reported_applied", "provider_acknowledged"})
TERMINAL_MILESTONES = frozenset({"rejected", "hired"})
MILESTONE_EVENTS = {
    "recruiter_replied": (
        "candidate_reported_reply",
        "You reported a recruiter reply. Check the message and decide your next step.",
    ),
    "interview": (
        "candidate_reported_interview",
        "You reported an interview. Verify the date and prepare your response.",
    ),
    "offer": (
        "candidate_reported_offer",
        "You reported an offer. Review its details before making a decision.",
    ),
    "rejected": (
        "candidate_reported_rejected",
        "You reported rejection. This application agent is now closed.",
    ),
    "hired": (
        "candidate_reported_hired",
        "You reported accepting employment. This application agent is now closed.",
    ),
}
ORDER = {"none": 0, "recruiter_replied": 1, "interview": 2, "offer": 3}


def _utc(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        raise ValueError("Agent times must be timezone-aware")
    return instant.astimezone(timezone.utc)


def next_candidate_followup(
    milestone: str, applied_at: datetime, last_sent_at: datetime | None,
    followups_sent: int,
) -> datetime | None:
    """Port of the applicable career-ops computeNextFollowupDate branches.

    A past/replayed date is valid (the worker will find it overdue), but no
    code path can ask SmartPloy to send mail. After two reported follow-ups,
    the application is "cold" and this function returns None.
    """
    started = _utc(applied_at)
    last = _utc(last_sent_at) if last_sent_at else None
    if not isinstance(followups_sent, int) or not 0 <= followups_sent <= 2:
        raise ValueError("Follow-up count is outside the safe range")
    if milestone in TERMINAL_MILESTONES or milestone == "offer":
        return None
    if milestone == "none":
        if followups_sent >= DEFAULT_CADENCE["applied_max_followups"]:
            return None
        if last:
            return last + timedelta(days=DEFAULT_CADENCE["applied_subsequent"])
        return started + timedelta(days=DEFAULT_CADENCE["applied_first"])
    if milestone in {"recruiter_replied", "interview"}:
        if last:
            return last + timedelta(days=DEFAULT_CADENCE["responded_subsequent"])
        return started + timedelta(days=(
            DEFAULT_CADENCE["responded_initial"]
            if milestone == "recruiter_replied"
            else DEFAULT_CADENCE["interview_thankyou"]
        ))
    raise ValueError("Unrecognized candidate milestone")


def next_case_due(
    milestone: str, workspace_status: str, event_at: datetime,
    followups_sent: int, last_sent_at: datetime | None = None,
) -> datetime | None:
    """Schedule only an in-app review, not a future employer interaction."""
    now = _utc(event_at)
    if milestone in TERMINAL_MILESTONES:
        return None
    if workspace_status not in SUBMITTED_WORKSPACE_STATUSES:
        return now + timedelta(days=DRAFT_REVIEW_DAYS)
    planned = next_candidate_followup(milestone, now, last_sent_at, followups_sent)
    if planned is not None:
        return max(planned, now)
    return now + timedelta(days=(
        OFFER_REVIEW_DAYS if milestone == "offer" else GENERAL_STATUS_RECHECK_DAYS
    ))


def due_message(milestone: str, workspace_status: str, followups_sent: int) -> tuple[str, str]:
    """The source of truth is the workspace and candidate-reported milestone."""
    if workspace_status not in SUBMITTED_WORKSPACE_STATUSES:
        return "review_reminder_due", (
            "Your application is still a draft. Review it before claiming you applied."
        )
    if milestone == "interview":
        return "review_reminder_due", (
            "Check your interview arrangements and prepare using verified information."
        )
    if milestone == "offer":
        return "review_reminder_due", (
            "Review your offer details. SmartPloy cannot accept a job for you."
        )
    if milestone == "recruiter_replied":
        return "review_reminder_due", (
            "Review the recruiter reply and decide whether a response is needed."
        )
    if followups_sent >= DEFAULT_CADENCE["applied_max_followups"]:
        return "review_reminder_due", (
            "Review this application status. No further outreach is suggested automatically."
        )
    return "followup_due", (
        "Your application may be due for a polite follow-up. Review before sending anything."
    )


def followup_draft(company: str, role_title: str) -> str:
    """Generic applicant-editable copy only. No recipient or PII is inferred."""
    safe_company = " ".join(str(company).split())[:150]
    safe_role = " ".join(str(role_title).split())[:150]
    return (
        f"Hello,\n\nI am following up on my application for the {safe_role} "
        f"position at {safe_company}. I remain interested in the opportunity "
        "and would appreciate any update on the recruitment timeline.\n\n"
        "Thank you for your time.\n\nKind regards,\n[Your name]"
    )

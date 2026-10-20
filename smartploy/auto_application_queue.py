"""Private match-to-application queue. No AI/network/employer submit operations.

REUSE: existing public-source ingestion, SearchPreferences.search_jobs ranking,
verified CandidateProfile/StoredCV, deterministic application_workspace.new_workspace
and owner-scoped create_or_get. This joins already tested pieces rather than
inventing another source crawler, matching engine, writer, or submitter.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from urllib.parse import urlsplit

from psycopg import connect

from .application_workspace import WorkspaceError, new_workspace
from .domain import JobCandidate
from .profile import CandidateProfile
from .search_preferences import SearchPreferences, _seniority, search_jobs

MAX_NEW_DRAFTS_PER_DAY = 5
MAX_DRAFTS_PER_CYCLE = 5
MIN_PREFERENCE_ALIGNMENT = 65


@contextmanager
def per_profile_draft_lock(dsn: str, profile_id: str):
    """Serialize the EXISTING idempotent workspace creations per account.

    The quota counts already-saved drafts. This advisory PostgreSQL
    transaction lock is held across that count and each create_or_get,
    so two browsers/worker replicas cannot both observe the same quota.
    It is NOT an employer submission grant, and never persists a lock row.
    """
    if not str(dsn or "").strip():
        yield
        return
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise AutoDraftSetupRequired("Verified candidate profile required")
    with connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("smartploy:auto-draft:" + profile_id,),
            )
        yield


class AutoDraftSetupRequired(ValueError):
    pass


def _usable_application_url(value: str) -> bool:
    """Reviewable HTTPS employer URL; NEVER fetch URL or infer ATS permission."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        url = urlsplit(value)
    except ValueError:
        return False
    try:
        return bool(
            url.scheme == "https" and url.hostname and url.username is None
            and url.password is None and url.port in {None, 443}
            and url.hostname not in {"localhost", "127.0.0.1", "::1"}
        )
    except ValueError:
        return False


def _on_day(iso: str, now: datetime) -> bool:
    try:
        value = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if value.tzinfo is None:
            return False
        return value.astimezone(timezone.utc).date() == now.astimezone(timezone.utc).date()
    except (ValueError, OverflowError, TypeError):
        return False


@dataclass(frozen=True)
class AutoDraftResult:
    candidates_reviewed: int
    eligible_count: int
    created: tuple[dict[str, str], ...]
    already_prepared: int
    skipped_previous_attempt: int
    remaining_today: int

    def to_dict(self) -> dict:
        return {
            "mode": "local_auto_draft",
            "candidates_reviewed": self.candidates_reviewed,
            "eligible_count": self.eligible_count,
            "created_count": len(self.created),
            "created": list(self.created),
            "already_prepared": self.already_prepared,
            "skipped_previous_attempt": self.skipped_previous_attempt,
            "remaining_today": self.remaining_today,
            "requires_owner_review": True,
            "actual_employer_submissions": 0,
            "external_actions_authorized": False,
            "external_ai_forwarding_performed": False,
        }


def prepare_matching_application_drafts(
    *, profile: CandidateProfile, preferences: SearchPreferences,
    candidates: Sequence[JobCandidate], workspace_repository,
    cv_text: str = "", cv_sha256: str = "",
    previous_attempt=None, limit: int = MAX_DRAFTS_PER_CYCLE,
    now: datetime | None = None,
) -> AutoDraftResult:
    """Make bounded saved drafts from *current source jobs*, NOT applications.

    Caller verifies signed-in owner or active background identity and makes
    the opt-in/criteria revision check. This function never calls an LLM,
    browser, employer API, source fetch or external service. Existing
    statuses and cross-device claims are left untouched.
    """
    if (
        not preferences.completed or preferences.mode != "personalized"
        or not (preferences.roles or preferences.keywords)
        or profile.profile_id != preferences.profile_id
    ):
        raise AutoDraftSetupRequired(
            "Choose personalized target IT job titles or keywords before automatic drafting"
        )
    if type(limit) is not int or not 1 <= limit <= MAX_DRAFTS_PER_CYCLE:
        raise AutoDraftSetupRequired("Local draft batch limit must be 1–5")

    now = now or datetime.now(timezone.utc)
    prior = workspace_repository.list(profile.profile_id, limit=200)
    already_keys = {w.canonical_key for w in prior}
    created_today = sum(_on_day(w.created_at, now) for w in prior)
    budget = min(limit, max(0, MAX_NEW_DRAFTS_PER_DAY - created_today))
    ranked = search_jobs(candidates, preferences)
    by_key = {candidate.canonical_key: candidate for candidate in candidates}
    eligible: list[JobCandidate] = []
    for item in ranked["recommendations"]:
        if (
            not isinstance(item["preference_score"], int)
            or item["preference_score"] < MIN_PREFERENCE_ALIGNMENT
            or item.get("mismatched_fields")
        ):
            continue
        candidate = by_key.get(item["canonical_key"])
        if (
            candidate is None or not candidate.source_current
            or not _usable_application_url(candidate.job.application_url)
        ):
            continue
        # Existing bilingual seniority parser is reused to avoid creating
        # unsolicited senior/lead applications for a junior/mid IT search.
        if (
            _seniority(candidate.job.role_title) == "senior"
            and preferences.seniority != "senior"
            and not any(_seniority(role) == "senior" for role in preferences.roles)
        ):
            continue
        eligible.append(candidate)

    created: list[dict[str, str]] = []
    existing = 0
    claimed = 0
    # Check all selected IDs, not just the first N. An older drafted job
    # should not prevent discovering a newer undrafted one.
    for candidate in eligible:
        if candidate.canonical_key in already_keys:
            existing += 1
            continue
        if budget <= 0:
            break
        if previous_attempt is not None and previous_attempt(candidate):
            claimed += 1
            continue
        try:
            proposal = new_workspace(
                candidate, profile, source_cv_text=cv_text,
                source_cv_sha256=cv_sha256,
            )
        except WorkspaceError:
            # No CV / no approved evidence means never invent credentials,
            # experience, role fit or cover-letter content.
            continue
        stored, is_new = workspace_repository.create_or_get(proposal)
        already_keys.add(candidate.canonical_key)
        if not is_new:
            existing += 1
            continue
        budget -= 1
        created.append({
            "workspace_id": stored.workspace_id,
            "canonical_key": stored.canonical_key,
            "role_title": stored.role_title,
            "company": stored.company,
        })

    return AutoDraftResult(
        candidates_reviewed=len(candidates),
        eligible_count=len(eligible),
        created=tuple(created),
        already_prepared=existing,
        skipped_previous_attempt=claimed,
        remaining_today=max(0, MAX_NEW_DRAFTS_PER_DAY - created_today - len(created)),
    )

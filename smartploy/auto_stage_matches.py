"""SP15j: opt-in, local-only matched IT job draft staging.

Reuses source-polling results, per-user search matcher, original approved
profile/CV and existing application workspace ID/uniqueness. No ObumAI,
browser, recruiter API, profile forwarding, final click, or email sender.
"""
from __future__ import annotations

from collections import Counter
from urllib.parse import urlsplit

from .application_workspace import WorkspaceError, new_workspace
from .application_workspace_storage import WorkspaceRepository, PostgresWorkspaceRepository
from .cv_storage import PostgresCVRepository, StoredCV
from .profile import CandidateProfile
from .profile_storage import PostgresProfileRepository
from .search_preferences import SearchPreferences, search_jobs
from .scoring import score_candidate
from .search_preference_storage import PostgresSearchPreferenceRepository
from .storage import PostgresJobRepository

MINIMUM_PREFERENCE_SCORE = 60
MAX_NEW_PER_USER = 3


def stage_owner_matches(
    *,
    preferences: SearchPreferences,
    candidates: list,
    profile: CandidateProfile,
    cv: StoredCV | None,
    workspaces: WorkspaceRepository,
    claimed_keys: frozenset[str] = frozenset(),
    max_new: int = MAX_NEW_PER_USER,
) -> dict[str, object]:
    """Save at most 3 unsubmitted existing-source matches, never submit.

    Search alignment is NOT verified qualification or employer permission.
    All documents are first-pass DRAFTS with review placeholders.
    """
    if (
        preferences.profile_id != profile.profile_id
        or not preferences.completed or preferences.mode != "personalized"
        or preferences.auto_stage_drafts is not True
    ):
        return {
            "status": "not_opted_in", "created": 0, "existing": 0,
            "considered": 0, "no_employer_actions": True,
        }
    bounded = max(1, min(int(max_new), MAX_NEW_PER_USER))
    ordered = search_jobs(candidates, preferences)["recommendations"]
    created = 0
    existing = 0
    considered = 0
    skipped: Counter[str] = Counter()
    source_cv = cv.text if cv is not None else ""
    source_sha = cv.digest if cv is not None and source_cv else ""
    for card in ordered[:250]:
        if created >= bounded:
            break
        considered += 1
        if (card["preference_score"] < MINIMUM_PREFERENCE_SCORE
                or card["mismatched_fields"]):
            skipped["weak_or_conflicting_fit"] += 1
            continue
        key = str(card["canonical_key"])
        if key in claimed_keys:
            skipped["prior_employer_attempt"] += 1
            continue
        candidate = next((job for job in candidates if job.canonical_key == key), None)
        if candidate is None or not candidate.source_current:
            skipped["not_current"] += 1
            continue
        # Search preference alignment never proves qualifications. Reuse
        # existing mandatory-requirement evidence gaps to prevent a false
        # "high fit" draft when a stated hard employer requirement is unmet.
        if score_candidate(candidate, profile).mandatory_gaps:
            skipped["unverified_mandatory_requirements"] += 1
            continue
        url = urlsplit(str(candidate.job.application_url or ""))
        if (
            url.scheme != "https" or not url.hostname
            or url.username or url.password or url.fragment
            or url.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            skipped["no_verified_application_link"] += 1
            continue
        try:
            draft = new_workspace(
                candidate, profile, source_cv_text=source_cv,
                source_cv_sha256=source_sha,
            )
        except WorkspaceError:
            skipped["missing_approved_cv_evidence"] += 1
            continue
        stored, was_created = workspaces.create_or_get(draft)
        if stored.profile_id != profile.profile_id:
            raise RuntimeError("Auto-staged application changed account")
        if was_created:
            created += 1
        else:
            existing += 1
    return {
        "status": "staged_for_owner_review",
        "created": created, "existing": existing,
        "considered": considered, "skipped": dict(sorted(skipped.items())),
        "no_employer_actions": True, "external_ai_requests": 0,
        "submission_authorized": False, "owner_review_required": True,
    }


def stage_matched_drafts_once(
    dsn: str, *, owner_limit: int = 50, max_new_per_owner: int = MAX_NEW_PER_USER,
) -> dict[str, object]:
    """Use existing source DB and persisted per-owner opt-in, no global PII."""
    preferences = PostgresSearchPreferenceRepository(dsn)
    opted = preferences.list_auto_stage_profiles(limit=owner_limit)
    if not opted:
        return {
            "status": "no_opted_in_users", "accounts_checked": 0,
            "created": 0, "no_employer_actions": True,
        }
    jobs = PostgresJobRepository(dsn).values()
    workspaces = PostgresWorkspaceRepository(dsn)
    cvs = PostgresCVRepository(dsn)
    from psycopg import connect

    totals: Counter[str] = Counter()
    for snapshot in opted:
        # An account may withdraw permission between two worker cycles.
        current = preferences.get(snapshot.profile_id)
        if (
            current.revision != snapshot.revision
            or current.auto_stage_drafts is not True
            or current.mode != "personalized"
        ):
            totals["withdrawn_or_changed"] += 1
            continue
        profile = PostgresProfileRepository(
            dsn, profile_id=current.profile_id
        ).profile()
        with connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT canonical_key FROM smartploy_employer_submit_claims
                       WHERE profile_id=%s""", (current.profile_id,),
                )
                claimed = frozenset(str(row[0]) for row in cur.fetchall())
        report = stage_owner_matches(
            preferences=current, candidates=jobs, profile=profile,
            cv=cvs.get(current.profile_id), workspaces=workspaces,
            claimed_keys=claimed, max_new=max_new_per_owner,
        )
        totals["accounts_checked"] += 1
        totals["created"] += int(report["created"])
        totals["existing"] += int(report["existing"])
    return {
        "status": "healthy", "accounts_checked": totals["accounts_checked"],
        "created": totals["created"], "existing": totals["existing"],
        "withdrawn_or_changed": totals["withdrawn_or_changed"],
        "no_employer_actions": True, "external_ai_requests": 0,
    }

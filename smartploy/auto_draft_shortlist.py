"""Per-user IT job discovery -> local application drafts, with explicit opt-in.

Reuses the ORIGINAL preference scorer, evidence-based fit, job source store,
uploaded CV and existing idempotent application workspace creation.
Never calls ObumAI, browsers or employers. Source worker is private and
reports counts only, without applicant data, job URLs or account identities.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .application_workspace import WorkspaceError, new_workspace
from .application_workspace_storage import PostgresWorkspaceRepository
from .cv_storage import PostgresCVRepository
from .profile import CandidateProfile
from .profile_storage import PostgresProfileRepository
from .scoring import score_candidate
from .search_preferences import SearchPreferences, search_jobs
from .search_preference_storage import PostgresSearchPreferenceRepository
from .storage import PostgresJobRepository

MAX_DRAFTS_PER_USER = 3
MIN_PREFERENCE_SCORE = 70
MIN_APPROVED_FIT_SCORE = 60


@dataclass(frozen=True)
class AutoDraftSummary:
    status: str
    checked: int = 0
    eligible: int = 0
    created: int = 0
    already_prepared: int = 0
    stopped_on_opt_out: bool = False

    def public_counts(self) -> dict[str, object]:
        return {
            "status": self.status, "checked": self.checked,
            "eligible": self.eligible, "created": self.created,
            "already_prepared": self.already_prepared,
            "stopped_on_opt_out": self.stopped_on_opt_out,
            "provider_calls": 0, "employer_actions_performed": False,
            "automatic_submission_authorized": False,
        }


def _safe_current_application_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
        return bool(
            parsed.scheme == "https" and parsed.hostname
            and "." in parsed.hostname
            and not parsed.username and not parsed.password
            and parsed.port in (None, 443)
            and parsed.hostname not in {"localhost", "127.0.0.1"}
        )
    except ValueError:
        return False


def prepare_profile_shortlist(
    profile_id: str, *,
    preferences_repository,
    job_repository,
    profile_repository,
    cv_repository,
    workspace_repository,
    max_new: int = MAX_DRAFTS_PER_USER,
    candidates=None,
) -> AutoDraftSummary:
    """Create bounded, review-required drafts from existing opted-in matches.

    No job is ever submitted to an employer. Qualification requirements are
    verified only against APPROVED profile facts; search settings alone
    cannot be treated as documented experience. The opt-in row is locked
    immediately before every create to serialize user revocation with work.
    """
    bound = max(1, min(int(max_new), MAX_DRAFTS_PER_USER))
    pref: SearchPreferences = preferences_repository.get(profile_id)
    if not (pref.completed and pref.mode == "personalized"
            and pref.auto_draft_enabled and pref.roles):
        return AutoDraftSummary("disabled")
    profile: CandidateProfile = profile_repository.profile()
    if profile.profile_id != profile_id:
        return AutoDraftSummary("owner_mismatch")
    if not profile.approved_facts:
        return AutoDraftSummary("needs_approved_profile")
    cv = cv_repository.get(profile_id)
    # If the uploaded CV has no reliable extract, only approved profile
    # evidence can populate a draft. Never hallucinate missing credentials.
    current = list(candidates if candidates is not None else job_repository.values())
    by_key = {item.canonical_key: item for item in current if item.source_current}
    ranked = search_jobs(current, pref)["recommendations"]
    checked = len(ranked)
    eligible = created = existing = 0
    for match in ranked:
        if created >= bound:
            break
        if (
            match["preference_score"] < MIN_PREFERENCE_SCORE
            or match["mismatched_fields"]
            or not any(reason.startswith("Job title matches ") for reason in match["reasons"])
        ):
            continue
        key = match["canonical_key"]
        candidate = by_key.get(key)
        if candidate is None or not _safe_current_application_url(candidate.job.application_url):
            continue
        fit = score_candidate(candidate, profile)
        if fit.mandatory_gaps or fit.fit_score < MIN_APPROVED_FIT_SCORE:
            continue
        eligible += 1
        with preferences_repository.auto_draft_guard(profile_id, pref.revision) as allowed:
            if not allowed:
                return AutoDraftSummary(
                    "disabled_after_revocation", checked, eligible, created,
                    existing, stopped_on_opt_out=True,
                )
            # Job may have been retired between initial matching and the
            # owner approval guard; re-fetch and enforce exact same content.
            latest = job_repository.get(key)
            if (
                latest is None or not latest.source_current
                or latest.description_fingerprint != candidate.description_fingerprint
                or not _safe_current_application_url(latest.job.application_url)
            ):
                continue
            try:
                proposed = new_workspace(
                    latest, profile, source_cv_text=cv.text if cv else "",
                    source_cv_sha256=cv.digest if cv else "",
                )
            except WorkspaceError:
                continue
            _, added = workspace_repository.create_or_get(proposed)
            created += int(added)
            existing += int(not added)
    return AutoDraftSummary("prepared", checked, eligible, created, existing)


def prepare_worker_shortlists(
    dsn: str, *, profile_limit: int = 100, total_new_limit: int = 30,
) -> dict[str, object]:
    """One bounded continuous-worker cycle; no account details in logs."""
    prefs = PostgresSearchPreferenceRepository(dsn)
    jobs = PostgresJobRepository(dsn)
    workspace = PostgresWorkspaceRepository(dsn)
    cv = PostgresCVRepository(dsn)
    current = jobs.values()
    checked_users = new_count = already = opted_out = 0
    for pid in prefs.list_auto_draft_profiles(limit=profile_limit):
        if new_count >= total_new_limit:
            break
        result = prepare_profile_shortlist(
            pid,
            preferences_repository=prefs,
            job_repository=jobs,
            profile_repository=PostgresProfileRepository(dsn, profile_id=pid),
            cv_repository=cv,
            workspace_repository=workspace,
            max_new=min(MAX_DRAFTS_PER_USER, total_new_limit - new_count),
            candidates=current,
        )
        checked_users += 1
        new_count += result.created
        already += result.already_prepared
        opted_out += int(result.stopped_on_opt_out)
    return {
        "mode": "per_user_opt_in_local_drafts",
        "profiles_checked": checked_users, "drafts_created": new_count,
        "already_prepared": already, "revocations_honored": opted_out,
        "model_calls": 0, "employer_actions_performed": False,
        "automatic_submission_authorized": False,
    }

"""Per-user IT job discovery -> local application drafts, with explicit opt-in.

Reuses the ORIGINAL preference scorer, evidence-based fit, job source store,
uploaded CV and existing idempotent application workspace creation.
Never calls ObumAI, browsers or employers. Source worker is private and
reports counts only, without applicant data, job URLs or account identities.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import re
from urllib.parse import urlsplit

from psycopg import Error as PostgresError

from .application_agents import PostgresApplicationAgentRepository
from .application_workspace import WorkspaceError, new_workspace
from .application_workspace_storage import PostgresWorkspaceRepository
from .cv_storage import PostgresCVRepository
from .domain import sha256_text
from .profile import CandidateProfile
from .profile_storage import PostgresProfileRepository
from .scoring import score_candidate
from .search_preferences import SearchPreferences, search_jobs
from .search_preference_storage import PostgresSearchPreferenceRepository
from .storage import PostgresJobRepository

MAX_DRAFTS_PER_USER = 3
MIN_PREFERENCE_SCORE = 70
MIN_APPROVED_FIT_SCORE = 60
# A source_current flag survives temporary/long-term ATS poll failures.
# Never silently prepare an unattended draft from an old cached listing.
MAX_VERIFIED_AGE = timedelta(hours=48)

# Reuse the three source-policy types actually issued by the existing
# public ATS, national Job Market Finland and approved Kuntarekry adapters.
# Manual bookmarks, ad-hoc imports, browser discoveries and unreviewed
# source policies never gain *unattended* draft authority merely because
# they happen to have a recent observation timestamp.
TRUSTED_AUTO_DRAFT_SOURCES = {
    ("direct_employer_ats", "api"),
    ("national_job_market", "api"),
    ("public_sector_jobs", "feed"),
}


@dataclass(frozen=True)
class AutoDraftSummary:
    status: str
    checked: int = 0
    eligible: int = 0
    created: int = 0
    already_prepared: int = 0
    stopped_on_opt_out: bool = False
    stale_skipped: int = 0
    unverified_source_skipped: int = 0
    agents_started: int = 0
    agents_already_present: int = 0
    agents_unavailable: int = 0
    # SP58: available only to an explicit owner-scoped POST. The shared
    # background worker continues to report aggregate public_counts ONLY.
    created_workspace_ids: tuple[str, ...] = ()

    def owner_review_handoff(self) -> dict[str, object]:
        """Only call after authenticated owner and same-origin POST checks."""
        return {
            **self.public_counts(),
            "created_workspace_ids": list(self.created_workspace_ids),
        }

    def public_counts(self) -> dict[str, object]:
        return {
            "status": self.status, "checked": self.checked,
            "eligible": self.eligible, "created": self.created,
            "already_prepared": self.already_prepared,
            "stopped_on_opt_out": self.stopped_on_opt_out,
            "stale_skipped": self.stale_skipped,
            "unverified_source_skipped": self.unverified_source_skipped,
            "agents_started": self.agents_started,
            "agents_already_present": self.agents_already_present,
            "agents_unavailable": self.agents_unavailable,
            "agent_tracking_external_actions_authorized": False,
            "worker_agent_wakeup_verified": False,
            "provider_calls": 0, "employer_actions_performed": False,
            "automatic_submission_authorized": False,
        }


def _safe_current_application_url(value: str) -> bool:
    """Reuse original browser handoff's HTTPS/no-IP/no-credentials guard."""
    try:
        raw = str(value or "")
        if len(raw) > 1500:
            return False
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        try:
            ip_address(host)
            return False
        except ValueError:
            pass  # Require a DNS hostname, not any IP literal.
        return bool(
            parsed.scheme == "https" and host
            and "." in host and not host.endswith((".localhost", ".local"))
            and not parsed.username and not parsed.password
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def _deadline_open(value: str, *, now: datetime | None = None) -> bool:
    """Don't automatically draft expired or ambiguous employer deadlines.

    Missing dates are normal for genuine public ATS postings. Date-only
    ISO/Finnish deadlines remain valid through the stated day. A timestamp
    must include an explicit timezone to be trusted for automatic drafting.
    """
    raw = str(value or "").strip()
    if not raw:
        return True
    stamp = now or datetime.now(timezone.utc)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return datetime.fromisoformat(raw).date() >= stamp.date()
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw):
            return datetime.strptime(raw, "%d.%m.%Y").date() >= stamp.date()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return False
        return parsed.astimezone(timezone.utc) > stamp
    except (ValueError, OverflowError, TypeError):
        return False


def _original_ashby_source_for_auto_draft(candidate, source_id: str) -> bool:
    """Admit an actual listed Ashby board job, not merely an ATS-like prefix.

    SP20 already imports Ashby through its reviewed read-only public API.
    A local background draft needs a stricter gate than search display: its
    original board URL, optional application path, stable external ID and
    provider/tenant evidence must all describe the SAME exact employer job.
    This creates only a private reviewable draft, never submission rights.
    """
    tenant = source_id.removeprefix("ashby-")
    if not re.fullmatch(r"[a-z0-9-]{1,100}", tenant):
        return False
    details = candidate.job.raw.get("source_details")
    if (
        not isinstance(details, dict)
        or details.get("provider") != "ashby"
        or str(details.get("tenant") or "").casefold() != tenant
        or candidate.metadata.get("terms_review_status") != "approved"
    ):
        return False
    source_url = str(candidate.job.raw.get("source_url") or "")
    if candidate.job.raw.get("source_external_id") != sha256_text(source_url):
        # Reuse Ashby's existing source identity: SHA-256 of the canonical
        # published board URL, NOT a title-derived or user-supplied ID.
        return False
    try:
        source = urlsplit(source_url)
        application = urlsplit(candidate.job.application_url)
        for address in (source, application):
            if (
                address.scheme != "https"
                or address.hostname != "jobs.ashbyhq.com"
                or address.username or address.password
                or address.port not in (None, 443)
                or address.fragment
            ):
                return False
    except ValueError:
        return False
    board_path = source.path.strip("/").split("/")
    apply_path = application.path.strip("/").split("/")
    return (
        len(board_path) == 2
        and board_path[0].casefold() == tenant
        and bool(board_path[1])
        and len(board_path[1]) <= 160
        and apply_path in (board_path, [*board_path, "application"])
    )


def _approved_source_for_auto_draft(candidate) -> bool:
    """Only source-policy-approved employer/public feeds may create drafts.

    The original normalizer attaches source_class/source_mode both to
    candidate.metadata and to job.raw. Requiring agreement protects
    against merge_candidates choosing the job body from a different,
    unreviewed source while retaining a newer verification timestamp.
    Existing source IDs are used as a second independent provenance
    check, not as a substitute for the original source policy.
    """
    source_ids = tuple(candidate.source_ids)
    stored_job_sources = tuple(
        item.strip() for item in str(candidate.job.source or "").split(",")
        if item.strip()
    )
    if (
        not source_ids or set(stored_job_sources) != set(source_ids)
        or candidate.job.raw.get("archived") is True
    ):
        return False
    job_class = candidate.job.raw.get("source_class")
    job_mode = candidate.job.raw.get("source_mode")
    if (
        not isinstance(job_class, str)
        or not isinstance(job_mode, str)
        or job_class != candidate.metadata.get("source_class")
        or job_mode != candidate.metadata.get("source_mode")
        or (job_class, job_mode) not in TRUSTED_AUTO_DRAFT_SOURCES
    ):
        return False
    if job_class == "national_job_market":
        return source_ids == ("job-market-finland",)
    if job_class == "public_sector_jobs":
        return source_ids == ("kuntarekry",)
    # SP40: Ashby's existing public adapter previously discovered Finnish
    # vacancies but its source ID was absent here, so they NEVER advanced to
    # opted-in AutoApply drafts. Use the real adapter's exact provenance;
    # mixed-origin merged records remain in the manual review lane.
    if any(sid.startswith("ashby-") for sid in source_ids):
        return len(source_ids) == 1 and _original_ashby_source_for_auto_draft(
            candidate, source_ids[0]
        )
    return all(
        sid.startswith(("lever-global-", "lever-eu-", "greenhouse-",
                        "smartrecruiters-"))
        for sid in source_ids
    )


def _recently_verified(candidate, *, now: datetime | None = None) -> bool:
    """Use the original source observation timestamps, never the job post date.

    A source_current=True bit only means the last known ATS snapshot listed
    this job. It does NOT prove the employer still lists it if polling stopped.
    Repeated successful ATS imports update last_verified_at; legacy records
    may only have last_seen_at. Ambiguous or future timestamps fail closed.
    """
    stamp = str(candidate.last_verified_at or candidate.last_seen_at or "").strip()
    if not stamp:
        return False
    try:
        verified = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if verified.tzinfo is None:
            return False
        current = now or datetime.now(timezone.utc)
        age = current.astimezone(timezone.utc) - verified.astimezone(timezone.utc)
        return timedelta(0) <= age <= MAX_VERIFIED_AGE
    except (TypeError, ValueError, OverflowError):
        return False


def _same_reviewable_posting(original, latest) -> bool:
    """A description hash alone misses changed employer requirements/links."""
    if original.description_fingerprint != latest.description_fingerprint:
        return False
    significant = (
        "company", "role_title", "application_url", "location", "work_mode",
        "language", "deadline", "requirements", "nice_to_have",
        "required_documents", "questions",
    )
    return all(
        getattr(original.job, field) == getattr(latest.job, field)
        for field in significant
    )


def prepare_profile_shortlist(
    profile_id: str, *,
    preferences_repository,
    job_repository,
    profile_repository,
    cv_repository,
    workspace_repository,
    application_agent_repository=None,
    max_new: int = MAX_DRAFTS_PER_USER,
    candidates=None,
    include_created_workspace_ids: bool = False,
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
    # Do not preload the CV here: the user may replace or delete the file
    # while job ranking is running. Retrieve it only after the account's
    # revocable AutoApply approval has been checked for each draft.
    current = list(candidates if candidates is not None else job_repository.values())
    by_key = {item.canonical_key: item for item in current if item.source_current}
    ranked = search_jobs(current, pref)["recommendations"]
    checked = len(ranked)
    eligible = created = existing = stale_skipped = unverified_skipped = 0
    agents_started = agents_already = agents_unavailable = 0
    # Never keep job IDs in an unattended worker summary unless the caller
    # explicitly requested an owner-private review handoff.
    created_workspace_ids: list[str] = []
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
        if (
            candidate is None
            or not _safe_current_application_url(candidate.job.application_url)
            or not _deadline_open(candidate.job.deadline)
        ):
            continue
        if not _approved_source_for_auto_draft(candidate):
            unverified_skipped += 1
            continue
        if not _recently_verified(candidate):
            stale_skipped += 1
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
                    stale_skipped=stale_skipped,
                    unverified_source_skipped=unverified_skipped,
                    agents_started=agents_started,
                    agents_already_present=agents_already,
                    agents_unavailable=agents_unavailable,
                    created_workspace_ids=tuple(created_workspace_ids),
                )
            # Job may have been retired between initial matching and the
            # owner approval guard; re-fetch and enforce exact same content.
            latest = job_repository.get(key)
            if (
                latest is None or not latest.source_current
                or not _same_reviewable_posting(candidate, latest)
                or not _safe_current_application_url(latest.job.application_url)
                or not _deadline_open(latest.job.deadline)
            ):
                continue
            # The original PostgresJobRepository.get() runs while the
            # revocable account preference guard is held. Check the live
            # snapshot age AGAIN before creating an application workspace.
            if not _approved_source_for_auto_draft(latest):
                unverified_skipped += 1
                continue
            if not _recently_verified(latest):
                stale_skipped += 1
                continue
            # A user can revoke qualifications, replace a CV or delete
            # private evidence after ranking but before this write. Reuse the
            # ORIGINAL profile/CV stores at the guarded insert boundary,
            # never copy a stale in-memory candidate's former approval.
            latest_profile = profile_repository.profile()
            if latest_profile.profile_id != profile_id or not latest_profile.approved_facts:
                continue
            fresh_fit = score_candidate(latest, latest_profile)
            if fresh_fit.mandatory_gaps or fresh_fit.fit_score < MIN_APPROVED_FIT_SCORE:
                continue
            latest_cv = cv_repository.get(profile_id)
            if latest_cv is not None and latest_cv.profile_id != profile_id:
                continue
            try:
                proposed = new_workspace(
                    latest, latest_profile,
                    source_cv_text=latest_cv.text if latest_cv else "",
                    source_cv_sha256=latest_cv.digest if latest_cv else "",
                )
            except WorkspaceError:
                continue
            saved, added = workspace_repository.create_or_get(proposed)
            created += int(added)
            existing += int(not added)
            if added and include_created_workspace_ids:
                # Original create-or-get already verified exact owner and job
                # identity. This is not a provider submission reference.
                created_workspace_ids.append(saved.workspace_id)
            # SP33: This is an INDEPENDENT, default-off permission stored in
            # the original owner criteria JSONB. Use the same revocation-locked
            # scope as draft creation, NOT a background agent scheduler or a
            # fresh employer-submit authority. Never exceed this scan's bound.
            if (
                pref.auto_agent_tracking_enabled and
                agents_started + agents_already + agents_unavailable < bound
            ):
                if application_agent_repository is None:
                    agents_unavailable += 1
                else:
                    try:
                        agent, agent_created = application_agent_repository.create_or_get(
                            profile_id, saved.workspace_id
                        )
                    except PostgresError:
                        # A private draft was already saved; don't report a
                        # successful tracking agent if its storage is down.
                        agents_unavailable += 1
                    else:
                        if agent is None:
                            agents_unavailable += 1
                        else:
                            # Paused and closed cases stay as-is, never resume.
                            agents_started += int(agent_created)
                            agents_already += int(not agent_created)
    return AutoDraftSummary(
        status=(
            "needs_source_refresh" if stale_skipped and not created and not existing
            else "needs_trusted_source" if unverified_skipped and not created and not existing
            else "prepared"
        ),
        checked=checked, eligible=eligible, created=created,
        already_prepared=existing, stale_skipped=stale_skipped,
        unverified_source_skipped=unverified_skipped,
        agents_started=agents_started, agents_already_present=agents_already,
        agents_unavailable=agents_unavailable,
        created_workspace_ids=tuple(created_workspace_ids),
    )


def prepare_worker_shortlists(
    dsn: str, *, profile_limit: int = 100, total_new_limit: int = 30,
) -> dict[str, object]:
    """One bounded continuous-worker cycle; no account details in logs."""
    prefs = PostgresSearchPreferenceRepository(dsn)
    jobs = PostgresJobRepository(dsn)
    workspace = PostgresWorkspaceRepository(dsn)
    # Reuse the existing shared Agent Zero ledger. The optional case is
    # dormant until the operator independently enables its worker task.
    agents = PostgresApplicationAgentRepository(dsn)
    cv = PostgresCVRepository(dsn)
    current = jobs.values()
    checked_users = new_count = already = opted_out = failed_profiles = 0
    agents_started = agents_existing = agents_unavailable = 0
    for pid in prefs.list_auto_draft_profiles(limit=profile_limit):
        if new_count >= total_new_limit:
            break
        checked_users += 1
        revision = None
        failed = False
        try:
            # Keep the original strict revision and opt-out guard on inserts.
            revision = prefs.get(pid).revision
            result = prepare_profile_shortlist(
                pid,
                preferences_repository=prefs,
                job_repository=jobs,
                profile_repository=PostgresProfileRepository(dsn, profile_id=pid),
                cv_repository=cv,
                workspace_repository=workspace,
                application_agent_repository=agents,
                max_new=min(MAX_DRAFTS_PER_USER, total_new_limit - new_count),
                candidates=current,
            )
            new_count += result.created
            already += result.already_prepared
            agents_started += result.agents_started
            agents_existing += result.agents_already_present
            agents_unavailable += result.agents_unavailable
            opted_out += int(result.stopped_on_opt_out)
        except Exception:
            # A faulty CV/profile must not starve the next opted-in account.
            # Never disclose an exception containing applicant or DB details.
            failed = True
        finally:
            if revision is not None:
                try:
                    prefs.mark_auto_draft_checked(pid, revision)
                except Exception:
                    failed = True
            failed_profiles += int(failed)
    return {
        "mode": "per_user_opt_in_local_drafts",
        "profiles_checked": checked_users, "profiles_failed": failed_profiles,
        "drafts_created": new_count,
        "already_prepared": already, "revocations_honored": opted_out,
        "agents_started": agents_started,
        "agents_already_present": agents_existing,
        "agents_unavailable": agents_unavailable,
        "agent_tracking_external_actions_authorized": False,
        "worker_agent_wakeup_verified": False,
        "model_calls": 0, "employer_actions_performed": False,
        "automatic_submission_authorized": False,
    }

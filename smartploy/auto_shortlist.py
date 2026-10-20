"""Opt-in per-account local job shortlist, reusing SmartPloy's worker and drafts.

No LLM, employer POST, browser click or external user-data forwarding.
User approval applies only to LOCAL creation of review-required workspaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Sequence

from psycopg import connect

from .application_workspace import WorkspaceError, new_workspace
from .application_workspace_storage import PostgresWorkspaceRepository
from .cv_storage import PostgresCVRepository
from .domain import JobCandidate
from .profile_storage import PostgresProfileRepository
from .search_preferences import SearchPreferences, search_jobs
from .search_preference_storage import PostgresSearchPreferenceRepository
from .storage import PostgresJobRepository


class AutoShortlistConflict(ValueError):
    pass


class AutoShortlistDenied(ValueError):
    pass


@dataclass(frozen=True)
class AutoShortlistSettings:
    profile_id: str
    enabled: bool = False
    minimum_score: int = 75
    max_per_cycle: int = 3
    revision: int = 0
    last_run_at: str = ""
    last_status: str = "not_run"
    last_created: int = 0
    last_inspected: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "minimum_score": self.minimum_score,
            "max_per_cycle": self.max_per_cycle,
            "revision": self.revision,
            "last_run_at": self.last_run_at,
            "last_status": self.last_status,
            "last_created": self.last_created,
            "last_inspected": self.last_inspected,
            "review_required": True,
            "automatic_employer_submission": False,
            "external_ai_processing": False,
        }


def _check_options(enabled: bool, minimum_score: int, max_per_cycle: int) -> None:
    if not isinstance(enabled, bool):
        raise AutoShortlistDenied("Explicit true/false local-draft permission required")
    if type(minimum_score) is not int or not 70 <= minimum_score <= 100:
        raise AutoShortlistDenied("Minimum alignment must be 70 to 100")
    if type(max_per_cycle) is not int or not 1 <= max_per_cycle <= 10:
        raise AutoShortlistDenied("Draft batch must be 1 to 10")


def _as_item(profile_id: str, row: tuple | None) -> AutoShortlistSettings:
    if row is None:
        return AutoShortlistSettings(profile_id=profile_id)
    return AutoShortlistSettings(
        profile_id=profile_id, enabled=bool(row[0]),
        minimum_score=int(row[1]), max_per_cycle=int(row[2]),
        revision=int(row[3]),
        last_run_at=row[4].isoformat() if row[4] else "",
        last_status=str(row[5]),
        last_created=int(row[6]), last_inspected=int(row[7]),
    )


class PostgresAutoShortlistRepository:
    """Opt-in and worker share ONE row lock. Revocation waits for in-flight run."""

    def __init__(self, dsn: str):
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL required for unattended private drafts")

    _fields = ("enabled,minimum_score,max_per_cycle,revision,last_run_at,"
               "last_status,last_created,last_inspected")

    def get(self, profile_id: str) -> AutoShortlistSettings:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT " + self._fields +
                    " FROM smartploy_auto_shortlist_settings WHERE profile_id=%s",
                    (profile_id,),
                )
                row = cur.fetchone()
        return _as_item(profile_id, row)

    def save(
        self, profile_id: str, *, enabled: bool, minimum_score: int,
        max_per_cycle: int, expected_revision: int,
    ) -> AutoShortlistSettings:
        _check_options(enabled, minimum_score, max_per_cycle)
        if type(expected_revision) is not int or expected_revision < 0:
            raise AutoShortlistDenied("A nonnegative expected revision is required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                # The authenticated API must resolve the owner. Never accept
                # an arbitrary profile_id supplied by an HTTP client.
                cur.execute(
                    """SELECT 1 FROM smartploy_user_profiles p
                       JOIN smartploy_users u ON u.user_id=p.user_id
                       WHERE p.profile_id=%s AND u.status='active'
                       FOR SHARE OF p,u""",
                    (profile_id,),
                )
                if cur.fetchone() is None:
                    raise AutoShortlistDenied("Verified active owner is required")
                cur.execute(
                    """INSERT INTO smartploy_auto_shortlist_settings
                       (profile_id,enabled,minimum_score,max_per_cycle,revision)
                       VALUES (%s,%s,%s,%s,1)
                       ON CONFLICT(profile_id) DO UPDATE SET
                         enabled=EXCLUDED.enabled,
                         minimum_score=EXCLUDED.minimum_score,
                         max_per_cycle=EXCLUDED.max_per_cycle,
                         revision=smartploy_auto_shortlist_settings.revision+1,
                         updated_at=now()
                       WHERE smartploy_auto_shortlist_settings.revision=%s
                       RETURNING enabled,minimum_score,max_per_cycle,revision,
                                 last_run_at,last_status,last_created,last_inspected""",
                    (profile_id,enabled,minimum_score,max_per_cycle,expected_revision),
                )
                row = cur.fetchone()
                # A first write must have expected_revision=0; the INSERT
                # clause otherwise cannot infer that the browser is current.
                if expected_revision != 0 and row is not None and int(row[3]) == 1:
                    raise AutoShortlistConflict("First local-draft permission must start at revision zero")
                if row is None:
                    raise AutoShortlistConflict("Draft settings changed on another device. Reload.")
        return _as_item(profile_id, row)

    def enabled_profiles(self, *, limit: int = 20) -> list[str]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT s.profile_id
                       FROM smartploy_auto_shortlist_settings s
                       JOIN smartploy_user_profiles p ON p.profile_id=s.profile_id
                       JOIN smartploy_users u ON u.user_id=p.user_id
                       WHERE s.enabled=true AND u.status='active'
                       ORDER BY s.last_run_at ASC NULLS FIRST,s.profile_id
                       LIMIT %s""",
                    (max(1,min(int(limit),100)),),
                )
                return [str(row[0]) for row in cur.fetchall()]


def shortlist_matches(
    jobs: Sequence[JobCandidate], prefs: SearchPreferences, *,
    minimum_score: int = 75, limit: int = 100,
) -> list[JobCandidate]:
    """Only fresh, actionable, primary-lane matches without KNOWN mismatch.

    Preference score is NOT a qualification/ATS fit score. Unknown required
    facts are left to the applicant for review, never invented.
    """
    if not prefs.completed or prefs.mode != "personalized":
        return []
    by_key = {item.canonical_key: item for item in jobs if item.source_current}
    rows = search_jobs(jobs, prefs)["recommendations"]
    result = []
    for item in rows:
        score = item["preference_score"]
        if score is None or int(score) < minimum_score or item["mismatched_fields"]:
            continue
        candidate = by_key.get(item["canonical_key"])
        if candidate is None:
            continue
        location = urlsplit(candidate.job.application_url or "")
        if (location.scheme != "https" or not location.hostname
            or "." not in location.hostname or location.username or location.password
            or location.hostname in {"localhost", "127.0.0.1"}
            or location.hostname.endswith((".localhost", ".local"))):
            continue
        result.append(candidate)
        if len(result) >= limit:
            break
    return result


def run_local_shortlist(dsn: str, profile_id: str) -> dict[str, object]:
    """Draft-only. Lock the saved opt-in for the entire local cycle.

    The same lock serializes a user switching this off and concurrent worker
    instances. Database unique(profile_id,canonical_key) is the second
    idempotency layer. In no case is a model/employer contacted.
    """
    repository = PostgresAutoShortlistRepository(dsn)
    with connect(repository.dsn) as conn:
        with conn.cursor() as cur:
            # Same lock acquisition ORDER as account-erasure quarantine:
            # first identity/profile, then explicit saved opt-in. A quarantined
            # user can never receive fresh local documents after revocation.
            cur.execute(
                """SELECT u.status FROM smartploy_users u
                   JOIN smartploy_user_profiles p ON p.user_id=u.user_id
                   WHERE p.profile_id=%s FOR SHARE OF u,p""",
                (profile_id,),
            )
            owner = cur.fetchone()
            if owner is None or owner[0] != "active":
                raise AutoShortlistDenied("Active verified account unavailable")
            cur.execute(
                """SELECT enabled,minimum_score,max_per_cycle,revision,
                          last_run_at,last_status,last_created,last_inspected
                   FROM smartploy_auto_shortlist_settings
                   WHERE profile_id=%s
                   FOR UPDATE SKIP LOCKED""",
                (profile_id,),
            )
            row = cur.fetchone()
            if row is None or not row[0]:
                raise AutoShortlistDenied(
                    "Local shortlist is disabled, already running or account unavailable"
                )
            config = _as_item(profile_id, row)
            preferences = PostgresSearchPreferenceRepository(dsn).get(profile_id)
            created = 0
            inspected = 0
            status = "ready"
            if not preferences.completed or preferences.mode != "personalized":
                status = "needs_preferences"
            else:
                profile = PostgresProfileRepository(dsn, profile_id=profile_id).profile()
                cv = PostgresCVRepository(dsn).get(profile_id)
                original_text = cv.text if cv else ""
                if not original_text.strip() and not profile.approved_facts:
                    status = "needs_profile"
                else:
                    jobs = PostgresJobRepository(dsn).values()
                    candidates = shortlist_matches(
                        jobs, preferences, minimum_score=config.minimum_score,limit=100,
                    )
                    workspace_store = PostgresWorkspaceRepository(dsn)
                    for candidate in candidates:
                        if created >= config.max_per_cycle:
                            break
                        inspected += 1
                        # Source changed or was withdrawn during ranking:
                        # recheck before saving a suggested draft.
                        current = PostgresJobRepository(dsn).get(candidate.canonical_key)
                        if current is None or not current.source_current:
                            continue
                        try:
                            proposal = new_workspace(
                                current, profile,
                                source_cv_text=original_text,
                                source_cv_sha256=cv.digest if cv and original_text.strip() else "",
                            )
                            _, was_created = workspace_store.create_or_get(proposal)
                        except WorkspaceError:
                            # Missing/invalid approved career evidence never
                            # triggers an external model or an invented CV.
                            continue
                        if was_created:
                            created += 1
            cur.execute(
                """UPDATE smartploy_auto_shortlist_settings
                   SET last_run_at=now(),last_status=%s,last_created=%s,
                       last_inspected=%s
                   WHERE profile_id=%s""",
                (status,created,inspected,profile_id),
            )
    return {
        "status": status, "created": created, "inspected": inspected,
        "review_required": True, "employer_submissions": 0,
        "external_ai_processing": False, "external_actions_authorized": False,
    }

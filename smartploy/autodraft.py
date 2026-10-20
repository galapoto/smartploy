"""Opt-in IT-job discovery -> owner-scoped REVIEWABLE drafts. Never sends applications.

Reuses existing source polling, personalized search alignment and deterministic
application-workspace creation. No candidate CV sent to ObumAI or employers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlsplit

from psycopg import connect

from .application_workspace import WorkspaceError, new_workspace
from .application_workspace_storage import WorkspaceRepository
from .cv_storage import StoredCV
from .domain import JobCandidate
from .identity import UserProfileBinding
from .profile import CandidateProfile
from .search_preferences import SearchPreferences, search_jobs


class AutoDraftError(ValueError):
    pass


class AutoDraftConflict(AutoDraftError):
    pass


@dataclass(frozen=True)
class AutoDraftSettings:
    user_id: str
    profile_id: str
    enabled: bool = False
    minimum_score: int = 75
    max_per_cycle: int = 5
    revision: int = 0

    def public(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "minimum_score": self.minimum_score,
            "max_per_cycle": self.max_per_cycle,
            "revision": self.revision,
            "draft_only": True,
            "automatic_employer_submission_authorized": False,
            "external_ai_processing_authorized": False,
        }


def validate_settings(minimum_score: int, max_per_cycle: int) -> None:
    if not 60 <= minimum_score <= 100 or not 1 <= max_per_cycle <= 10:
        raise AutoDraftError("Choose 60–100% search alignment and 1–10 drafts per run")


class MemoryAutoDraftRepository:
    """Fixture equivalent of the production per-user settings table."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], AutoDraftSettings] = {}

    def get(self, user_id: str, profile_id: str) -> AutoDraftSettings:
        return self._values.get((user_id, profile_id)) or AutoDraftSettings(user_id, profile_id)

    def save(
        self, binding: UserProfileBinding, *, expected_revision: int,
        enabled: bool, minimum_score: int, max_per_cycle: int,
    ) -> AutoDraftSettings:
        validate_settings(minimum_score, max_per_cycle)
        if binding.status != "active":
            raise AutoDraftError("An active signed-in account is required")
        previous = self.get(binding.user_id, binding.profile_id)
        if previous.revision != expected_revision:
            raise AutoDraftConflict("Settings changed on another device; reload")
        updated = AutoDraftSettings(
            user_id=binding.user_id, profile_id=binding.profile_id,
            enabled=enabled, minimum_score=minimum_score,
            max_per_cycle=max_per_cycle, revision=previous.revision + 1,
        )
        self._values[(binding.user_id, binding.profile_id)] = updated
        return updated

    def list_enabled(self, limit: int = 25) -> list[AutoDraftSettings]:
        return [x for x in self._values.values() if x.enabled][:max(1, min(limit, 100))]


class PostgresAutoDraftRepository:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("PostgreSQL is required for scheduled drafts")
        self.dsn = dsn

    @staticmethod
    def _record(row: tuple[Any, ...] | None, user_id: str, profile_id: str) -> AutoDraftSettings:
        if row is None:
            return AutoDraftSettings(user_id, profile_id)
        return AutoDraftSettings(
            user_id, profile_id, enabled=bool(row[0]),
            minimum_score=int(row[1]), max_per_cycle=int(row[2]),
            revision=int(row[3]),
        )

    def get(self, user_id: str, profile_id: str) -> AutoDraftSettings:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT enabled, minimum_score, max_per_cycle, revision
                       FROM smartploy_autodraft_settings
                       WHERE user_id=%s AND profile_id=%s""",
                    (user_id, profile_id),
                )
                row = cur.fetchone()
        return self._record(row, user_id, profile_id)

    def save(
        self, binding: UserProfileBinding, *, expected_revision: int,
        enabled: bool, minimum_score: int, max_per_cycle: int,
    ) -> AutoDraftSettings:
        validate_settings(minimum_score, max_per_cycle)
        if binding.status != "active":
            raise AutoDraftError("An active signed-in account is required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT u.status FROM smartploy_users AS u
                       JOIN smartploy_user_profiles AS p ON p.user_id=u.user_id
                       WHERE u.user_id=%s AND p.profile_id=%s FOR UPDATE OF u,p""",
                    (binding.user_id, binding.profile_id),
                )
                row = cur.fetchone()
                if row is None or row[0] != "active":
                    raise AutoDraftError("Verified owner is no longer active")
                cur.execute(
                    """SELECT revision FROM smartploy_autodraft_settings
                       WHERE user_id=%s AND profile_id=%s FOR UPDATE""",
                    (binding.user_id, binding.profile_id),
                )
                previous = cur.fetchone()
                current_revision = int(previous[0]) if previous is not None else 0
                if current_revision != expected_revision:
                    raise AutoDraftConflict("Settings changed on another device; reload")
                cur.execute(
                    """INSERT INTO smartploy_autodraft_settings
                       (user_id,profile_id,enabled,minimum_score,max_per_cycle,revision)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (user_id) DO UPDATE SET
                          enabled=EXCLUDED.enabled,
                          minimum_score=EXCLUDED.minimum_score,
                          max_per_cycle=EXCLUDED.max_per_cycle,
                          revision=EXCLUDED.revision,updated_at=now()
                       WHERE smartploy_autodraft_settings.profile_id=EXCLUDED.profile_id
                       RETURNING enabled,minimum_score,max_per_cycle,revision""",
                    (
                        binding.user_id,binding.profile_id,enabled,minimum_score,
                        max_per_cycle,current_revision+1,
                    ),
                )
                saved = cur.fetchone()
                if saved is None:
                    raise AutoDraftError("Owner profile no longer matches")
        return self._record(saved, binding.user_id, binding.profile_id)

    def list_enabled(self, limit: int = 25) -> list[AutoDraftSettings]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT s.user_id,s.profile_id,s.enabled,s.minimum_score,
                              s.max_per_cycle,s.revision
                       FROM smartploy_autodraft_settings AS s
                       JOIN smartploy_users AS u ON u.user_id=s.user_id
                       JOIN smartploy_user_profiles AS p
                           ON p.user_id=s.user_id AND p.profile_id=s.profile_id
                       WHERE s.enabled=true AND u.status='active'
                       ORDER BY s.updated_at,s.user_id LIMIT %s""",
                    (max(1,min(int(limit),100)),),
                )
                rows = cur.fetchall()
        return [
            AutoDraftSettings(row[0], row[1],bool(row[2]),int(row[3]),
                              int(row[4]),int(row[5]))
            for row in rows
        ]


def draft_matching_jobs(
    binding: UserProfileBinding, settings: AutoDraftSettings,
    preferences: SearchPreferences, candidates: Sequence[JobCandidate],
    profile: CandidateProfile, cv: StoredCV | None,
    workspaces: WorkspaceRepository,
    *, still_enabled: Any = None,
) -> dict[str, Any]:
    """Prepare only high-alignment, currently published owner-specific drafts.

    This is NOT an applicant qualification check or consent to apply.
    The existing workspace unique (profile_id, canonical_key) prevents
    duplicate drafts on concurrent scheduled/manual runs.
    """
    if (
        binding.status != "active"
        or binding.user_id != settings.user_id
        or binding.profile_id != settings.profile_id
        or profile.profile_id != binding.profile_id
        or not settings.enabled
    ):
        raise AutoDraftError("Active owner-scoped automatic draft opt-in is required")
    validate_settings(settings.minimum_score, settings.max_per_cycle)
    if not preferences.completed or preferences.profile_id != binding.profile_id:
        return _summary("setup_required")
    if preferences.mode != "personalized" or not (preferences.roles or preferences.keywords):
        return _summary("personalized_search_required")
    source = cv.text.strip() if cv is not None else ""
    approved = profile.approved_evidence().get("facts", {})
    if not source and not any(approved.values()):
        return _summary("profile_evidence_required")

    ranked = search_jobs(candidates, preferences)
    indexed = {item.canonical_key: item for item in candidates if item.source_current}
    created: list[dict[str, Any]] = []
    existing = 0
    skipped = 0
    for card in ranked["recommendations"]:
        if len(created) >= settings.max_per_cycle:
            break
        candidate = indexed.get(card["canonical_key"])
        if candidate is None or int(card["preference_score"]) < settings.minimum_score:
            continue
        if card["mismatched_fields"]:
            skipped += 1
            continue
        # No applicant or job data is fetched from employer sites here.
        url = urlsplit(str(candidate.job.application_url or ""))
        if (
            url.scheme != "https" or not url.hostname or url.username
            or url.password or url.fragment or url.port in {0}
            or url.hostname in {"localhost","127.0.0.1","::1"}
        ):
            skipped += 1
            continue
        if still_enabled is not None and not still_enabled():
            return {
                **_summary("disabled_during_cycle"), "created": created,
                "created_count": len(created), "existing_count": existing,
                "skipped_count": skipped,
            }
        try:
            proposal = new_workspace(
                candidate, profile, source_cv_text=source,
                source_cv_sha256=cv.digest if cv is not None and source else "",
            )
        except WorkspaceError:
            skipped += 1
            continue
        workspace, is_new = workspaces.create_or_get(proposal)
        if is_new:
            created.append({
                "workspace_id": workspace.workspace_id,
                "canonical_key": candidate.canonical_key,
                "preference_score": card["preference_score"],
                "reasons": card["reasons"][:3],
            })
        else:
            existing += 1
    return {
        **_summary("ready"), "created": created,
        "created_count": len(created), "existing_count": existing,
        "skipped_count": skipped,
        "inspected_recommendations": len(ranked["recommendations"]),
    }


def _summary(status: str) -> dict[str, Any]:
    return {
        "status": status, "created": [], "created_count": 0,
        "existing_count": 0, "skipped_count": 0,
        "external_actions_performed": False,
        "external_ai_calls": 0, "employer_applications_submitted": 0,
        "requires_individual_review_before_application": True,
    }

"""Read-only tenant-scoped preview of unattended ObumAI draft readiness.

No network/model/browser/employer calls. A preview is not authorization:
any future actual dispatch must recheck exact source, identity, evidence
and consent under the PostgreSQL revocation lock immediately before send.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256

from .ai_processing_consent import JobAIConsent, PostgresJobAIConsentRepository
from .domain import JobCandidate, canonical_json
from .identity import PostgresIdentityRepository, UserProfileBinding
from .preparation_storage import PostgresPreparationRepository
from .preparations import (
    PreparationNotEligible, approved_evidence_snapshot,
    build_preparation, ensure_preparation_eligible, preparation_job_snapshot,
)
from .profile import CandidateProfile
from .profile_storage import PostgresProfileRepository
from .scoring import score_candidate
from .storage import PostgresJobRepository


READINESS_REASONS = frozenset({
    "ready", "owner_inactive", "job_missing", "job_not_current",
    "source_restricted", "profile_mismatch", "no_approved_evidence",
    "insufficient_fit", "snapshot_changed", "existing_preparation",
    "consent_changed",
})


@dataclass(frozen=True)
class PreparationReadiness:
    reason: str
    job_hash: str = ""
    evidence_hash: str = ""
    package_id: str = ""

    def __post_init__(self) -> None:
        if self.reason not in READINESS_REASONS:
            raise ValueError("Unknown consent planning reason")


def _digest(value: dict) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def assess_consent_readiness(
    consent: JobAIConsent,
    binding: UserProfileBinding | None,
    candidate: JobCandidate | None,
    profile: CandidateProfile | None,
) -> PreparationReadiness:
    """Inspect immutable snapshot match without mutating a profile or queue."""
    if (
        binding is None or binding.status != "active"
        or binding.user_id != consent.user_id
        or binding.profile_id != consent.profile_id
        or not consent.active
    ):
        return PreparationReadiness("owner_inactive")
    if candidate is None or candidate.canonical_key != consent.canonical_key:
        return PreparationReadiness("job_missing")
    if not candidate.source_current:
        return PreparationReadiness("job_not_current")
    if candidate.job.raw.get("external_ai_forwarding_allowed") is not True:
        return PreparationReadiness("source_restricted")
    if profile is None or profile.profile_id != consent.profile_id:
        return PreparationReadiness("profile_mismatch")
    evidence = approved_evidence_snapshot(profile)
    if int(evidence.get("approved_fact_count") or 0) == 0:
        return PreparationReadiness("no_approved_evidence")
    score = score_candidate(candidate, profile)
    try:
        ensure_preparation_eligible(candidate, profile, score)
    except PreparationNotEligible:
        return PreparationReadiness("insufficient_fit")

    snapshot = preparation_job_snapshot(candidate)
    job_hash = _digest(snapshot)
    evidence_hash = _digest(evidence)
    if (job_hash, evidence_hash) != (
        consent.job_snapshot_sha256, consent.evidence_sha256
    ):
        return PreparationReadiness("snapshot_changed")

    package = build_preparation(candidate, profile, score)
    if (package.job_snapshot_sha256, package.evidence_sha256) != (
        job_hash, evidence_hash
    ):
        # Local identity contract mismatch: never assume permission.
        return PreparationReadiness("snapshot_changed")
    return PreparationReadiness(
        "ready", job_hash=job_hash,
        evidence_hash=evidence_hash, package_id=package.package_id,
    )


def preview_consented_preparations(dsn: str, *, limit: int = 50) -> dict[str, object]:
    """Bounded consent/eligibility scan. Aggregates ONLY; no PII in return.

    No claim, lease, reservation or network connection to ObumAI. Every
    repository after candidate discovery is scoped to the verified owner.
    Missing DB services raise instead of silently authorizing work.
    """
    bounded = max(1, min(int(limit), 500))
    ledger = PostgresJobAIConsentRepository(dsn)
    identities = PostgresIdentityRepository(dsn)
    jobs = PostgresJobRepository(dsn)
    candidates = ledger.list_active_verified(limit=bounded)
    counts: Counter[str] = Counter()
    for consent in candidates:
        binding = identities.get(consent.user_id)
        if (
            binding is None or binding.status != "active"
            or binding.profile_id != consent.profile_id
        ):
            counts["owner_inactive"] += 1
            continue
        candidate = jobs.get(consent.canonical_key)
        # Never use SMARTPLOY_PROFILE_ID, user-supplied email, or default
        # profile when loading approved evidence for another account.
        profile = PostgresProfileRepository(
            dsn, profile_id=consent.profile_id
        ).profile()
        readiness = assess_consent_readiness(consent, binding, candidate, profile)
        if readiness.reason != "ready":
            counts[readiness.reason] += 1
            continue
        # A queue listing can race with withdrawal. The second read detects
        # ordinary changes; this is still a preview and never a send gate.
        if not ledger.authorized(
            binding, consent.canonical_key,
            readiness.job_hash, readiness.evidence_hash,
        ):
            counts["consent_changed"] += 1
            continue
        prior = PostgresPreparationRepository(
            dsn, profile_id=consent.profile_id
        ).get(readiness.package_id)
        counts["existing_preparation" if prior else "ready"] += 1
    return {
        "mode": "read_only_consent_preview",
        "checked": len(candidates),
        "counts": dict(sorted(counts.items())),
        "model_calls": 0,
        "processing_started": False,
        "external_actions_authorized": False,
        "release_approved": False,
    }

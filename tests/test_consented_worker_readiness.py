"""Synthetic multi-tenant consent readiness; never sends AI requests."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import json

import pytest

import smartploy.consented_worker_readiness as planner
from smartploy.ai_processing_consent import JobAIConsent
from smartploy.domain import SourceObservation, SourcePolicy, canonical_json, normalize_observation
from smartploy.identity import UserProfileBinding
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.preparations import approved_evidence_snapshot, preparation_job_snapshot
from smartploy.scoring import ScoreResult


def _digest(value: dict) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _scope():
    source = SourcePolicy(
        source_id="synthetic", display_name="Synthetic",
        source_class="manual", allowed_modes=("manual",),
    )
    result = normalize_observation(SourceObservation(
        source_id="synthetic", source_mode="manual",
        source_url="https://jobs.example.invalid/apply",
        raw_text="Synthetic Python job",
        payload={
            "company": "Fictional Employer", "role_title": "Python Developer",
            "description": "Python development", "requirements": ["Python"],
            "external_ai_forwarding_allowed": True,
        },
        observed_at="2026-10-17T08:00:00+00:00",
    ), source)
    assert result.candidate is not None
    candidate = result.candidate
    fact = ProfileFact(
        fact_type="skill", value="Python", source="synthetic",
        approved=True,
    ).normalized()
    profile = CandidateProfile(profile_id="profile-a", facts=(fact,))
    binding = UserProfileBinding(
        user_id="usr-synthetic-a", profile_id="profile-a",
        email="same@example.invalid", status="active",
    )
    consent = JobAIConsent(
        consent_id="consent-a", user_id=binding.user_id,
        profile_id=binding.profile_id, canonical_key=candidate.canonical_key,
        job_snapshot_sha256=_digest(preparation_job_snapshot(candidate)),
        evidence_sha256=_digest(approved_evidence_snapshot(profile)),
        revision=1, granted_at="2026-10-17T08:00:00+00:00",
    )
    return consent, binding, candidate, profile


def _eligible_score(job, profile):
    return ScoreResult(
        canonical_key=job.canonical_key,
        fit_score=92, priority_score=91,
        queue="auto_prepare",
        fit_breakdown={"skill_overlap": 100},
        priority_breakdown={"fit": 91},
        matched_evidence_ids=tuple(x.fact_id for x in profile.approved_facts),
        matched_requirements=("Python",),
        mandatory_gaps=(), preferred_gaps=(), prepare_recommended=True,
    )


def test_snapshot_preflight_denies_stale_or_wrong_tenant_without_model(monkeypatch):
    monkeypatch.setattr(planner, "score_candidate", _eligible_score)
    consent, binding, job, profile = _scope()
    permitted = planner.assess_consent_readiness(consent, binding, job, profile)
    assert permitted.reason == "ready"
    assert permitted.job_hash == consent.job_snapshot_sha256
    assert permitted.evidence_hash == consent.evidence_sha256
    assert permitted.package_id.startswith("prep-")
    cases = [
        (consent, None, job, profile, "owner_inactive"),
        (consent, replace(binding, status="disabled"), job, profile, "owner_inactive"),
        (consent, replace(binding, profile_id="profile-b"), job, profile, "owner_inactive"),
        (replace(consent, revoked_at="2026-10-17T09:00:00Z"), binding, job, profile, "owner_inactive"),
        (consent, binding, None, profile, "job_missing"),
        (consent, binding, replace(job, source_current=False), profile, "job_not_current"),
        (consent, binding, replace(job, job=replace(
            job.job, raw={**job.job.raw, "external_ai_forwarding_allowed": False}
        )), profile, "source_restricted"),
        (consent, binding, job, replace(profile, profile_id="profile-b"), "profile_mismatch"),
        (consent, binding, job, CandidateProfile(profile_id="profile-a"), "no_approved_evidence"),
        (replace(consent, job_snapshot_sha256="0" * 64), binding, job, profile, "snapshot_changed"),
        (replace(consent, evidence_sha256="1" * 64), binding, job, profile, "snapshot_changed"),
    ]
    for grant, user, candidate, evidence, reason in cases:
        assert planner.assess_consent_readiness(
            grant, user, candidate, evidence
        ).reason == reason
    monkeypatch.setattr(planner, "score_candidate", lambda job, profile: replace(
        _eligible_score(job, profile), fit_score=12
    ))
    assert planner.assess_consent_readiness(
        consent, binding, job, profile
    ).reason == "insufficient_fit"


def test_preview_uses_verified_individual_profile_and_returns_only_aggregate_counts(monkeypatch):
    monkeypatch.setattr(planner, "score_candidate", _eligible_score)
    consent, binding, job, profile = _scope()
    revoked = replace(
        consent, consent_id="consent-revoked", user_id="usr-synthetic-revoked",
        profile_id="profile-revoked", revoked_at="2026-10-17T10:00:00Z",
    )
    missing = replace(
        consent, consent_id="consent-missing", user_id="usr-synthetic-missing",
        profile_id="profile-missing", canonical_key="synthetic-missing-job",
    )
    cross = replace(
        consent, consent_id="consent-cross", user_id="usr-synthetic-cross",
        profile_id="profile-cross",
    )
    active = [consent, revoked, missing, cross]
    details = []
    fake_users = {
        binding.user_id: binding,
        "usr-synthetic-missing": UserProfileBinding(
            user_id="usr-synthetic-missing", profile_id="profile-missing",
            email=binding.email,
        ),
        "usr-synthetic-cross": UserProfileBinding(
            user_id="usr-synthetic-cross", profile_id="profile-other",
            email=binding.email,
        ),
    }

    class FakeLedger:
        def __init__(self, dsn):
            assert dsn == "postgresql://synthetic"
        def list_active_verified(self, *, limit):
            assert limit == 50
            return active
        def authorized(self, who, key, job_hash, evidence_hash):
            details.append(("check", who.profile_id))
            assert who.user_id == binding.user_id
            return True

    class FakeIdentities:
        def __init__(self, dsn): pass
        def get(self, user_id):
            details.append(("identity", user_id))
            return fake_users.get(user_id)

    class FakeJobs:
        def __init__(self, dsn): pass
        def get(self, key):
            details.append(("job", key))
            return job if key == job.canonical_key else None

    class FakeProfile:
        def __init__(self, dsn, *, profile_id):
            self.profile_id = profile_id
            details.append(("profile", profile_id))
        def profile(self):
            return profile if self.profile_id == binding.profile_id else CandidateProfile(
                profile_id=self.profile_id
            )

    class FakePrep:
        def __init__(self, dsn, *, profile_id):
            assert profile_id == binding.profile_id
        def get(self, package_id):
            return None

    monkeypatch.setattr(planner, "PostgresJobAIConsentRepository", FakeLedger)
    monkeypatch.setattr(planner, "PostgresIdentityRepository", FakeIdentities)
    monkeypatch.setattr(planner, "PostgresJobRepository", FakeJobs)
    monkeypatch.setattr(planner, "PostgresProfileRepository", FakeProfile)
    monkeypatch.setattr(planner, "PostgresPreparationRepository", FakePrep)
    report = planner.preview_consented_preparations("postgresql://synthetic")
    assert report["checked"] == 4
    assert report["counts"] == {
        "job_missing": 1, "owner_inactive": 2, "ready": 1,
    }
    assert report["model_calls"] == 0
    assert report["release_approved"] is False
    assert details.count(("profile", "profile-a")) == 1
    assert ("profile", "profile-other") not in details
    redacted = json.dumps(report)
    assert "usr-synthetic" not in redacted
    assert "profile-a" not in redacted
    assert "Fictional Employer" not in redacted
    assert "same@example.invalid" not in redacted


def test_preview_db_failure_does_not_convert_to_authorized_work(monkeypatch):
    def denied(_dsn):
        raise RuntimeError("Synthetic database unreachable")
    monkeypatch.setattr(planner, "PostgresJobAIConsentRepository", denied)
    with pytest.raises(RuntimeError, match="database unreachable"):
        planner.preview_consented_preparations("postgresql://synthetic")

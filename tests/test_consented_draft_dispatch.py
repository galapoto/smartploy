"""An internal dispatch call may send only once after full consent and rights checks.

Only synthetic service and HTTP clients; no real model, browser, or employer call.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

import smartploy.consented_draft_dispatch as runner
import smartploy.consented_worker_readiness as readiness
from smartploy.ai_processing_consent import ConsentDispatchDenied, JobAIConsent
from smartploy.application_storage import MemoryApplicationRepository
from smartploy.domain import SourceObservation, SourcePolicy, canonical_json, normalize_observation
from smartploy.identity import UserProfileBinding
from smartploy.obumai import ObumAIError
from smartploy.preparation_storage import MemoryPreparationRepository
from smartploy.preparations import approved_evidence_snapshot, preparation_job_snapshot
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.scoring import ScoreResult
from smartploy.service import SmartployService


def _hash(data):
    return sha256(canonical_json(data).encode("utf-8")).hexdigest()


def _score(job, profile):
    return ScoreResult(
        canonical_key=job.canonical_key, fit_score=95,
        priority_score=95, queue="auto_prepare",
        fit_breakdown={"skill_overlap": 100},
        priority_breakdown={"fit": 95},
        matched_evidence_ids=tuple(f.fact_id for f in profile.approved_facts),
        matched_requirements=("Python",), mandatory_gaps=(),
        preferred_gaps=(), prepare_recommended=True,
    )


def _setup(monkeypatch, *, failure="", after_reservation=None):
    result = normalize_observation(SourceObservation(
        source_id="synthetic", source_mode="manual",
        source_url="https://jobs.example.invalid/role",
        raw_text="Fictional Python job",
        payload={
            "company": "Fixture Employer", "role_title": "Junior Python Developer",
            "description": "Python for a junior team",
            "requirements": ["Python"], "external_ai_forwarding_allowed": True,
        }, observed_at="2026-10-17T08:00:00+00:00",
    ), SourcePolicy("synthetic", "Fixture", "manual", ("manual",)))
    assert result.candidate is not None
    job = result.candidate
    profile = CandidateProfile(
        profile_id="profile-synthetic-user",
        facts=(ProfileFact("skill", "Python", "synthetic", approved=True).normalized(),),
    )
    binding = UserProfileBinding(
        user_id="usr-synthetic-user", profile_id=profile.profile_id,
        email="shared@example.invalid",
    )
    consent = JobAIConsent(
        consent_id="consent-synthetic", user_id=binding.user_id,
        profile_id=binding.profile_id, canonical_key=job.canonical_key,
        job_snapshot_sha256=_hash(preparation_job_snapshot(job)),
        evidence_sha256=_hash(approved_evidence_snapshot(profile)),
        revision=1, granted_at="2026-10-17T08:00:00+00:00",
    )
    records = []
    attempts = {}
    prep = MemoryPreparationRepository(profile_id=profile.profile_id)
    applications = MemoryApplicationRepository(profile_id=profile.profile_id)

    class Service(SmartployService):
        def __init__(self):
            super().__init__(
                preparation_repository=prep,
                application_repository=applications,
            )
        def get_job(self, key):
            assert key == job.canonical_key
            return job
        def profile(self):
            return profile

    service = Service()

    class IdentityRepo:
        def __init__(self, dsn):
            assert dsn == "postgresql://synthetic"
        def get(self, user_id):
            return binding if binding.user_id == user_id else None

    class ConsentRepo:
        def __init__(self, dsn):
            assert dsn == "postgresql://synthetic"
        @contextmanager
        def hold_authorized_dispatch(self, who, key, job_hash, evidence_hash):
            records.append(("guard", who.profile_id))
            if (
                not consent.active or who.profile_id != consent.profile_id
                or key != consent.canonical_key
                or job_hash != consent.job_snapshot_sha256
                or evidence_hash != consent.evidence_sha256
            ):
                raise ConsentDispatchDenied("Synthetic withdrawal or snapshot mismatch")
            yield consent

    class AttemptRepo:
        def __init__(self, dsn):
            assert dsn == "postgresql://synthetic"
        def reserve(self, grant, package, request_id):
            records.append(("reserve", package.profile_id))
            if after_reservation is not None:
                after_reservation()
            if package.package_id in attempts:
                return SimpleNamespace(state=attempts[package.package_id]), False
            attempts[package.package_id] = "sending"
            return SimpleNamespace(state="sending"), True
        def acknowledge(self, package_id, request_id, remote_id, *, profile_id):
            records.append(("acknowledge", profile_id))
            attempts[package_id] = "acknowledged"
        def mark_uncertain(self, package_id, request_id, *, profile_id, code):
            records.append(("uncertain", code))
            attempts[package_id] = "uncertain"

    class Client:
        def __init__(self):
            self.settings = SimpleNamespace(timeout_seconds=10)
            self.calls = []
        def submit_reasoning(self, *, action, candidate, candidate_evidence,
                             instructions, client_request_id_override):
            records.append(("send", candidate.canonical_key))
            self.calls.append(client_request_id_override)
            assert action == "application_package_v1"
            assert candidate_evidence["profile_id"] == binding.profile_id
            assert client_request_id_override.startswith("smartploy:application_package_v1:prep-")
            assert "external_actions_authorized: true" not in instructions
            if failure == "remote":
                raise ObumAIError("synthetic remote may have accepted request")
            if failure == "invalid":
                return {"job": {"id": "", "state": "queued"}}
            if failure == "crash":
                raise RuntimeError("synthetic unexpected exception")
            return {
                "job": {"id": "remote-synthetic-job", "state": "queued"},
                "smartploy_client_request_id": client_request_id_override,
            }

    client = Client()
    monkeypatch.setattr(runner, "PostgresIdentityRepository", IdentityRepo)
    monkeypatch.setattr(runner, "PostgresJobAIConsentRepository", ConsentRepo)
    monkeypatch.setattr(runner, "PostgresDraftDispatchRepository", AttemptRepo)
    monkeypatch.setattr(
        runner, "_scoped_application_service",
        lambda dsn, obum, profile_id: (
            service if profile_id == binding.profile_id
            else pytest.fail("Cross-tenant service forbidden")
        ),
    )
    monkeypatch.setattr(readiness, "score_candidate", _score)
    monkeypatch.setattr(runner, "score_candidate", _score)
    return consent, client, records, attempts, prep, applications, job, profile, binding


def test_guarded_draft_dispatch_persists_before_remote_send_and_never_repeats(monkeypatch):
    consent, client, records, attempts, prep, apps, job, profile, binding = _setup(monkeypatch)
    result = runner.dispatch_consented_draft_once("postgresql://synthetic", consent, client)
    assert result["status"] == "acknowledged"
    assert result["model_dispatch_attempted"] is True
    assert result["employer_actions_authorized"] is False
    assert result["worker_registered"] is False
    assert len(client.calls) == 1
    assert [s[0] for s in records] == ["guard", "reserve", "send", "acknowledge"]
    assert all(x == "acknowledged" for x in attempts.values())
    assert len(prep.list()) == 1
    assert len(apps.list()) == 1
    assert prep.list()[0].obum_client_request_id == client.calls[0]
    assert prep.list()[0].profile_id == binding.profile_id
    assert apps.list()[0].profile_id == binding.profile_id
    assert apps.list()[0].has_been_submitted is False

    second = runner.dispatch_consented_draft_once("postgresql://synthetic", consent, client)
    assert second["status"] == "existing_preparation"
    assert second["model_dispatch_attempted"] is False
    assert len(client.calls) == 1


@pytest.mark.parametrize("failure", ["remote", "invalid", "crash"])
def test_failed_or_ambiguous_send_never_automatically_repeats(monkeypatch, failure):
    consent, client, records, attempts, prep, _, _, _, _ = _setup(
        monkeypatch, failure=failure,
    )
    if failure == "crash":
        with pytest.raises(RuntimeError, match="unexpected"):
            runner.dispatch_consented_draft_once("postgresql://synthetic", consent, client)
    else:
        reply = runner.dispatch_consented_draft_once("postgresql://synthetic", consent, client)
        assert reply["status"] == "uncertain" and reply["model_dispatch_attempted"]
    assert list(attempts.values()) == ["uncertain"]
    assert len(client.calls) == 1
    assert records.index(("reserve", consent.profile_id)) < records.index(
        ("send", consent.canonical_key)
    )
    result = runner.dispatch_consented_draft_once("postgresql://synthetic", consent, client)
    assert result["status"] == "existing_preparation"
    assert len(client.calls) == 1
    assert len(prep.list()) == 1


def test_revoked_or_changed_job_never_enters_outbound_code(monkeypatch):
    consent, client, records, _, _, _, job, _, _ = _setup(monkeypatch)
    with pytest.raises(ConsentDispatchDenied):
        runner.dispatch_consented_draft_once(
            "postgresql://synthetic",
            replace(consent, job_snapshot_sha256="a" * 64),
            client,
        )
    assert client.calls == []
    assert records == [("guard", consent.profile_id)]


def test_bounded_remote_timeout_fails_before_any_database_or_network_action(monkeypatch):
    consent, client, records, _, _, _, _, _, _ = _setup(monkeypatch)
    client.settings.timeout_seconds = 180
    with pytest.raises(ValueError, match="timeout"):
        runner.dispatch_consented_draft_once("postgresql://synthetic", consent, client)
    assert records == [] and client.calls == []

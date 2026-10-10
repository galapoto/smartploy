"""Smartploy application service layer."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from .application_storage import ApplicationRepository, MemoryApplicationRepository
from .applications import ApplicationEvent, ApplicationRecord
from .artifact_storage import ArtifactRepository, MemoryArtifactRepository
from .artifacts import ApplicationArtifact
from .document_render import render_application_artifacts
from .domain import (
    DiscoveryResult,
    JobCandidate,
    JobSearchFilters,
    SourceObservation,
    SourcePolicy,
    apply_filters,
    normalize_observation,
    utc_now_iso,
)
from .obumai import ObumAIClient, ObumAIError
from .preparation_storage import (
    MemoryPreparationRepository,
    PreparationRepository,
    with_runtime,
)
from .preparations import (
    ApplicationPreparation,
    PreparationNotEligible,
    PreparationResultError,
    action_for_contract,
    approved_evidence_ids,
    build_preparation,
    draft_schema_for_contract,
    ensure_preparation_eligible,
    instructions_for_contract,
    parse_draft_output,
)
from .profile import CandidateProfile
from .profile_storage import MemoryProfileRepository, ProfileRepository
from .scoring import ScoreResult, rank_candidates, score_candidate
from .storage import JobRepository, MemoryJobRepository, SourceHealth


class SmartployService:
    def __init__(
        self,
        *,
        repository: JobRepository | None = None,
        profile_repository: ProfileRepository | None = None,
        preparation_repository: PreparationRepository | None = None,
        application_repository: ApplicationRepository | None = None,
        artifact_repository: ArtifactRepository | None = None,
        obumai: ObumAIClient | None = None,
    ) -> None:
        self.repository = repository or MemoryJobRepository()
        self.profile_repository = profile_repository or MemoryProfileRepository()
        self.preparation_repository = preparation_repository or MemoryPreparationRepository()
        self.application_repository = application_repository or MemoryApplicationRepository()
        self.artifact_repository = artifact_repository or MemoryArtifactRepository()
        self.obumai = obumai
        self._policies: dict[str, SourcePolicy] = {}

    def register_source(self, policy: SourcePolicy) -> SourcePolicy:
        item = policy.normalized()
        self._policies[item.source_id] = item
        return item

    def source(self, source_id: str) -> SourcePolicy | None:
        key = str(source_id or "").strip().casefold().replace(" ", "-")
        return self._policies.get(key)

    def ingest(
        self,
        observation: SourceObservation,
        *,
        filters: JobSearchFilters | None = None,
    ) -> DiscoveryResult:
        policy = self.source(observation.source_id)
        if policy is None:
            return DiscoveryResult(status="blocked", reasons=("source_policy_not_registered",))

        result = normalize_observation(observation, policy)
        if not result.discovered or result.candidate is None:
            return result

        candidate = result.candidate
        external_id = str(observation.source_external_id or "").strip()
        if external_id:
            existing_key = self.repository.canonical_key_for_source_external_id(
                candidate.job.source,
                external_id,
            )
            if existing_key and existing_key != candidate.canonical_key:
                candidate = replace(candidate, canonical_key=existing_key)

        decision = apply_filters(candidate, filters or JobSearchFilters())
        if not decision.accepted:
            return DiscoveryResult(
                status="filtered",
                reasons=decision.reasons,
                candidate=candidate,
                filter_decision=decision,
            )

        stored = self.repository.upsert(candidate, observation)
        return DiscoveryResult(
            status="discovered",
            candidate=stored,
            filter_decision=decision,
        )

    def get_job(self, canonical_key: str) -> JobCandidate | None:
        return self.repository.get(canonical_key)

    def list_jobs(self) -> list[JobCandidate]:
        return self.repository.values()

    def source_health(self, source_id: str) -> SourceHealth | None:
        return self.repository.get_source_health(source_id)

    def list_source_health(self) -> list[SourceHealth]:
        return self.repository.list_source_health()

    def storage_status(self) -> dict[str, Any]:
        return self.repository.storage_status()

    def profile(self) -> CandidateProfile:
        return self.profile_repository.profile()

    def profile_summary(self) -> dict[str, Any]:
        try:
            summary = self.profile().summary()
        except Exception as exc:
            return {
                "profile_id": getattr(self.profile_repository, "profile_id", "default"),
                "ready": False,
                "error": type(exc).__name__,
            }
        return {**summary, "ready": True}

    def score_job(self, canonical_key: str, *, now: datetime | None = None) -> ScoreResult:
        candidate = self.get_job(canonical_key)
        if candidate is None:
            raise KeyError(canonical_key)
        return score_candidate(candidate, self.profile(), now=now)

    def rankings(self, *, now: datetime | None = None) -> list[ScoreResult]:
        return rank_candidates(self.list_jobs(), self.profile(), now=now)

    def submit_obumai(
        self,
        canonical_key: str,
        *,
        action: str,
        instructions: str = "",
    ) -> dict[str, Any]:
        candidate = self.get_job(canonical_key)
        if candidate is None:
            raise KeyError(canonical_key)
        if self.obumai is None:
            raise ObumAIError("ObumAI integration is not configured")
        if candidate.job.raw.get("external_ai_forwarding_allowed") is False:
            raise ObumAIError(
                "source terms restrict forwarding this job posting to external AI processing"
            )
        evidence = self.profile().approved_evidence()
        if int(evidence.get("approved_fact_count") or 0) == 0:
            raise ObumAIError("no approved Smartploy profile evidence is available")
        return self.obumai.submit_reasoning(
            action=action,
            candidate=candidate,
            candidate_evidence=evidence,
            instructions=instructions,
        )

    def _apply_obum_job(
        self,
        item: ApplicationPreparation,
        job: dict[str, Any],
        *,
        client_request_id: str | None = None,
    ) -> ApplicationPreparation:
        timestamp = utc_now_iso()
        state = str(job.get("state") or "").strip().casefold()
        obum_job_id = str(job.get("id") or item.obum_job_id).strip()
        if not obum_job_id:
            return with_runtime(
                item,
                status="failed",
                error="ObumAI job projection did not contain an id",
                updated_at=timestamp,
            )

        if state in {"queued", "running", "blocked", "failed", "cancelled"}:
            completed_at = timestamp if state in {"failed", "cancelled"} else ""
            return with_runtime(
                item,
                status=state,
                obum_job_id=obum_job_id,
                obum_client_request_id=client_request_id,
                completed_at=completed_at,
                error=str(job.get("terminal_reason_code") or "") if state == "failed" else "",
                updated_at=timestamp,
            )

        if state == "completed":
            raw_output = str(job.get("output_text") or "")
            try:
                result = parse_draft_output(
                    raw_output,
                    allowed_evidence_ids=approved_evidence_ids(item.evidence_snapshot),
                    expected_schema=draft_schema_for_contract(item.preparation_contract),
                    evidence_snapshot=item.evidence_snapshot,
                )
            except PreparationResultError as exc:
                return with_runtime(
                    item,
                    status="completed_unparsed",
                    obum_job_id=obum_job_id,
                    obum_client_request_id=client_request_id,
                    raw_output=raw_output,
                    error=str(exc),
                    completed_at=timestamp,
                    updated_at=timestamp,
                )
            return with_runtime(
                item,
                status="completed",
                obum_job_id=obum_job_id,
                obum_client_request_id=client_request_id,
                result=result,
                raw_output=raw_output,
                error="",
                completed_at=timestamp,
                updated_at=timestamp,
            )

        return with_runtime(
            item,
            status="failed",
            obum_job_id=obum_job_id,
            obum_client_request_id=client_request_id,
            error=f"unsupported ObumAI job state: {state or 'missing'}",
            completed_at=timestamp,
            updated_at=timestamp,
        )

    def _sync_application(self, preparation: ApplicationPreparation) -> ApplicationRecord:
        return self.application_repository.sync_preparation(preparation)

    def get_application(self, application_id: str) -> ApplicationRecord | None:
        return self.application_repository.get(application_id)

    def list_applications(self, *, limit: int = 100) -> list[ApplicationRecord]:
        return self.application_repository.list(limit=limit)

    def application_events(self, application_id: str, *, limit: int = 500) -> list[ApplicationEvent]:
        return self.application_repository.events(application_id, limit=limit)

    def application_summary(self) -> dict[str, Any]:
        return self.application_repository.summary()

    def dashboard(self) -> dict[str, Any]:
        rankings = self.rankings()

        def card(score: ScoreResult) -> dict[str, Any]:
            candidate = self.get_job(score.canonical_key)
            job = candidate.job if candidate is not None else None
            return {
                **score.to_dict(),
                "job": None
                if job is None
                else {
                    "company": job.company,
                    "role_title": job.role_title,
                    "location": job.location,
                    "work_mode": job.work_mode,
                    "deadline": job.deadline,
                    "application_url": job.application_url,
                    "employer_sector": str(job.raw.get("employer_sector") or "unknown"),
                    "source_ids": list(candidate.source_ids) if candidate is not None else [],
                    "posted_at": candidate.posted_at if candidate is not None else "",
                    "first_seen_at": candidate.first_seen_at if candidate is not None else "",
                    "last_seen_at": candidate.last_seen_at if candidate is not None else "",
                    "source_current": candidate.source_current if candidate is not None else False,
                    "source_attribution": str(job.raw.get("source_attribution") or ""),
                    "ai_preparation_allowed": job.raw.get("external_ai_forwarding_allowed") is not False,
                },
            }

        top = [
            card(item)
            for item in rankings
            if item.queue in {"exceptional", "auto_prepare", "review"}
        ][:50]
        possible = [card(item) for item in rankings if item.queue == "possible"][:100]

        preparation_counts: dict[str, int] = {}
        for item in self.list_preparations(limit=500):
            preparation_counts[item.status] = preparation_counts.get(item.status, 0) + 1

        return {
            "top_matches": top,
            "possible_matches": possible,
            "preparation_counts": preparation_counts,
            "applications": self.application_summary(),
            "source_health": [item.to_dict() for item in self.list_source_health()],
            "profile": self.profile_summary(),
            "external_actions_authorized": False,
        }

    def prepare_job(
        self,
        canonical_key: str,
        *,
        now: datetime | None = None,
    ) -> ApplicationPreparation:
        candidate = self.get_job(canonical_key)
        if candidate is None:
            raise KeyError(canonical_key)

        if candidate.job.raw.get("external_ai_forwarding_allowed") is False:
            raise PreparationNotEligible(
                "source terms restrict forwarding this job posting to external AI processing"
            )

        profile = self.profile()
        score = score_candidate(candidate, profile, now=now)
        ensure_preparation_eligible(candidate, profile, score)
        proposed = build_preparation(candidate, profile, score)
        stored, created = self.preparation_repository.create_or_get(proposed)

        if not created:
            if stored.status in {
                "queued",
                "running",
                "blocked",
                "completed",
                "completed_unparsed",
                "cancelled",
            }:
                self._sync_application(stored)
                return stored
            if stored.status == "failed" and stored.obum_job_id:
                self._sync_application(stored)
                return stored

        if self.obumai is None:
            failed = with_runtime(
                stored,
                status="failed",
                error="ObumAI integration is not configured",
                completed_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            failed = self.preparation_repository.save(failed)
            self._sync_application(failed)
            raise ObumAIError("ObumAI integration is not configured")

        evidence = profile.approved_evidence()
        action = action_for_contract(stored.preparation_contract)
        instructions = instructions_for_contract(stored.preparation_contract)
        request_id = self.obumai.client_request_id(
            action=action,
            candidate=candidate,
            candidate_evidence=evidence,
            instructions=instructions,
        )
        awaiting = with_runtime(
            stored,
            status="created",
            obum_client_request_id=request_id,
            error="",
            completed_at="",
            updated_at=utc_now_iso(),
        )
        awaiting = self.preparation_repository.save(awaiting)
        self._sync_application(awaiting)

        try:
            response = self.obumai.submit_reasoning(
                action=action,
                candidate=candidate,
                candidate_evidence=evidence,
                instructions=instructions,
            )
        except ObumAIError as exc:
            failed = with_runtime(
                awaiting,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            failed = self.preparation_repository.save(failed)
            self._sync_application(failed)
            raise

        job = response.get("job")
        if not isinstance(job, dict):
            failed = with_runtime(
                awaiting,
                status="failed",
                error="ObumAI create response did not contain a job projection",
                completed_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            failed = self.preparation_repository.save(failed)
            self._sync_application(failed)
            raise ObumAIError("ObumAI create response did not contain a job projection")

        updated = self._apply_obum_job(
            awaiting,
            job,
            client_request_id=str(response.get("smartploy_client_request_id") or request_id),
        )
        saved = self.preparation_repository.save(updated)
        self._materialize_artifacts(saved)
        self._sync_application(saved)
        return saved

    def _materialize_artifacts(
        self,
        preparation: ApplicationPreparation,
    ) -> list[ApplicationArtifact]:
        if preparation.status != "completed":
            return []
        rendered = render_application_artifacts(preparation)
        stored: list[ApplicationArtifact] = []
        for artifact in rendered:
            item, _ = self.artifact_repository.create_or_get(artifact)
            stored.append(item)
        return stored

    def get_artifact(self, artifact_id: str) -> ApplicationArtifact | None:
        return self.artifact_repository.get(artifact_id)

    def list_artifacts(self, package_id: str) -> list[ApplicationArtifact]:
        return self.artifact_repository.list_for_package(package_id)

    def get_preparation(self, package_id: str) -> ApplicationPreparation | None:
        return self.preparation_repository.get(package_id)

    def list_preparations(self, *, limit: int = 100) -> list[ApplicationPreparation]:
        return self.preparation_repository.list(limit=limit)

    def refresh_preparation(self, package_id: str) -> ApplicationPreparation:
        item = self.get_preparation(package_id)
        if item is None:
            raise KeyError(package_id)
        if item.status in {"completed", "completed_unparsed", "cancelled"}:
            if item.status == "completed":
                self._materialize_artifacts(item)
            self._sync_application(item)
            return item
        if not item.obum_job_id:
            if item.status == "failed":
                self._sync_application(item)
                return item
            raise ObumAIError("preparation has no ObumAI job id")
        if self.obumai is None:
            raise ObumAIError("ObumAI integration is not configured")

        job = self.obumai.get_job(item.obum_job_id)
        updated = self._apply_obum_job(
            item,
            job,
            client_request_id=item.obum_client_request_id,
        )
        saved = self.preparation_repository.save(updated)
        self._materialize_artifacts(saved)
        self._sync_application(saved)
        return saved

    def prepare_eligible(
        self,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[ApplicationPreparation]:
        prepared: list[ApplicationPreparation] = []
        for score in self.rankings(now=now):
            if len(prepared) >= max(1, limit):
                break
            if not score.prepare_recommended:
                continue
            try:
                prepared.append(self.prepare_job(score.canonical_key, now=now))
            except PreparationNotEligible:
                continue
        return prepared

"""Smartploy application service layer."""

from __future__ import annotations

from typing import Any, Mapping

from .domain import (
    DiscoveryResult,
    JobCandidate,
    JobSearchFilters,
    SourceObservation,
    SourcePolicy,
    apply_filters,
    normalize_observation,
)
from .obumai import ObumAIClient, ObumAIError
from .storage import JobRepository, MemoryJobRepository, SourceHealth


class SmartployService:
    def __init__(
        self,
        *,
        repository: JobRepository | None = None,
        obumai: ObumAIClient | None = None,
    ) -> None:
        self.repository = repository or MemoryJobRepository()
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

        decision = apply_filters(result.candidate, filters or JobSearchFilters())
        if not decision.accepted:
            return DiscoveryResult(
                status="filtered",
                reasons=decision.reasons,
                candidate=result.candidate,
                filter_decision=decision,
            )

        stored = self.repository.upsert(result.candidate, observation)
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

    def submit_obumai(
        self,
        canonical_key: str,
        *,
        action: str,
        candidate_evidence: Mapping[str, Any],
        instructions: str = "",
    ) -> dict[str, Any]:
        candidate = self.get_job(canonical_key)
        if candidate is None:
            raise KeyError(canonical_key)
        if self.obumai is None:
            raise ObumAIError("ObumAI integration is not configured")
        return self.obumai.submit_reasoning(
            action=action,
            candidate=candidate,
            candidate_evidence=candidate_evidence,
            instructions=instructions,
        )

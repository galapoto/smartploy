"""Smartploy application service layer."""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .domain import (
    DiscoveryResult,
    JobCandidate,
    JobDiscoveryIndex,
    JobSearchFilters,
    SourceObservation,
    SourcePolicy,
)
from .obumai import ObumAIClient, ObumAIError


class SmartployService:
    def __init__(
        self,
        *,
        index: Optional[JobDiscoveryIndex] = None,
        obumai: Optional[ObumAIClient] = None,
    ) -> None:
        self.index = index or JobDiscoveryIndex()
        self.obumai = obumai
        self._policies: Dict[str, SourcePolicy] = {}

    def register_source(self, policy: SourcePolicy) -> SourcePolicy:
        item = policy.normalized()
        self._policies[item.source_id] = item
        return item

    def source(self, source_id: str) -> Optional[SourcePolicy]:
        key = str(source_id or "").strip().casefold().replace(" ", "-")
        return self._policies.get(key)

    def ingest(
        self,
        observation: SourceObservation,
        *,
        filters: Optional[JobSearchFilters] = None,
    ) -> DiscoveryResult:
        policy = self.source(observation.source_id)
        if policy is None:
            return DiscoveryResult(status="blocked", reasons=("source_policy_not_registered",))
        return self.index.ingest(observation, policy, filters)

    def get_job(self, canonical_key: str) -> Optional[JobCandidate]:
        return self.index.get(canonical_key)

    def list_jobs(self) -> list[JobCandidate]:
        return self.index.values()

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

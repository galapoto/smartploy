"""Exhaustive public ATS polling with fail-closed retirement semantics."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import JobSearchFilters, utc_now_iso
from ..service import SmartployService
from .public_ats import PublicATSAdapter


@dataclass(frozen=True)
class PublicATSPollSummary:
    source_id: str
    provider: str
    tenant: str
    status: str
    item_count: int
    discovered_count: int
    filtered_count: int
    blocked_count: int
    retired_count: int
    attempted_at: str
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "provider": self.provider,
            "tenant": self.tenant,
            "status": self.status,
            "item_count": self.item_count,
            "discovered_count": self.discovered_count,
            "filtered_count": self.filtered_count,
            "blocked_count": self.blocked_count,
            "retired_count": self.retired_count,
            "attempted_at": self.attempted_at,
            "error": self.error,
        }


def poll_public_ats(
    service: SmartployService,
    adapter: PublicATSAdapter,
    *,
    filters: JobSearchFilters | None = None,
    attempted_at: str | None = None,
) -> PublicATSPollSummary:
    timestamp = attempted_at or utc_now_iso()
    service.register_source(adapter.policy())
    previous_ids = service.repository.active_source_external_ids(adapter.source_id)

    try:
        observations = adapter.fetch_all(observed_at=timestamp)
        current_ids = [item.source_external_id for item in observations]
        if any(not item for item in current_ids):
            raise ValueError("ATS adapter returned an item without source external ID")
        if len(current_ids) != len(set(current_ids)):
            raise ValueError("ATS adapter returned duplicate source external IDs")
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:2000]
        service.repository.record_source_attempt(
            adapter.source_id,
            status="failed",
            item_count=0,
            parser_version=adapter.parser_version,
            attempted_at=timestamp,
            error=message,
            metadata={
                "provider": adapter.provider,
                "tenant": adapter.config.tenant,
                "stack": adapter.config.stack,
                "complete_snapshot": False,
            },
        )
        return PublicATSPollSummary(
            source_id=adapter.source_id,
            provider=adapter.provider,
            tenant=adapter.config.tenant,
            status="failed",
            item_count=0,
            discovered_count=0,
            filtered_count=0,
            blocked_count=0,
            retired_count=0,
            attempted_at=timestamp,
            error=message,
        )

    discovered = 0
    filtered = 0
    blocked = 0
    for observation in observations:
        result = service.ingest(observation, filters=filters)
        if result.status == "discovered":
            discovered += 1
        elif result.status == "filtered":
            filtered += 1
        else:
            blocked += 1

    retired = 0
    if blocked == 0:
        missing_ids = previous_ids - set(current_ids)
        for external_id in sorted(missing_ids):
            if service.repository.retire_source_external_id(
                adapter.source_id,
                external_id,
                archived_at=timestamp,
            ) is not None:
                retired += 1

    status = "degraded" if blocked else "healthy"
    error = (
        f"{blocked} ATS items blocked during normalization; retirement skipped"
        if blocked
        else ""
    )
    service.repository.record_source_attempt(
        adapter.source_id,
        status=status,
        item_count=len(observations),
        parser_version=adapter.parser_version,
        attempted_at=timestamp,
        error=error,
        metadata={
            "provider": adapter.provider,
            "tenant": adapter.config.tenant,
            "stack": adapter.config.stack,
            "complete_snapshot": blocked == 0,
            "discovered_count": discovered,
            "filtered_count": filtered,
            "blocked_count": blocked,
            "retired_count": retired,
            "external_ai_forwarding_allowed": adapter.config.external_ai_forwarding_allowed,
            "employer_sector": adapter.config.employer_sector,
        },
    )
    return PublicATSPollSummary(
        source_id=adapter.source_id,
        provider=adapter.provider,
        tenant=adapter.config.tenant,
        status=status,
        item_count=len(observations),
        discovered_count=discovered,
        filtered_count=filtered,
        blocked_count=blocked,
        retired_count=retired,
        attempted_at=timestamp,
        error=error,
    )

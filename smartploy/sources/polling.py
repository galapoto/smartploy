"""Source polling orchestration with durable health reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain import JobSearchFilters, SourceObservation, SourcePolicy, utc_now_iso
from ..service import SmartployService


class FeedAdapter(Protocol):
    source_id: str
    parser_version: str
    def policy(self) -> SourcePolicy: ...
    def fetch(self, *, observed_at: str | None = None) -> list[SourceObservation]: ...


@dataclass(frozen=True)
class PollSummary:
    source_id: str
    status: str
    item_count: int
    discovered_count: int
    filtered_count: int
    blocked_count: int
    attempted_at: str
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "item_count": self.item_count,
            "discovered_count": self.discovered_count,
            "filtered_count": self.filtered_count,
            "blocked_count": self.blocked_count,
            "attempted_at": self.attempted_at,
            "error": self.error,
        }


def poll_feed(
    service: SmartployService,
    adapter: FeedAdapter,
    *,
    filters: JobSearchFilters | None = None,
    attempted_at: str | None = None,
) -> PollSummary:
    timestamp = attempted_at or utc_now_iso()
    service.register_source(adapter.policy())
    try:
        observations = adapter.fetch(observed_at=timestamp)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:2000]
        service.repository.record_source_attempt(
            adapter.source_id,
            status="failed",
            item_count=0,
            parser_version=adapter.parser_version,
            attempted_at=timestamp,
            error=message,
        )
        return PollSummary(
            source_id=adapter.source_id,
            status="failed",
            item_count=0,
            discovered_count=0,
            filtered_count=0,
            blocked_count=0,
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

    status = "degraded" if blocked else "healthy"
    error = f"{blocked} feed items blocked during normalization" if blocked else ""
    service.repository.record_source_attempt(
        adapter.source_id,
        status=status,
        item_count=len(observations),
        parser_version=adapter.parser_version,
        attempted_at=timestamp,
        error=error,
        metadata={
            "discovered_count": discovered,
            "filtered_count": filtered,
            "blocked_count": blocked,
        },
    )
    return PollSummary(
        source_id=adapter.source_id,
        status=status,
        item_count=len(observations),
        discovered_count=discovered,
        filtered_count=filtered,
        blocked_count=blocked,
        attempted_at=timestamp,
        error=error,
    )

"""Polling orchestration for Job Market Finland P67 published + archived data."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import JobSearchFilters, utc_now_iso
from ..service import SmartployService
from .jobmarket_finland import (
    ORIGINAL_SOURCE_LABEL,
    JobMarketFinlandAdapter,
)


@dataclass(frozen=True)
class JobMarketFinlandPollSummary:
    source_id: str
    status: str
    published_count: int
    archived_count: int
    discovered_count: int
    filtered_count: int
    blocked_count: int
    retired_count: int
    unknown_archived_count: int
    attempted_at: str
    modified_from: str
    modified_to: str
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "published_count": self.published_count,
            "archived_count": self.archived_count,
            "discovered_count": self.discovered_count,
            "filtered_count": self.filtered_count,
            "blocked_count": self.blocked_count,
            "retired_count": self.retired_count,
            "unknown_archived_count": self.unknown_archived_count,
            "attempted_at": self.attempted_at,
            "modified_from": self.modified_from,
            "modified_to": self.modified_to,
            "error": self.error,
        }


def poll_jobmarket_finland(
    service: SmartployService,
    adapter: JobMarketFinlandAdapter,
    *,
    modified_from: str,
    modified_to: str,
    filters: JobSearchFilters | None = None,
    attempted_at: str | None = None,
) -> JobMarketFinlandPollSummary:
    timestamp = attempted_at or utc_now_iso()
    service.register_source(adapter.policy())

    try:
        published = adapter.fetch_window(
            status="PUBLISHED",
            modified_from=modified_from,
            modified_to=modified_to,
            observed_at=timestamp,
        )
        archived = adapter.fetch_window(
            status="ARCHIVED",
            modified_from=modified_from,
            modified_to=modified_to,
            observed_at=timestamp,
        )
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
                "environment": adapter.environment,
                "source_attribution": ORIGINAL_SOURCE_LABEL,
                "external_ai_forwarding_allowed": False,
            },
        )
        return JobMarketFinlandPollSummary(
            source_id=adapter.source_id,
            status="failed",
            published_count=0,
            archived_count=0,
            discovered_count=0,
            filtered_count=0,
            blocked_count=0,
            retired_count=0,
            unknown_archived_count=0,
            attempted_at=timestamp,
            modified_from=modified_from,
            modified_to=modified_to,
            error=message,
        )

    discovered = 0
    filtered = 0
    blocked = 0
    for observation in published.observations:
        result = service.ingest(observation, filters=filters)
        if result.status == "discovered":
            discovered += 1
        elif result.status == "filtered":
            filtered += 1
        else:
            blocked += 1

    retired = 0
    unknown_archived = 0
    for item in archived.archived:
        closed = service.repository.retire_source_external_id(
            adapter.source_id,
            item.external_id,
            archived_at=item.archived_at or item.last_modified or timestamp,
        )
        if closed is None:
            unknown_archived += 1
        else:
            retired += 1

    status = "degraded" if blocked else "healthy"
    error = f"{blocked} P67 published items blocked during normalization" if blocked else ""
    service.repository.record_source_attempt(
        adapter.source_id,
        status=status,
        item_count=published.item_count + archived.item_count,
        parser_version=adapter.parser_version,
        attempted_at=timestamp,
        error=error,
        metadata={
            "environment": adapter.environment,
            "source_attribution": ORIGINAL_SOURCE_LABEL,
            "external_ai_forwarding_allowed": False,
            "published_count": published.item_count,
            "archived_count": archived.item_count,
            "discovered_count": discovered,
            "filtered_count": filtered,
            "blocked_count": blocked,
            "retired_count": retired,
            "unknown_archived_count": unknown_archived,
            "modified_from": modified_from,
            "modified_to": modified_to,
        },
    )

    return JobMarketFinlandPollSummary(
        source_id=adapter.source_id,
        status=status,
        published_count=published.item_count,
        archived_count=archived.item_count,
        discovered_count=discovered,
        filtered_count=filtered,
        blocked_count=blocked,
        retired_count=retired,
        unknown_archived_count=unknown_archived,
        attempted_at=timestamp,
        modified_from=modified_from,
        modified_to=modified_to,
        error=error,
    )

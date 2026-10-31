#!/usr/bin/env python3
"""Run one credential-gated Job Market Finland P67 incremental poll."""

from __future__ import annotations

from datetime import datetime, timezone
import os

from smartploy.service import SmartployService
from smartploy.sources.jobmarket_finland import (
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
    compute_modified_window,
)
from smartploy.sources.jobmarket_finland_polling import poll_jobmarket_finland
from smartploy.storage import PostgresJobRepository


def main() -> int:
    settings = JobMarketFinlandSettings.from_env()
    if settings is None:
        raise SystemExit("Job Market Finland API is disabled; set JOBMARKET_FINLAND_API_ENABLED=true")

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required for Job Market Finland polling")

    repository = PostgresJobRepository(dsn)
    health = repository.get_source_health("job-market-finland")
    modified_from, modified_to = compute_modified_window(
        last_success_at=health.last_success_at if health else "",
        now=datetime.now(timezone.utc),
        initial_lookback_minutes=settings.initial_lookback_minutes,
        overlap_minutes=settings.overlap_minutes,
    )

    service = SmartployService(repository=repository)
    adapter = JobMarketFinlandAdapter(settings, quarantine_missing_identity=True)
    try:
        summary = poll_jobmarket_finland(
            service,
            adapter,
            modified_from=modified_from,
            modified_to=modified_to,
        )
    finally:
        adapter.close()

    print(summary.to_dict())
    return 0 if summary.status in {"healthy", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

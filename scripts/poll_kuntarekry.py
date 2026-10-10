#!/usr/bin/env python3
"""Run one authorized Kuntarekry feed poll."""

from __future__ import annotations

import os

from smartploy.service import SmartployService
from smartploy.sources.kuntarekry import KuntarekryFeedAdapter, KuntarekryFeedSettings
from smartploy.sources.polling import poll_feed
from smartploy.storage import MemoryJobRepository, PostgresJobRepository


def main() -> int:
    settings = KuntarekryFeedSettings.from_env()
    if settings is None:
        raise SystemExit("KUNTAREKRY_FEED_URL is required")

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    repository = PostgresJobRepository(dsn) if dsn else MemoryJobRepository()
    service = SmartployService(repository=repository)
    adapter = KuntarekryFeedAdapter(settings)
    try:
        summary = poll_feed(service, adapter)
    finally:
        adapter.close()
    print(summary.to_dict())
    return 0 if summary.status in {"healthy", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

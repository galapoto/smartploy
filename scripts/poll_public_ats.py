#!/usr/bin/env python3
"""Poll all configured read-only public ATS sources once."""

from __future__ import annotations

import json
import os

from smartploy.service import SmartployService
from smartploy.sources.public_ats import (
    PublicATSRuntimeSettings,
    build_public_ats_adapter,
    load_public_ats_sources,
)
from smartploy.sources.public_ats_polling import poll_public_ats
from smartploy.storage import PostgresJobRepository


def main() -> int:
    configs = load_public_ats_sources()
    if not configs:
        raise SystemExit("no public ATS sources configured")

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required for public ATS polling")

    repository = PostgresJobRepository(dsn)
    service = SmartployService(repository=repository)
    runtime = PublicATSRuntimeSettings.from_env()

    summaries = []
    failed = False
    for config in configs:
        adapter = build_public_ats_adapter(config, runtime)
        try:
            summary = poll_public_ats(service, adapter)
        finally:
            adapter.close()
        summaries.append(summary.to_dict())
        if summary.status == "failed":
            failed = True

    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

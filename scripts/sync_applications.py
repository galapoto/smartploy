#!/usr/bin/env python3
"""Backfill/synchronize Smartploy CRM projections from preparation packages."""

from __future__ import annotations

import os

from smartploy.application_storage import PostgresApplicationRepository
from smartploy.preparation_storage import PostgresPreparationRepository
from smartploy.storage import PostgresJobRepository


def main() -> int:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required")

    jobs = PostgresJobRepository(dsn)
    if not jobs.storage_status().get("ready"):
        raise SystemExit("Smartploy PostgreSQL schema is not ready; run scripts/migrate.py")

    preparations = PostgresPreparationRepository(dsn)
    applications = PostgresApplicationRepository(dsn)
    limit = max(1, min(int(os.getenv("SMARTPLOY_CRM_SYNC_LIMIT", "500")), 5000))

    synced = []
    for item in preparations.list(limit=limit):
        record = applications.sync_preparation(item)
        synced.append(
            {
                "application_id": record.application_id,
                "canonical_key": record.canonical_key,
                "state": record.state,
                "package_id": record.package_id,
            }
        )

    print(
        {
            "synced": len(synced),
            "applications": synced,
            "submitted_claims_created": 0,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Queue eligible Smartploy application-draft packages through ObumAI."""

from __future__ import annotations

import os

from smartploy.obumai import ObumAIClient, ObumAISettings
from smartploy.preparation_storage import PostgresPreparationRepository
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


def main() -> int:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required")

    obum_settings = ObumAISettings.from_env()
    if obum_settings is None:
        raise SystemExit("OBUMAI_BASE_URL is required")

    jobs = PostgresJobRepository(dsn)
    status = jobs.storage_status()
    if not status.get("ready"):
        raise SystemExit("Smartploy PostgreSQL schema is not ready; run scripts/migrate.py")

    profile_id = os.getenv("SMARTPLOY_PROFILE_ID", "default").strip() or "default"
    service = SmartployService(
        repository=jobs,
        profile_repository=PostgresProfileRepository(dsn, profile_id=profile_id),
        preparation_repository=PostgresPreparationRepository(dsn),
        obumai=ObumAIClient(obum_settings),
    )
    limit = max(1, min(int(os.getenv("SMARTPLOY_PREPARE_BATCH_LIMIT", "20")), 100))
    packages = service.prepare_eligible(limit=limit)

    print(
        {
            "eligible_processed": len(packages),
            "packages": [
                {
                    "package_id": item.package_id,
                    "canonical_key": item.canonical_key,
                    "status": item.status,
                    "obum_job_id": item.obum_job_id,
                }
                for item in packages
            ],
            "external_actions_authorized": False,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Refresh active Smartploy application-draft packages from ObumAI."""

from __future__ import annotations

import os

from smartploy.application_storage import PostgresApplicationRepository
from smartploy.obumai import ObumAIClient, ObumAIError, ObumAISettings
from smartploy.preparation_storage import PostgresPreparationRepository
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.service import SmartployService
from smartploy.storage import PostgresJobRepository


ACTIVE_STATES = {"queued", "running", "blocked"}


def main() -> int:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required")

    obum_settings = ObumAISettings.from_env()
    if obum_settings is None:
        raise SystemExit("OBUMAI_BASE_URL is required")

    jobs = PostgresJobRepository(dsn)
    if not jobs.storage_status().get("ready"):
        raise SystemExit("Smartploy PostgreSQL schema is not ready; run scripts/migrate.py")

    preparations = PostgresPreparationRepository(dsn)
    profile_id = os.getenv("SMARTPLOY_PROFILE_ID", "default").strip() or "default"
    service = SmartployService(
        repository=jobs,
        profile_repository=PostgresProfileRepository(dsn, profile_id=profile_id),
        preparation_repository=preparations,
        application_repository=PostgresApplicationRepository(dsn),
        obumai=ObumAIClient(obum_settings),
    )

    limit = max(1, min(int(os.getenv("SMARTPLOY_REFRESH_BATCH_LIMIT", "50")), 500))
    updated = []
    failures = []
    for item in preparations.list(limit=limit):
        if item.status not in ACTIVE_STATES:
            continue
        try:
            current = service.refresh_preparation(item.package_id)
        except ObumAIError as exc:
            failures.append({"package_id": item.package_id, "error": str(exc)})
            continue
        updated.append(
            {
                "package_id": current.package_id,
                "status": current.status,
                "obum_job_id": current.obum_job_id,
            }
        )

    print(
        {
            "updated": updated,
            "refresh_failures": failures,
            "external_actions_authorized": False,
        }
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

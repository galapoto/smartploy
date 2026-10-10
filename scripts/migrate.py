#!/usr/bin/env python3
"""Apply Smartploy PostgreSQL migrations."""

from __future__ import annotations

import os

from smartploy.storage import PostgresJobRepository


def main() -> int:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required")
    repository = PostgresJobRepository(dsn)
    repository.migrate()
    print("Smartploy migration 001: applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

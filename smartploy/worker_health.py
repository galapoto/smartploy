"""Worker-specific Docker health probe.

The worker uses the API image but does not serve /healthz on port 8090.
Docker itself checks whether the worker's foreground process is still alive;
this probe additionally verifies the worker can reach its scheduling database.
It requires no public HTTP listener, extra credentials, or new packages.
"""
from __future__ import annotations

import os
import sys

from psycopg import connect


def worker_storage_ready(dsn: str) -> bool:
    """True only when the PostgreSQL worker-scheduling schema can be queried."""
    if not dsn:
        return False
    try:
        with connect(dsn, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('public.smartploy_worker_tasks') IS NOT NULL"
                )
                return cursor.fetchone() == (True,)
    except Exception:
        # Connection exceptions can include credential-bearing DSNs.
        # Do not emit exception details to health logs.
        return False


def main() -> int:
    if worker_storage_ready(os.getenv("SMARTPLOY_DATABASE_URL", "").strip()):
        return 0
    print("SmartPloy worker health: scheduling database unavailable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

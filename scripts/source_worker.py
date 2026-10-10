#!/usr/bin/env python3
"""Run Smartploy's persistent continuous source/application worker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sys
from threading import Event

from smartploy.storage import PostgresJobRepository
from smartploy.worker_runtime import build_worker_task_specs
from smartploy.worker_schedule import ContinuousWorker, PostgresWorkerTaskRepository


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if value <= 0:
        raise SystemExit(f"{name} must be positive")
    if maximum is not None:
        value = min(value, maximum)
    return value


def _owner() -> str:
    configured = os.getenv("SMARTPLOY_WORKER_OWNER", "").strip()
    if configured:
        if len(configured) > 200 or any(ord(char) < 32 for char in configured):
            raise SystemExit("SMARTPLOY_WORKER_OWNER must be a short printable value")
        return configured
    return f"{socket.gethostname()}:{os.getpid()}"


def _schema_ready(repository: PostgresWorkerTaskRepository) -> bool:
    try:
        repository.list()
    except Exception:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one scheduler claim/execute cycle and exit",
    )
    args = parser.parse_args()

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required")

    jobs = PostgresJobRepository(dsn)
    if not jobs.storage_status().get("ready"):
        raise SystemExit("Smartploy PostgreSQL schema is not ready; run scripts/migrate.py")

    scheduler = PostgresWorkerTaskRepository(dsn)
    if not _schema_ready(scheduler):
        raise SystemExit("Smartploy worker schema is not ready; run scripts/migrate.py")

    specs = build_worker_task_specs(dsn)
    worker = ContinuousWorker(
        scheduler,
        specs,
        owner=_owner(),
        lease_seconds=_positive_int("SMARTPLOY_WORKER_LEASE_SECONDS", 300),
        max_backoff_seconds=_positive_int("SMARTPLOY_WORKER_MAX_BACKOFF_SECONDS", 3600),
        claim_limit=_positive_int("SMARTPLOY_WORKER_CLAIM_LIMIT", 8, maximum=100),
    )
    sleep_seconds = _positive_int("SMARTPLOY_WORKER_LOOP_SECONDS", 15)

    stop = Event()

    def request_stop(signum, frame):
        del signum, frame
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    while not stop.is_set():
        cycle = worker.run_once()
        print(json.dumps(cycle.to_dict(), sort_keys=True), flush=True)
        if args.once:
            return 1 if cycle.failed else 0
        stop.wait(sleep_seconds)

    print(
        json.dumps(
            {
                "status": "stopped",
                "worker": Path(sys.argv[0]).name,
                "external_actions_authorized": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""SP36: prove configured Agent Zero task ran on the real shared worker.

Read-only, candidate-independent acceptance for container-local use. No CV,
email, tenant/profile IDs, DSN, task failure text or employer actions appear in
output. This is NOT proof of a particular candidate's reminder delivery.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from typing import Any

from .worker_schedule import PostgresWorkerTaskRepository, WorkerTask


TASK_ID = "application:agent-zero-reminders"
SCHEMA = "smartploy.agent_zero.runtime.v1"


class AgentZeroAcceptanceError(ValueError):
    """Safe, non-sensitive failure code; never include database diagnostics."""


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise AgentZeroAcceptanceError("INVALID_ACCEPTANCE_TIME")
    return moment.astimezone(timezone.utc)


def evaluate(
    raw_flag: str,
    task: WorkerTask | None,
    *,
    now: datetime | None = None,
    require_run: bool = False,
    not_before: datetime | None = None,
) -> dict[str, Any]:
    """Classify the ACTUAL worker environment and persisted task row.

    The caller must execute this in the worker container, not in the API
    container or on an operator laptop. No private data is read.
    """
    flag = str(raw_flag or "").strip().lower()
    if flag not in {"true", "false"}:
        raise AgentZeroAcceptanceError("AGENT_ZERO_FLAG_INVALID")
    moment = _utc(now or datetime.now(timezone.utc))
    after = _utc(not_before) if not_before is not None else None

    if flag == "false":
        if require_run:
            raise AgentZeroAcceptanceError("AGENT_ZERO_OPERATOR_OPT_IN_REQUIRED")
        if task is not None and task.enabled:
            raise AgentZeroAcceptanceError("DISABLED_AGENT_TASK_STILL_ENABLED")
        return {
            "schema": SCHEMA, "status": "disabled_by_operator",
            "task_registered": task is not None,
            "task_enabled": False, "completed_run_verified": False,
            "candidate_reminder_delivered_verified": False,
            "employer_contacts_authorized": False,
            "external_actions_authorized": False,
        }

    if task is None:
        raise AgentZeroAcceptanceError("AGENT_ZERO_TASK_NOT_REGISTERED")
    if not task.enabled or task.task_id != TASK_ID or (
        task.task_kind != "application_agent"
    ):
        raise AgentZeroAcceptanceError("AGENT_ZERO_TASK_NOT_ENABLED")
    policy = task.metadata or {}
    if (
        policy.get("channel") != "in_app_only"
        or policy.get("external_actions_authorized") is not False
        or policy.get("employer_submission_authorized") is not False
    ):
        raise AgentZeroAcceptanceError("AGENT_ZERO_EXTERNAL_POLICY_MISMATCH")
    if not 1 <= task.cadence_seconds <= 86400:
        raise AgentZeroAcceptanceError("AGENT_ZERO_CADENCE_INVALID")
    if task.last_status != "healthy" or task.consecutive_failures:
        if require_run:
            raise AgentZeroAcceptanceError("AGENT_ZERO_RUN_NOT_HEALTHY")
        last_good = False
    else:
        last_good = task.last_completed_at is not None

    if last_good and task.last_completed_at is not None:
        completed = _utc(task.last_completed_at)
        if completed > moment + timedelta(seconds=10):
            raise AgentZeroAcceptanceError("AGENT_ZERO_RUN_CLOCK_INVALID")
        # A stale previous run is not evidence of ongoing scheduled work.
        age = (moment - completed).total_seconds()
        if age > max(120, task.cadence_seconds * 3):
            last_good = False
        if after is not None and completed + timedelta(seconds=1) < after:
            last_good = False

    if require_run and not last_good:
        raise AgentZeroAcceptanceError("AGENT_ZERO_FRESH_RUN_MISSING")

    return {
        "schema": SCHEMA,
        "status": "healthy_scheduled_run" if last_good else "registered_waiting_for_run",
        "task_registered": True, "task_enabled": True,
        "completed_run_verified": last_good,
        "candidate_reminder_delivered_verified": False,
        "employer_contacts_authorized": False,
        "external_actions_authorized": False,
    }


def _parse_after(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _utc(parsed)
    except (ValueError, TypeError) as exc:
        raise AgentZeroAcceptanceError("INVALID_NOT_BEFORE_TIME") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-run", action="store_true")
    parser.add_argument("--not-before", default="")
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if not 0 <= args.wait_seconds <= 120:
            raise AgentZeroAcceptanceError("INVALID_WAIT_LIMIT")
        after = _parse_after(args.not_before)
        dsn = os.environ.get("SMARTPLOY_DATABASE_URL", "").strip()
        if not dsn:
            raise AgentZeroAcceptanceError("WORKER_DATABASE_NOT_CONFIGURED")
        # DB errors must NEVER leak connection strings or private SQL
        # diagnostics into CI logs, host terminals or release receipts.
        repo = PostgresWorkerTaskRepository(dsn)
        end = time.monotonic() + args.wait_seconds
        last_error = "AGENT_ZERO_TASK_UNAVAILABLE"
        while True:
            try:
                task = repo.get(TASK_ID)
                result = evaluate(
                    os.getenv("SMARTPLOY_WORKER_AGENT_ZERO_ENABLED", "false"),
                    task, require_run=args.require_run,
                    not_before=after,
                )
                print(json.dumps(result, sort_keys=True))
                return 0
            except AgentZeroAcceptanceError as exc:
                last_error = str(exc)
            except Exception:
                last_error = "AGENT_ZERO_TASK_REGISTRY_UNAVAILABLE"
            if time.monotonic() >= end:
                break
            time.sleep(min(2.0, max(0.0, end - time.monotonic())))
        print("SmartPloy Agent Zero acceptance: HOLD (" + last_error + ")", file=sys.stderr)
        return 3
    except AgentZeroAcceptanceError as exc:
        print("SmartPloy Agent Zero acceptance: HOLD (" + str(exc) + ")", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

"""SP59: independently prove the opted-in AutoDraft worker has actually run.

This is a read-only, account-independent worker receipt. It never reads CVs,
user identities, job listings, or receipts and never contacts any employer.
Reuse the existing Agent Zero accepted-timestamp helpers and original
Postgres worker task ledger; do not create another scheduler or draft engine.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from typing import Any

from .agent_zero_runtime_acceptance import (
    AgentZeroAcceptanceError, _parse_after, _utc,
)
from .worker_schedule import PostgresWorkerTaskRepository, WorkerTask


TASK_ID = "application:auto-draft-shortlist"
SCHEMA = "smartploy.auto_draft.runtime.v1"


class AutoDraftAcceptanceError(ValueError):
    """Safe fixed-category error only; no database contents or owner details."""


def _safe_utc(value: datetime) -> datetime:
    try:
        return _utc(value)
    except AgentZeroAcceptanceError as exc:
        raise AutoDraftAcceptanceError("AUTO_DRAFT_TIMESTAMP_INVALID") from exc


def evaluate(
    raw_flag: str,
    task: WorkerTask | None,
    *,
    now: datetime | None = None,
    require_run: bool = False,
    not_before: datetime | None = None,
) -> dict[str, Any]:
    """Attest the task in THIS worker container, not generic /healthz."""
    if raw_flag not in {"true", "false"}:
        raise AutoDraftAcceptanceError("AUTO_DRAFT_FLAG_INVALID")
    moment = _safe_utc(now or datetime.now(timezone.utc))
    after = _safe_utc(not_before) if not_before is not None else None

    if raw_flag == "false":
        if require_run:
            raise AutoDraftAcceptanceError("AUTO_DRAFT_OPERATOR_OPT_IN_REQUIRED")
        if task is not None and task.enabled:
            raise AutoDraftAcceptanceError("DISABLED_AUTO_DRAFT_TASK_STILL_ENABLED")
        return {
            "schema": SCHEMA, "status": "disabled_by_operator",
            "task_registered": task is not None, "task_enabled": False,
            "completed_run_verified": False,
            "candidate_drafts_created_verified": False,
            "employer_contacts_authorized": False,
            "external_actions_authorized": False,
        }

    if task is None:
        raise AutoDraftAcceptanceError("AUTO_DRAFT_TASK_NOT_REGISTERED")
    if (
        not task.enabled or task.task_id != TASK_ID
        or task.task_kind != "application_draft"
    ):
        raise AutoDraftAcceptanceError("AUTO_DRAFT_TASK_NOT_ENABLED")
    policy = task.metadata or {}
    if (
        policy.get("private_opt_in_required") is not True
        or policy.get("processing") != "local_only"
        or policy.get("external_actions_authorized") is not False
    ):
        raise AutoDraftAcceptanceError("AUTO_DRAFT_PRIVATE_POLICY_MISMATCH")
    if not 1 <= task.cadence_seconds <= 86400:
        raise AutoDraftAcceptanceError("AUTO_DRAFT_CADENCE_INVALID")

    healthy = (
        task.last_status == "healthy"
        and task.consecutive_failures == 0
        and task.last_completed_at is not None
    )
    if require_run and not healthy:
        raise AutoDraftAcceptanceError("AUTO_DRAFT_RUN_NOT_HEALTHY")

    if healthy and task.last_completed_at is not None:
        completed = _safe_utc(task.last_completed_at)
        if completed > moment + timedelta(seconds=10):
            raise AutoDraftAcceptanceError("AUTO_DRAFT_RUN_CLOCK_INVALID")
        if (moment - completed).total_seconds() > max(120, task.cadence_seconds * 3):
            healthy = False
        if after is not None and completed + timedelta(seconds=1) < after:
            healthy = False

    if require_run and not healthy:
        raise AutoDraftAcceptanceError("AUTO_DRAFT_FRESH_RUN_MISSING")

    return {
        "schema": SCHEMA,
        "status": "healthy_scheduled_run" if healthy else "registered_waiting_for_run",
        "task_registered": True, "task_enabled": True,
        "completed_run_verified": bool(healthy),
        # A completed background cycle may have zero opted-in applicants or
        # zero eligible jobs. A task receipt is NEVER a candidate-draft receipt.
        "candidate_drafts_created_verified": False,
        "employer_contacts_authorized": False,
        "external_actions_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-run", action="store_true")
    parser.add_argument("--not-before", default="")
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if not 0 <= args.wait_seconds <= 120:
            raise AutoDraftAcceptanceError("INVALID_WAIT_LIMIT")
        try:
            after = _parse_after(args.not_before)
        except AgentZeroAcceptanceError as exc:
            raise AutoDraftAcceptanceError("INVALID_NOT_BEFORE_TIME") from exc
        dsn = os.environ.get("SMARTPLOY_DATABASE_URL", "").strip()
        if not dsn:
            raise AutoDraftAcceptanceError("WORKER_DATABASE_NOT_CONFIGURED")
        repo = PostgresWorkerTaskRepository(dsn)
        end = time.monotonic() + args.wait_seconds
        last_error = "AUTO_DRAFT_TASK_UNAVAILABLE"
        while True:
            try:
                task = repo.get(TASK_ID)
                result = evaluate(
                    os.environ.get("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED", "false"),
                    task, require_run=args.require_run, not_before=after,
                )
                print(json.dumps(result, sort_keys=True))
                return 0
            except AutoDraftAcceptanceError as exc:
                last_error = str(exc)
            except Exception:
                last_error = "AUTO_DRAFT_TASK_REGISTRY_UNAVAILABLE"
            if time.monotonic() >= end:
                break
            time.sleep(min(2.0, max(0.0, end - time.monotonic())))
        print("SmartPloy AutoDraft acceptance: HOLD (" + last_error + ")", file=sys.stderr)
        return 3
    except AutoDraftAcceptanceError as exc:
        print("SmartPloy AutoDraft acceptance: HOLD (" + str(exc) + ")", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

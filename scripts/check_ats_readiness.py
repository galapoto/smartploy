#!/usr/bin/env python3
"""Read-only ATS source readiness from the live SmartPloy worker container.

Prints only non-sensitive counts/states. No user profiles, CVs, job bodies,
credentials, database DSN or raw provider exception messages are returned.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import sys
from typing import Any, Iterable

from psycopg import connect

from smartploy.sources.public_ats import load_public_ats_sources
from smartploy.storage import PostgresJobRepository, SourceHealth
from smartploy.worker_schedule import PostgresWorkerTaskRepository, WorkerTask


def _iso(value: Any) -> str:
    if not value:
        return ""
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _count(metadata: dict[str, Any], key: str) -> int:
    value = metadata.get(key)
    if type(value) is not int:
        return 0
    return min(max(value, 0), 1_000_000_000)



def _failure_category(*messages: str) -> str:
    """Allowlist a diagnostic class; never disclose raw driver/provider errors."""
    value = " ".join(str(message or "") for message in messages).casefold()
    if not value.strip():
        return "not_reported"
    if "timeout" in value or "timed out" in value:
        return "network_timeout"
    if "http 429" in value or "rate limit" in value or "too many requests" in value:
        return "upstream_rate_limited"
    if "http 401" in value or "http 403" in value:
        return "upstream_access_denied"
    if "http 404" in value or "http 410" in value:
        return "upstream_source_missing"
    if "http 5" in value:
        return "upstream_server_error"
    if "response exceeds" in value or "configured item limit" in value or "too large" in value:
        return "source_size_limit"
    if "invalid json" in value or "jsondecode" in value or "unexpected shape" in value:
        return "unexpected_upstream_data"
    if "connection" in value or "connecterror" in value:
        return "network_connection_error"
    if "ssl" in value or "tls" in value:
        return "tls_error"
    return "other_failure"


def _utc_timestamp(value: Any) -> datetime | None:
    """Accept only timezone-aware datetimes for a security-relevant freshness check."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _poll_freshness(
    task: WorkerTask | None,
    health: SourceHealth | None,
    *,
    reference_at: datetime,
    max_age_hours: float | None,
) -> str:
    """Fail closed on stale, unknown or future-dated worker and source evidence."""
    if max_age_hours is None:
        return "not_checked"
    completed = _utc_timestamp(task.last_completed_at if task else None)
    succeeded = _utc_timestamp(health.last_success_at if health else None)
    if completed is None or succeeded is None:
        return "missing_timestamp"
    ages = (
        (reference_at - completed).total_seconds() / 3600,
        (reference_at - succeeded).total_seconds() / 3600,
    )
    if any(age < -(5 / 60) for age in ages):
        return "future_timestamp"
    return "fresh" if all(age <= max_age_hours for age in ages) else "stale"


def source_report(
    expected: Iterable[str],
    tasks: Iterable[WorkerTask],
    statuses: Iterable[SourceHealth],
    *,
    active_job_count: int,
    freshness_max_age_hours: float | None = None,
    reference_at: datetime | None = None,
) -> dict[str, Any]:
    """Compose a credential-free report from already loaded repository data."""
    now = reference_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("freshness reference time must have a UTC offset")
    now = now.astimezone(timezone.utc)
    if freshness_max_age_hours is not None and (
        not math.isfinite(freshness_max_age_hours)
        or not 0.25 <= freshness_max_age_hours <= 168
    ):
        raise ValueError("freshness_max_age_hours must be 0.25-168")
    task_index = {task.task_id: task for task in tasks}
    health_index = {status.source_id: status for status in statuses}
    summaries = []
    completed = 0
    successful = 0
    matched = 0
    fresh_count = 0

    for source_id in expected:
        task = task_index.get("source:" + source_id)
        health = health_index.get(source_id)
        details = dict(health.metadata or {}) if health else {}
        task_status = task.last_status if task else "missing"
        poll_status = health.status if health else "not_polled"

        if task is None or not task.enabled:
            state = "task_not_registered"
        elif task.last_completed_at is None:
            state = "awaiting_first_poll"
        elif task_status == "failed" or poll_status == "failed":
            state = "poll_failed"
        elif poll_status == "healthy" and task_status == "healthy":
            state = "healthy_with_matching_jobs" if health.last_item_count else "healthy_zero_matching_jobs"
        elif poll_status == "degraded" or task_status == "degraded":
            state = "degraded"
        else:
            state = "check_required"

        if task and task.last_completed_at:
            completed += 1
        if state.startswith("healthy_"):
            successful += 1
        if health and state.startswith("healthy_"):
            matched += health.last_item_count
        freshness = _poll_freshness(
            task, health, reference_at=now, max_age_hours=freshness_max_age_hours
        )
        if state.startswith("healthy_") and freshness == "fresh":
            fresh_count += 1

        summaries.append({
            "source_id": source_id,
            "readiness": state,
            "freshness": freshness,
            "task_enabled": bool(task and task.enabled),
            "task_last_status": task_status,
            "last_completed_at": _iso(task.last_completed_at) if task else "",
            "next_run_at": _iso(task.next_run_at) if task else "",
            "source_status": poll_status,
            "failure_category": _failure_category(task.last_error if task else "", health.last_error if health else "") if state == "poll_failed" else "",
            "last_attempt_at": _iso(health.last_attempt_at) if health else "",
            "last_success_at": _iso(health.last_success_at) if health else "",
            "last_finnish_matching_postings": int(health.last_item_count) if health else 0,
            "upstream_total_at_last_poll": _count(details, "total_source_postings"),
            "excluded_by_location_at_last_poll": _count(details, "location_filtered_count"),
            "excluded_non_job_postings_at_last_poll": _count(details, "prospect_filtered_count"),
            "blocked_at_last_poll": _count(details, "blocked_count"),
            "consecutive_task_failures": task.consecutive_failures if task else 0,
            "consecutive_source_failures": health.consecutive_failures if health else 0,
        })

    expected_count = len(summaries)
    return {
        "report": "smartploy-ats-readiness-v1",
        "checked_at": now.isoformat(timespec="seconds"),
        "configured_sources": expected_count,
        "freshness_max_age_hours": freshness_max_age_hours,
        "sources_fresh": fresh_count if freshness_max_age_hours is not None else None,
        "freshness_gate_ready": (
            bool(expected_count and expected_count == fresh_count and
                 expected_count == successful)
            if freshness_max_age_hours is not None else None
        ),
        "source_tasks_completed": completed,
        "sources_healthy": successful,
        "last_finnish_matching_postings_sum": matched,
        "active_jobs_all_sources": active_job_count,
        "ready": bool(expected_count and expected_count == successful),
        "job_discovery_observed": matched > 0,
        "sources": summaries,
        "private_cv_contents_included": False,
        "credentials_included": False,
        "external_actions_authorized": False,
    }


def collect_report(
    dsn: str, *, freshness_max_age_hours: float | None = None
) -> dict[str, Any]:
    configured = load_public_ats_sources()
    expected = [item.source_id for item in configured]
    tasks = PostgresWorkerTaskRepository(dsn).list()
    health = PostgresJobRepository(dsn).list_source_health()
    with connect(dsn, connect_timeout=4, options="-c default_transaction_read_only=on") as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM smartploy_jobs WHERE source_current = true")
            active_count = int(cursor.fetchone()[0])
    return source_report(
        expected, tasks, health, active_job_count=active_count,
        freshness_max_age_hours=freshness_max_age_hours,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only live public ATS status")
    parser.add_argument("--require-healthy", action="store_true",
                        help="Fail if any configured source lacks a healthy completed poll")
    parser.add_argument("--require-jobs", action="store_true",
                        help="Fail if no selected ATS feed has returned matching Finnish vacancies")
    parser.add_argument(
        "--require-fresh-hours", type=float,
        help="Opt-in: require each healthy source's last completed/successful poll to be recent (0.25-168h)",
    )
    args = parser.parse_args()
    if args.require_fresh_hours is not None and (
        not math.isfinite(args.require_fresh_hours)
        or not 0.25 <= args.require_fresh_hours <= 168
    ):
        print(json.dumps({"error": "invalid_source_freshness_threshold"}), file=sys.stderr)
        return 2
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        print(json.dumps({"error": "worker database is not configured"}), file=sys.stderr)
        return 2
    try:
        report = (
            collect_report(dsn, freshness_max_age_hours=args.require_fresh_hours)
            if args.require_fresh_hours is not None else collect_report(dsn)
        )
    except Exception as exc:
        # Driver exceptions can include DSNs; never print exception text.
        print(json.dumps({"error": "read_only_source_check_failed", "type": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    if args.require_healthy and not report["ready"]:
        return 3
    if args.require_jobs and not report["job_discovery_observed"]:
        return 4
    if args.require_fresh_hours is not None and not report["freshness_gate_ready"]:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

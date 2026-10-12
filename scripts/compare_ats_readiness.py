#!/usr/bin/env python3
"""Compare two sanitized SmartPloy ATS readiness snapshots without side effects.

This reports potential source-health regressions for an operator's review.
It never polls employers, queries a database, changes source state or
authorizes third-party data sharing or employer applications.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping


SNAPSHOT_CONTRACT = "smartploy-ats-readiness-v1"
DIFF_CONTRACT = "smartploy-ats-coverage-diff-v1"
MAX_SNAPSHOT_BYTES = 512_000
SAFE_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,149}$")
HEALTHY_STATES = frozenset({
    "healthy_with_matching_jobs", "healthy_zero_matching_jobs",
})
KNOWN_STATES = HEALTHY_STATES | frozenset({
    "task_not_registered", "awaiting_first_poll", "poll_failed",
    "degraded", "check_required",
})
MAX_CLOCK_SKEW = timedelta(minutes=5)


class ReadinessSnapshotError(ValueError):
    """Malformed, oversized, out-of-order, or untrusted readiness evidence."""


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0 or value > 1_000_000_000:
        raise ReadinessSnapshotError(f"{field} must be a bounded nonnegative integer")
    return value


def _timestamp(value: Any, field: str, *, required: bool = True) -> datetime | None:
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str):
        raise ReadinessSnapshotError(f"{field} must be an ISO date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadinessSnapshotError(f"{field} has an invalid date-time") from exc
    if parsed.tzinfo is None:
        raise ReadinessSnapshotError(f"{field} needs a timezone")
    return parsed.astimezone(timezone.utc)


def read_snapshot(path: Path) -> dict[str, Any]:
    """Read a bounded JSON file; never reprint its untrusted input on errors."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise ReadinessSnapshotError("snapshot exceeds size limit")
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessSnapshotError("snapshot cannot be read as UTF-8 JSON") from exc
    return validate_snapshot(data)


def validate_snapshot(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("report") != SNAPSHOT_CONTRACT:
        raise ReadinessSnapshotError("unsupported ATS readiness snapshot")
    checked_at = _timestamp(data.get("checked_at"), "checked_at")
    assert checked_at is not None
    sources = data.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 500:
        raise ReadinessSnapshotError("snapshot requires 1-500 sources")
    declared = _nonnegative_int(data.get("configured_sources"), "configured_sources")
    if declared != len(sources):
        raise ReadinessSnapshotError("configured_sources does not match source list")

    seen: set[str] = set()
    healthy = 0
    matched = 0
    for item in sources:
        if not isinstance(item, dict):
            raise ReadinessSnapshotError("source entry must be an object")
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not SAFE_SOURCE_ID.fullmatch(source_id):
            raise ReadinessSnapshotError("source identity is invalid")
        if source_id in seen:
            raise ReadinessSnapshotError("duplicate source identity")
        seen.add(source_id)
        state = item.get("readiness")
        if state not in KNOWN_STATES:
            raise ReadinessSnapshotError("source readiness state is invalid")
        healthy += int(state in HEALTHY_STATES)
        count = _nonnegative_int(
            item.get("last_finnish_matching_postings"),
            "last_finnish_matching_postings",
        )
        if state in HEALTHY_STATES:
            matched += count
        for key in ("last_success_at", "last_completed_at"):
            timestamp = _timestamp(item.get(key), key, required=False)
            if timestamp is not None and timestamp > checked_at + MAX_CLOCK_SKEW:
                raise ReadinessSnapshotError("source timestamp lies in the future")

    total_healthy = _nonnegative_int(data.get("sources_healthy"), "sources_healthy")
    if total_healthy != healthy:
        raise ReadinessSnapshotError("sources_healthy does not match source states")
    observed_sum = _nonnegative_int(
        data.get("last_finnish_matching_postings_sum"),
        "last_finnish_matching_postings_sum",
    )
    if observed_sum != matched:
        raise ReadinessSnapshotError("posting sum does not match healthy sources")
    expected_ready = bool(healthy == declared)
    if type(data.get("ready")) is not bool or data["ready"] != expected_ready:
        raise ReadinessSnapshotError("source readiness aggregate is inconsistent")
    if type(data.get("job_discovery_observed")) is not bool or (
        data["job_discovery_observed"] != (matched > 0)
    ):
        raise ReadinessSnapshotError("job discovery aggregate is inconsistent")
    _nonnegative_int(data.get("active_jobs_all_sources"), "active_jobs_all_sources")
    if "freshness_gate_ready" in data and data["freshness_gate_ready"] is not None:
        if type(data["freshness_gate_ready"]) is not bool:
            raise ReadinessSnapshotError("source freshness state is invalid")
    return data


def _event(
    events: list[dict[str, Any]], kind: str, source_id: str | None = None,
    *, before: int | None = None, after: int | None = None,
) -> None:
    row: dict[str, Any] = {"kind": kind}
    if source_id is not None:
        row["source_id"] = source_id
    if before is not None:
        row["before_count"] = before
    if after is not None:
        row["after_count"] = after
    events.append(row)


def compare_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    max_drop_fraction: float = 0.50,
    require_new_poll: bool = False,
) -> dict[str, Any]:
    """Flag unsafe source changes without modifying either input or live jobs."""
    baseline = validate_snapshot(dict(before))
    candidate = validate_snapshot(dict(after))
    if (not isinstance(max_drop_fraction, (int, float))
            or isinstance(max_drop_fraction, bool)
            or not math.isfinite(max_drop_fraction)
            or not 0 < max_drop_fraction <= 1):
        raise ReadinessSnapshotError("max_drop_fraction must be finite and within (0,1]")
    early = _timestamp(baseline["checked_at"], "baseline_checked_at")
    late = _timestamp(candidate["checked_at"], "candidate_checked_at")
    assert early is not None and late is not None
    if late <= early:
        raise ReadinessSnapshotError("candidate snapshot must be newer than baseline")

    old_sources = {row["source_id"]: row for row in baseline["sources"]}
    new_sources = {row["source_id"]: row for row in candidate["sources"]}
    events: list[dict[str, Any]] = []
    for source_id in sorted(old_sources.keys() - new_sources.keys()):
        _event(events, "removed_source", source_id)
    for source_id in sorted(new_sources.keys() - old_sources.keys()):
        _event(events, "new_source_requires_terms_review", source_id)
    for source_id in sorted(old_sources.keys() & new_sources.keys()):
        old = old_sources[source_id]
        new = new_sources[source_id]
        old_healthy = old["readiness"] in HEALTHY_STATES
        new_healthy = new["readiness"] in HEALTHY_STATES
        if old_healthy and not new_healthy:
            _event(events, "source_health_regressed", source_id)
        old_time = _timestamp(old.get("last_success_at"), "last_success_at", required=False)
        new_time = _timestamp(new.get("last_success_at"), "last_success_at", required=False)
        if old_time and new_time and new_time < old_time:
            _event(events, "source_last_success_regressed", source_id)
        elif old_healthy and new_time is None:
            _event(events, "source_success_evidence_missing", source_id)
        elif require_new_poll and (old_time is None or new_time is None or new_time <= old_time):
            _event(events, "new_source_poll_not_confirmed", source_id)
        old_count = old["last_finnish_matching_postings"]
        new_count = new["last_finnish_matching_postings"]
        if old_count > 0 and new_count < old_count and (
            (old_count - new_count) / old_count >= max_drop_fraction
        ):
            _event(
                events, "source_posting_count_drop", source_id,
                before=old_count, after=new_count,
            )

    old_total = baseline["active_jobs_all_sources"]
    new_total = candidate["active_jobs_all_sources"]
    if old_total > 0 and new_total < old_total and (
        (old_total - new_total) / old_total >= max_drop_fraction
    ):
        _event(events, "active_unique_jobs_drop", before=old_total, after=new_total)
    if baseline["ready"] and not candidate["ready"]:
        _event(events, "aggregate_source_readiness_regressed")
    if candidate.get("freshness_gate_ready") is False:
        _event(events, "explicit_freshness_gate_failed")

    return {
        "contract": DIFF_CONTRACT,
        "input_kind": "sanitized_ats_readiness_snapshots",
        "baseline_checked_at": early.isoformat(timespec="seconds"),
        "candidate_checked_at": late.isoformat(timespec="seconds"),
        "baseline_source_count": len(old_sources),
        "candidate_source_count": len(new_sources),
        "baseline_active_jobs": old_total,
        "candidate_active_jobs": new_total,
        "drop_fraction_review_threshold": float(max_drop_fraction),
        "new_poll_required": bool(require_new_poll),
        "status": "review_required" if events else "pass",
        "events": events,
        "database_writes": False,
        "network_calls": False,
        "external_actions_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two private, sanitized SmartPloy ATS readiness snapshots"
    )
    parser.add_argument("baseline", type=Path, help="Earlier read-only readiness JSON")
    parser.add_argument("candidate", type=Path, help="Newer read-only readiness JSON")
    parser.add_argument(
        "--max-job-drop-percent", type=float, default=50.0,
        help="Review a per-source or total count drop at or above this percentage",
    )
    parser.add_argument(
        "--require-new-poll", action="store_true",
        help="Also flag sources without newer last-success poll evidence",
    )
    parser.add_argument("--json", action="store_true", help="Print bounded machine JSON")
    args = parser.parse_args(argv)
    try:
        if (not math.isfinite(args.max_job_drop_percent)
                or not 0 < args.max_job_drop_percent <= 100):
            raise ReadinessSnapshotError("invalid job-count drop threshold")
        report = compare_snapshots(
            read_snapshot(args.baseline), read_snapshot(args.candidate),
            max_drop_fraction=args.max_job_drop_percent / 100,
            require_new_poll=args.require_new_poll,
        )
    except (ReadinessSnapshotError, TypeError, ValueError, KeyError):
        # Malicious or private snapshot content must never be echoed to logs.
        print("ATS_COVERAGE_COMPARE: invalid_or_untrusted_snapshot", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            f"ATS_COVERAGE_COMPARE: {report['status']} "
            f"sources={report['baseline_source_count']}->{report['candidate_source_count']} "
            f"active_jobs={report['baseline_active_jobs']}->{report['candidate_active_jobs']}"
        )
        for event in report["events"]:
            print(
                "  " + event["kind"]
                + (":" + event["source_id"] if "source_id" in event else "")
            )
    return 0 if report["status"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())

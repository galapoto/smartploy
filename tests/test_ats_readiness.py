"""ATS pilot readiness must reflect persisted worker polls and never reveal secrets."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sys

from scripts import check_ats_readiness
from smartploy.storage import SourceHealth
from smartploy.worker_schedule import WorkerTask


STAMP = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)
SOURCE = "lever-global-uprightproject"


def task(source_id=SOURCE, *, status="healthy", done=True, enabled=True):
    return WorkerTask(
        task_id="source:" + source_id,
        task_kind="source",
        enabled=enabled,
        cadence_seconds=600,
        next_run_at=STAMP,
        last_completed_at=STAMP if done else None,
        last_status=status,
    )


def health(source_id=SOURCE, *, state="healthy", count=2, metadata=None):
    return SourceHealth(
        source_id=source_id,
        status=state,
        last_attempt_at=STAMP.isoformat(),
        last_success_at=STAMP.isoformat(),
        last_item_count=count,
        metadata=metadata or {
            "total_source_postings": 13,
            "location_filtered_count": 11,
            "blocked_count": 0,
            "secret": "do-not-print",
        },
    )


def test_healthy_finnish_pilot_source_report():
    report = check_ats_readiness.source_report([SOURCE], [task()], [health()], active_job_count=7)
    assert report["ready"] is True
    assert report["job_discovery_observed"] is True
    assert report["last_finnish_matching_postings_sum"] == 2
    assert report["active_jobs_all_sources"] == 7
    source = report["sources"][0]
    assert source["readiness"] == "healthy_with_matching_jobs"
    assert source["excluded_by_location_at_last_poll"] == 11
    assert source["upstream_total_at_last_poll"] == 13
    assert "do-not-print" not in json.dumps(report)
    assert "raw_text" not in json.dumps(report)
    assert report["external_actions_authorized"] is False


def test_healthy_zero_items_is_not_a_failure_or_a_job_discovery():
    report = check_ats_readiness.source_report(
        [SOURCE], [task()], [health(count=0)], active_job_count=1,
    )
    assert report["ready"] is True
    assert report["job_discovery_observed"] is False
    assert report["sources"][0]["readiness"] == "healthy_zero_matching_jobs"


def test_pending_task_is_not_classified_as_success():
    report = check_ats_readiness.source_report([SOURCE], [task(done=False)], [], active_job_count=0)
    assert report["ready"] is False
    assert report["sources"][0]["readiness"] == "awaiting_first_poll"
    missing = check_ats_readiness.source_report([SOURCE], [], [], active_job_count=0)
    assert missing["sources"][0]["readiness"] == "task_not_registered"


def test_failed_and_degraded_polls_are_not_healthy():
    failure = check_ats_readiness.source_report(
        [SOURCE], [task(status="failed")], [health(state="failed", count=0)], active_job_count=0
    )
    degraded = check_ats_readiness.source_report(
        [SOURCE], [task(status="degraded")], [health(state="degraded", count=1)], active_job_count=1
    )
    assert failure["sources"][0]["readiness"] == "poll_failed"
    assert degraded["sources"][0]["readiness"] == "degraded"
    assert failure["ready"] is False
    assert degraded["ready"] is False


def test_missing_fifth_source_prevents_all_healthy():
    report = check_ats_readiness.source_report(
        [SOURCE, "lever-global-netlight"], [task()], [health()], active_job_count=1
    )
    assert report["configured_sources"] == 2
    assert report["sources_healthy"] == 1
    assert report["ready"] is False
    assert report["sources"][1]["readiness"] == "task_not_registered"


def test_cli_verification_flags_and_error_redaction(monkeypatch, capsys):
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", "postgresql://user:very-private-password@db/smartploy")
    monkeypatch.setattr(check_ats_readiness, "collect_report", lambda dsn: check_ats_readiness.source_report(
        [SOURCE], [task()], [health(count=0)], active_job_count=0
    ))
    monkeypatch.setattr(sys, "argv", ["check_ats_readiness.py", "--require-healthy"])
    assert check_ats_readiness.main() == 0
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["check_ats_readiness.py", "--require-jobs"])
    assert check_ats_readiness.main() == 4
    capsys.readouterr()

    def fail(dsn):
        raise RuntimeError("postgresql://user:very-private-password@db/smartploy")
    monkeypatch.setattr(check_ats_readiness, "collect_report", fail)
    monkeypatch.setattr(sys, "argv", ["check_ats_readiness.py"])
    assert check_ats_readiness.main() == 2
    result = capsys.readouterr()
    assert "very-private-password" not in result.err + result.out
    assert "RuntimeError" in result.err

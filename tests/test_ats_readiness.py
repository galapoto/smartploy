"""ATS pilot readiness must reflect persisted worker polls and never reveal secrets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
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


def test_only_safe_categories_are_exposed_for_real_worker_failures():
    error = "PublicATSError: lever request failed: ReadTimeout postgresql://user:secret-value@db"
    failed_task = replace(task(status="failed"), last_error=error)
    failed_source = replace(health(state="failed", count=0), last_error=error)
    report = check_ats_readiness.source_report(
        [SOURCE], [failed_task], [failed_source], active_job_count=0
    )
    assert report["sources"][0]["failure_category"] == "network_timeout"
    assert "secret-value" not in json.dumps(report)
    assert "ReadTimeout" not in json.dumps(report)


def test_known_poll_errors_are_categorized_without_echoing_input():
    checks = [
        ("PublicATSError: lever returned HTTP 429", "upstream_rate_limited"),
        ("PublicATSError: lever returned HTTP 403", "upstream_access_denied"),
        ("PublicATSError: lever returned HTTP 404", "upstream_source_missing"),
        ("PublicATSError: lever returned HTTP 500", "upstream_server_error"),
        ("PublicATSError: Lever result exceeds configured item limit", "source_size_limit"),
        ("PublicATSError: invalid JSON", "unexpected_upstream_data"),
        ("PublicATSError: ConnectionError", "network_connection_error"),
        ("PublicATSError: SSL verification failed", "tls_error"),
        ("Unexpected opaque sensitive content", "other_failure"),
        ("", "not_reported"),
    ]
    for message, expected_category in checks:
        assert check_ats_readiness._failure_category(message) == expected_category


def test_freshness_is_opt_in_and_requires_both_success_and_worker_completion():
    old_report = check_ats_readiness.source_report(
        [SOURCE], [task()], [health()], active_job_count=7,
        reference_at=STAMP + timedelta(hours=30),
    )
    assert old_report["ready"] is True
    assert old_report["freshness_gate_ready"] is None
    assert old_report["sources"][0]["freshness"] == "not_checked"

    fresh = check_ats_readiness.source_report(
        [SOURCE], [task()], [health()], active_job_count=7,
        reference_at=STAMP + timedelta(hours=1),
        freshness_max_age_hours=2,
    )
    assert fresh["ready"] is True
    assert fresh["sources_fresh"] == 1
    assert fresh["freshness_gate_ready"] is True
    assert fresh["sources"][0]["freshness"] == "fresh"

    stale = check_ats_readiness.source_report(
        [SOURCE], [task()], [health()], active_job_count=7,
        reference_at=STAMP + timedelta(hours=25),
        freshness_max_age_hours=24,
    )
    assert stale["ready"] is True  # Legacy readiness is deliberately unchanged.
    assert stale["freshness_gate_ready"] is False
    assert stale["sources_fresh"] == 0
    assert stale["sources"][0]["freshness"] == "stale"


def test_freshness_requires_valid_both_timestamps_and_rejects_future_evidence():
    expired = check_ats_readiness.source_report(
        [SOURCE], [task()], [replace(health(), last_success_at="unknown")],
        active_job_count=1, freshness_max_age_hours=2, reference_at=STAMP,
    )
    assert expired["sources"][0]["freshness"] == "missing_timestamp"
    assert expired["freshness_gate_ready"] is False

    future = check_ats_readiness.source_report(
        [SOURCE], [task()],
        [replace(health(), last_success_at=(STAMP + timedelta(minutes=6)).isoformat())],
        active_job_count=1, freshness_max_age_hours=2, reference_at=STAMP,
    )
    assert future["sources"][0]["freshness"] == "future_timestamp"
    assert future["freshness_gate_ready"] is False

    unpublished = check_ats_readiness.source_report(
        [SOURCE], [task(done=False)], [health()],
        active_job_count=1, freshness_max_age_hours=2, reference_at=STAMP,
    )
    assert unpublished["sources"][0]["freshness"] == "missing_timestamp"
    assert unpublished["freshness_gate_ready"] is False


def test_freshness_cli_fails_on_stale_sources_without_exposing_credentials(monkeypatch, capsys):
    monkeypatch.setenv(
        "SMARTPLOY_DATABASE_URL",
        "postgresql://user:never-leak-this-password@db/smartploy",
    )
    def fixture_report(dsn, *, freshness_max_age_hours=None):
        return check_ats_readiness.source_report(
            [SOURCE], [task()], [health()], active_job_count=7,
            freshness_max_age_hours=freshness_max_age_hours,
            reference_at=STAMP + timedelta(hours=25),
        )

    monkeypatch.setattr(check_ats_readiness, "collect_report", fixture_report)
    monkeypatch.setattr(sys, "argv", [
        "check_ats_readiness.py", "--require-healthy",
        "--require-jobs", "--require-fresh-hours", "24",
    ])
    assert check_ats_readiness.main() == 5
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ready"] is True
    assert payload["freshness_gate_ready"] is False
    assert "never-leak-this-password" not in captured.out + captured.err

    monkeypatch.setattr(sys, "argv", [
        "check_ats_readiness.py", "--require-fresh-hours", "48",
    ])
    assert check_ats_readiness.main() == 0
    capsys.readouterr()

    for invalid in ("0", "-1", "169", "nan", "inf"):
        monkeypatch.setattr(sys, "argv", [
            "check_ats_readiness.py", "--require-fresh-hours", invalid,
        ])
        assert check_ats_readiness.main() == 2
        capsys.readouterr()

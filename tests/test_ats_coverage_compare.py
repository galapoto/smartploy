"""Offline ATS coverage checks for pre/post release comparison."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.compare_ats_readiness import (
    DIFF_CONTRACT,
    ReadinessSnapshotError,
    compare_snapshots,
    read_snapshot,
    validate_snapshot,
)


START = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def source(
    source_id="lever-global-employer",
    *,
    state="healthy_with_matching_jobs",
    count=30,
    time=START,
):
    return {
        "source_id": source_id,
        "readiness": state,
        "last_completed_at": time.isoformat() if time else "",
        "last_success_at": time.isoformat() if time else "",
        "last_finnish_matching_postings": count,
        # Extra private details must not leak into comparison output.
        "sensitive_untrusted_metadata": "private-candidate-CV-never-print",
    }


def snapshot(when, sources=None, *, active=30, freshness=None):
    data = list(sources if sources is not None else [source()])
    good = [row for row in data if row["readiness"].startswith("healthy_")]
    matched = sum(row["last_finnish_matching_postings"] for row in good)
    report = {
        "report": "smartploy-ats-readiness-v1",
        "checked_at": when.isoformat(),
        "configured_sources": len(data),
        "sources_healthy": len(good),
        "last_finnish_matching_postings_sum": matched,
        "active_jobs_all_sources": active,
        "ready": bool(len(good) == len(data)),
        "job_discovery_observed": matched > 0,
        "sources": data,
    }
    if freshness is not None:
        report["freshness_gate_ready"] = freshness
    return report


def test_stable_sources_pass_without_exposing_job_or_profile_content():
    before = snapshot(START + timedelta(minutes=10))
    after = snapshot(START + timedelta(minutes=20))
    result = compare_snapshots(before, after)
    assert result["contract"] == DIFF_CONTRACT
    assert result["status"] == "pass"
    assert result["events"] == []
    assert result["external_actions_authorized"] is False
    assert result["database_writes"] is False
    assert result["network_calls"] is False
    text = json.dumps(result)
    assert "private-candidate-CV-never-print" not in text
    assert "last_finnish_matching_postings" not in text


def test_new_greenhouse_board_requires_independent_source_terms_review():
    before = snapshot(START + timedelta(minutes=10))
    other = source("greenhouse-reviewed-example", count=6)
    after = snapshot(
        START + timedelta(minutes=20), [source(), other], active=36
    )
    result = compare_snapshots(before, after)
    assert result["status"] == "review_required"
    assert result["events"] == [
        {"kind": "new_source_requires_terms_review",
         "source_id": "greenhouse-reviewed-example"}
    ]


def test_removed_or_degraded_sources_are_flagged_even_if_aggregate_jobs_increase():
    before = snapshot(
        START + timedelta(minutes=10),
        [source("lever-global-a"), source("lever-global-b", count=5)],
        active=35,
    )
    after = snapshot(
        START + timedelta(minutes=20),
        [source("lever-global-a", state="poll_failed", count=0)],
        active=42,
    )
    result = compare_snapshots(before, after)
    assert {"removed_source", "source_health_regressed",
            "aggregate_source_readiness_regressed"} <= {
        event["kind"] for event in result["events"]
    }
    assert result["status"] == "review_required"


def test_large_selected_job_or_total_job_losses_require_review():
    before = snapshot(START + timedelta(minutes=10))
    after = snapshot(
        START + timedelta(minutes=20),
        [source(count=14, time=START + timedelta(minutes=15))],
        active=10,
    )
    events = compare_snapshots(before, after)["events"]
    assert any(row == {
        "kind": "source_posting_count_drop",
        "source_id": "lever-global-employer",
        "before_count": 30,
        "after_count": 14,
    } for row in events)
    assert any(row == {
        "kind": "active_unique_jobs_drop",
        "before_count": 30,
        "after_count": 10,
    } for row in events)


def test_moderate_normal_vacancy_changes_are_not_falsely_an_emergency():
    before = snapshot(START + timedelta(minutes=10))
    after = snapshot(
        START + timedelta(minutes=20),
        [source(count=24, time=START + timedelta(minutes=15))],
        active=24,
    )
    report = compare_snapshots(before, after, max_drop_fraction=0.5)
    assert report["status"] == "pass"
    assert report["events"] == []


def test_missing_regressed_and_unchanged_poll_evidence():
    before = snapshot(START + timedelta(minutes=10))
    later = START + timedelta(minutes=30)
    same = snapshot(later)
    assert compare_snapshots(before, same)["status"] == "pass"
    strict = compare_snapshots(before, same, require_new_poll=True)
    assert "new_source_poll_not_confirmed" in {
        event["kind"] for event in strict["events"]
    }
    older = snapshot(
        later, [source(time=START - timedelta(minutes=5))]
    )
    regressed = compare_snapshots(before, older)
    assert "source_last_success_regressed" in {
        event["kind"] for event in regressed["events"]
    }
    missing = snapshot(later, [source(time=None)])
    found = compare_snapshots(before, missing)
    assert "source_success_evidence_missing" in {
        event["kind"] for event in found["events"]
    }


def test_explicit_source_freshness_gate_is_independent_and_can_block_review():
    before = snapshot(START + timedelta(minutes=10))
    after = snapshot(START + timedelta(minutes=20), freshness=False)
    result = compare_snapshots(before, after)
    assert result["status"] == "review_required"
    assert any(row["kind"] == "explicit_freshness_gate_failed"
               for row in result["events"])


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(report="unknown"),
    lambda x: x.update(configured_sources=2),
    lambda x: x.update(sources_healthy=0),
    lambda x: x.update(last_finnish_matching_postings_sum=99),
    lambda x: x.update(ready=False),
    lambda x: x.update(job_discovery_observed=False),
    lambda x: x.update(active_jobs_all_sources=True),
    lambda x: x["sources"][0].update(readiness="apparently_healthy"),
    lambda x: x["sources"][0].update(last_finnish_matching_postings=-1),
    lambda x: x["sources"][0].update(source_id="secret@token"),
    lambda x: x["sources"].append(deepcopy(x["sources"][0])),
    lambda x: x.update(checked_at="2026-10-11 12:00:00"),
    lambda x: x["sources"][0].update(
        last_success_at=(START + timedelta(hours=2)).isoformat()
    ),
])
def test_malformed_or_fabricated_snapshot_rejected(mutation):
    data = snapshot(START + timedelta(minutes=10))
    mutation(data)
    with pytest.raises(ReadinessSnapshotError):
        validate_snapshot(data)


def test_compare_requires_newer_snapshot_and_finite_valid_threshold():
    baseline = snapshot(START + timedelta(minutes=10))
    with pytest.raises(ReadinessSnapshotError):
        compare_snapshots(baseline, deepcopy(baseline))
    later = snapshot(START + timedelta(minutes=20))
    for bad in (0, -1, 1.1, float("nan"), float("inf"), True):
        with pytest.raises(ReadinessSnapshotError):
            compare_snapshots(baseline, later, max_drop_fraction=bad)


def test_load_size_limit_and_invalid_json_rejected(tmp_path: Path):
    huge = tmp_path / "huge.json"
    huge.write_bytes(b"x" * 600_000)
    with pytest.raises(ReadinessSnapshotError, match="size limit"):
        read_snapshot(huge)
    bad = tmp_path / "bad.json"
    bad.write_text("{secret=token}", encoding="utf-8")
    with pytest.raises(ReadinessSnapshotError) as error:
        read_snapshot(bad)
    assert "secret=token" not in str(error.value)


def test_cli_success_review_and_invalid_input_have_distinct_codes_and_redaction(
    tmp_path: Path,
):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps(snapshot(START + timedelta(minutes=10))), encoding="utf-8")
    new.write_text(json.dumps(snapshot(START + timedelta(minutes=20))), encoding="utf-8")

    command = [
        sys.executable, "-m", "scripts.compare_ats_readiness",
        str(old), str(new), "--json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["status"] == "pass"

    new.write_text(json.dumps(snapshot(
        START + timedelta(minutes=20),
        [source(state="poll_failed", count=0)],
        active=0,
    )), encoding="utf-8")
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    assert result.returncode == 3
    assert json.loads(result.stdout)["status"] == "review_required"

    result = subprocess.run(
        command + ["--max-job-drop-percent", "nan"],
        check=False, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "private-candidate-CV-never-print" not in result.stdout + result.stderr
    assert "source" not in result.stderr.casefold() or "untrusted" in result.stderr

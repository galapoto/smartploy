"""Prove the offline synthetic benchmark catches regressions without PII/network."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.evaluate_search_quality import (
    CONTRACT, DEFAULT_FIXTURE, _candidate, evaluate_suite, load_fixture,
)


def test_synthetic_observations_cannot_authorize_ai_forwarding():
    case = load_fixture()["cases"][0]
    candidate = _candidate(case)
    assert candidate.job.raw["external_ai_forwarding_allowed"] is False
    assert candidate.source_current is True


def test_fixture_has_search_and_evidence_coverage_and_is_fully_labeled():
    source = load_fixture()
    report = evaluate_suite(source)
    assert report["contract"] == CONTRACT
    assert report["dataset_kind"] == "synthetic_not_empirical"
    assert report["case_count"] >= 30
    assert report["search_cases"] >= 24
    assert report["fit_cases"] >= 7
    assert report["failed"] == 0, [item for item in report["cases"] if not item["passed"]]
    assert report["recommendation_precision"] == 1.0
    assert report["recommendation_recall"] == 1.0
    assert all(item["passed"] for item in report["cases"])
    assert all(item["cases"] == item["passed"] for item in report["categories"].values())
    assert {"bilingual", "seniority", "language", "location", "work-mode",
            "career-switch", "boundaries", "general", "degree", "evidence"} <= set(report["categories"])


def test_relevance_regression_fails_closed_without_exposing_job_content():
    source = deepcopy(load_fixture())
    record = next(row for row in source["cases"] if row["id"] == "ai-not-paid")
    record["expected"]["lane"] = "recommendations"
    report = evaluate_suite(source)
    assert report["failed"] == 1
    failure = next(row for row in report["cases"] if not row["passed"])
    assert failure["id"] == "ai-not-paid"
    assert failure["failed_checks"] == ["lane"]
    assert failure["observed_lane"] == "broader"
    # The structured output never contains job descriptions, CVs, names, or URLs.
    dumped = json.dumps(report)
    assert "Paid Marketing Specialist" not in dumped
    assert "Synthetic Evaluation Employer" not in dumped
    assert "jobs.example.invalid" not in dumped


def test_requirement_regression_detects_fabricated_master_degree():
    source = deepcopy(load_fixture())
    record = next(row for row in source["cases"] if row["id"] == "bachelor-not-masters")
    record["expected"]["mandatory_gaps"] = []
    report = evaluate_suite(source)
    assert report["failed"] == 1
    failure = next(row for row in report["cases"] if not row["passed"])
    assert failure["id"] == "bachelor-not-masters"
    assert "mandatory_gaps" in failure["failed_checks"]


@pytest.mark.parametrize("invalid", [
    {"contract": "wrong", "cases": []},
    {"contract": CONTRACT, "cases": []},
    {"contract": CONTRACT, "cases": ["not-an-object"]},
])
def test_invalid_suite_contract_is_rejected(tmp_path: Path, invalid: dict):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError):
        load_fixture(path)


def test_duplicate_fixture_identifiers_are_rejected(tmp_path: Path):
    payload = load_fixture()
    payload["cases"].append(deepcopy(payload["cases"][0]))
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_fixture(path)


def test_offline_cli_executes_with_json_report_and_no_network_dependency():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_search_quality", "--json",
         "--fixture", str(DEFAULT_FIXTURE)],
        check=False, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["failed"] == 0
    assert report["search_cases"] > report["fit_cases"]
    assert report["dataset_kind"] == "synthetic_not_empirical"

"""Hard regression gates for synthetic bilingual preference and evidence matching."""
from __future__ import annotations

from copy import deepcopy

import pytest

from smartploy.matching_quality import (
    BENCHMARK_SCHEMA, DEFAULT_FIXTURE, REPORT_SCHEMA,
    evaluate_fixture, load_fixture,
)


def test_synthetic_quality_benchmark_passes_all_reviewed_cases():
    payload = load_fixture()
    report = evaluate_fixture(payload)

    assert report["schema"] == REPORT_SCHEMA
    assert report["fixture_schema"] == BENCHMARK_SCHEMA
    assert report["total_cases"] >= 22
    assert len(report["categories"]) >= 15
    assert report["failed_cases"] == 0, report["failures"]
    assert report["passed_cases"] == report["total_cases"]
    assert all(row["passed"] == row["total"] for row in report["categories"].values())

    # Synthetic regression cases never become hiring, employer or site evidence.
    assert report["synthetic_only"] is True
    assert report["real_world_match_accuracy_measured"] is False
    assert report["real_employer_qualification_verified"] is False
    assert report["external_actions_performed"] is False


def test_mutated_benchmark_expectation_fails_closed():
    payload = deepcopy(load_fixture())
    row = next(case for case in payload["cases"] if case["id"] == "ai-keyword-not-inside-paid")
    row["expect"]["lanes"]["Paid Marketing Specialist"] = "recommended"

    report = evaluate_fixture(payload)
    assert report["failed_cases"] == 1
    assert report["failures"][0]["case_id"] == "ai-keyword-not-inside-paid"
    assert "job lanes" in report["failures"][0]["details"]


def test_missing_category_and_duplicate_case_id_fail_schema():
    payload = load_fixture()
    missing = deepcopy(payload)
    missing["required_categories"].append("unaudited-fantasy-category")
    with pytest.raises(ValueError, match="missing required category"):
        evaluate_fixture(missing)

    duplicate = deepcopy(payload)
    duplicate["cases"].append(deepcopy(duplicate["cases"][0]))
    with pytest.raises(ValueError, match="IDs must be unique"):
        evaluate_fixture(duplicate)


def test_fixture_is_read_only_and_checked_into_repository():
    assert DEFAULT_FIXTURE.is_file()
    assert load_fixture(DEFAULT_FIXTURE)["schema"] == BENCHMARK_SCHEMA

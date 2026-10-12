"""Contract and privacy tests for the offline independent human-review evidence gate."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.evaluate_human_relevance import (
    ADJUDICATION, DEFAULT_DIR, REPORT, ReviewContractError,
    evaluate_review, read_document,
)


def fixtures() -> tuple[dict, dict, dict, dict, dict]:
    return tuple(read_document(DEFAULT_DIR / filename) for filename in (
        "set.json", "predictions.json", "review-a.json",
        "review-b.json", "adjudication.json",
    ))


def test_fictional_two_reviewers_and_adjudication_report_only_sample_metrics():
    result = evaluate_review(*fixtures())
    assert result["contract"] == REPORT
    assert result["dataset_kind"] == "synthetic"
    assert result["status"] == "reviewed_sample_complete"
    assert result["prediction_sha"] == "fc94e78e779650e781277ee1056ec92cd26a6e98"
    assert result["agreement"]["double_labeled_cases"] == 12
    assert result["agreement"]["exact_agreements"] == 10
    assert result["agreement"]["disagreements"] == 2
    assert result["agreement"]["raw_agreement_rate"] == 0.8333
    assert -1 <= result["agreement"]["cohen_kappa"] <= 1
    assert result["adjudication_needed_count"] == 2
    assert result["adjudication_case_ids"] == []

    metric = result["metrics"]
    assert metric["cases"] == 12
    assert metric["recommended"] == 6
    assert metric["relevant"] == 5
    assert metric["relevant_recommended"] == 4
    assert metric["unrelated_recommended"] == 1
    assert metric["precision_at_recommended_in_reviewed_sample"] == 0.6667
    assert metric["recall_of_relevant_in_reviewed_sample"] == 0.8
    assert set(result["slices"]) >= {"fi", "en", "career-switch", "bilingual", "junior"}
    assert result["empirical_population_accuracy_established"] is False
    assert result["employer_outcomes_measured"] is False
    assert result["qualification_eligibility_verified"] is False
    assert result["external_actions_performed"] is False
    assert result["reviewer_blindness_independently_verified"] is False


def test_no_adjudication_reports_disagreements_but_no_precision_or_recall():
    manifest, predictions, first, second, _ = fixtures()
    report = evaluate_review(manifest, predictions, first, second)
    assert report["status"] == "requires_adjudication"
    assert report["metrics"] is None
    assert report["slices"] == {}
    assert report["adjudication_case_ids"] == ["case-005", "case-010"]


def test_missing_extra_and_duplicate_case_labels_fail_closed():
    manifest, predictions, first, second, adjudication = fixtures()
    gone = deepcopy(first)
    gone["rows"].pop()
    with pytest.raises(ReviewContractError, match="incomplete"):
        evaluate_review(manifest, predictions, gone, second, adjudication)

    repeated = deepcopy(second)
    repeated["rows"].append(deepcopy(repeated["rows"][0]))
    with pytest.raises(ReviewContractError, match="duplicate"):
        evaluate_review(manifest, predictions, first, repeated, adjudication)

    extra = deepcopy(predictions)
    extra["rows"][0]["role_title"] = "PERSONALIZED SECRET CV"
    with pytest.raises(ReviewContractError, match="shape"):
        evaluate_review(manifest, extra, first, second, adjudication)


def test_rejects_profile_claims_and_same_reviewer_disguised_as_independent():
    manifest, predictions, first, second, adjudication = fixtures()
    unsafe = deepcopy(predictions)
    unsafe["rows"][0]["qualification_verified"] = True
    with pytest.raises(ReviewContractError, match="qualification"):
        evaluate_review(manifest, unsafe, first, second, adjudication)

    fake_independence = deepcopy(second)
    fake_independence["reviewer_alias"] = first["reviewer_alias"]
    with pytest.raises(ReviewContractError, match="independent"):
        evaluate_review(manifest, predictions, first, fake_independence, adjudication)

    unblinded = deepcopy(first)
    unblinded["blind_to_predictions"] = False
    with pytest.raises(ReviewContractError, match="blindness"):
        evaluate_review(manifest, predictions, unblinded, second, adjudication)


def test_rejects_misleading_provenance_and_disallows_tiny_real_sample():
    manifest, predictions, first, second, adjudication = fixtures()
    needs_rights = deepcopy(manifest)
    needs_rights["dataset_kind"] = "approved_real"
    with pytest.raises(ReviewContractError, match="source rights"):
        evaluate_review(needs_rights, predictions, first, second, adjudication)

    needs_sample = deepcopy(needs_rights)
    needs_sample["provenance"]["source_rights_reviewed"] = True
    with pytest.raises(ReviewContractError, match="at least 30"):
        evaluate_review(needs_sample, predictions, first, second, adjudication)

    has_personal = deepcopy(manifest)
    has_personal["provenance"]["applicant_data_excluded"] = False
    with pytest.raises(ReviewContractError, match="PII"):
        evaluate_review(has_personal, predictions, first, second, adjudication)

    has_restricted = deepcopy(manifest)
    has_restricted["provenance"]["restricted_data_excluded"] = False
    with pytest.raises(ReviewContractError, match="restricted"):
        evaluate_review(has_restricted, predictions, first, second, adjudication)


def test_frozen_identity_timestamp_and_adjudicator_constraints():
    manifest, predictions, first, second, adjudication = fixtures()
    wrong_revision = deepcopy(predictions)
    wrong_revision["model_sha"] = "main"
    with pytest.raises(ReviewContractError, match="immutable"):
        evaluate_review(manifest, wrong_revision, first, second, adjudication)

    early_review = deepcopy(first)
    early_review["reviewed_at"] = "2024-12-31T20:00:00Z"
    with pytest.raises(ReviewContractError, match="predates"):
        evaluate_review(manifest, predictions, early_review, second, adjudication)

    wrong_adjudicator = deepcopy(adjudication)
    wrong_adjudicator["adjudicator_alias"] = first["reviewer_alias"]
    with pytest.raises(ReviewContractError, match="distinct"):
        evaluate_review(manifest, predictions, first, second, wrong_adjudicator)

    wrong_labels = deepcopy(adjudication)
    wrong_labels["rows"] = wrong_labels["rows"][:-1]
    with pytest.raises(ReviewContractError, match="exactly"):
        evaluate_review(manifest, predictions, first, second, wrong_labels)


def test_output_never_contains_job_titles_cv_or_reviewer_identifiers():
    manifest, predictions, first, second, adjudication = fixtures()
    report = evaluate_review(manifest, predictions, first, second, adjudication)
    encoded = json.dumps(report)
    assert "synthetic-rater-a" not in encoded
    assert "synthetic-rater-b" not in encoded
    assert "job-boards.greenhouse.io" not in encoded
    assert "Synthetic CV" not in encoded
    assert "application_url" not in encoded
    assert "candidate" not in encoded.lower()


def test_bounded_reader_rejects_symlinks_and_oversized_untrusted_files(tmp_path: Path):
    file_path = tmp_path / "sensitive-private.json"
    file_path.write_bytes(b"X" * 256_001)
    with pytest.raises(ReviewContractError, match="size limit"):
        read_document(file_path)

    link = tmp_path / "link.json"
    link.symlink_to(DEFAULT_DIR / "set.json")
    with pytest.raises(ReviewContractError, match="regular local"):
        read_document(link)


def test_cli_status_codes_and_redacted_contract_failures(tmp_path: Path):
    success = subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_human_relevance"],
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout)["status"] == "reviewed_sample_complete"

    unresolved = subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_human_relevance", "--no-adjudication"],
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert unresolved.returncode == 3
    assert json.loads(unresolved.stdout)["metrics"] is None

    private = tmp_path / "private-email-applicant@example.invalid.json"
    private.write_text('{"untrusted_cv":"SECRET CV DATA"}', encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, "-m", "scripts.evaluate_human_relevance",
         "--review-a", str(private)],
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert rejected.returncode == 2
    assert rejected.stdout == ""
    assert "SECRET CV DATA" not in rejected.stderr
    assert "applicant@example.invalid" not in rejected.stderr
    assert json.loads(rejected.stderr)["status"] == "invalid_evidence"

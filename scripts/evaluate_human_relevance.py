#!/usr/bin/env python3
"""Independent, offline SmartPloy human relevance review.

Only accepts anonymous case IDs, categorical labels and frozen lane decisions.
Never reads CVs, job descriptions, a database, a browser or network resources.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping

REVIEW_SET = "smartploy.human-relevance.set.v1"
PREDICTIONS = "smartploy.human-relevance.predictions.v1"
REVIEW = "smartploy.human-relevance.review.v1"
ADJUDICATION = "smartploy.human-relevance.adjudication.v1"
REPORT = "smartploy.human-relevance.report.v1"

MAX_BYTES = 256_000
CASE_ID = re.compile(r"case-[0-9]{3,5}\Z")
ALIAS = re.compile(r"[a-z][a-z0-9-]{1,39}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
SLICES = frozenset({
    "fi", "en", "bilingual", "junior", "experienced", "career-switch",
    "remote", "hybrid", "onsite", "public", "private", "unknown-metadata",
})
LABELS = frozenset({"relevant", "related", "unrelated", "insufficient"})
LANES = frozenset({"recommended", "broader"})
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "tests/fixtures/human_relevance"


class ReviewContractError(ValueError):
    """Invalid, untrusted or incomplete review evidence. Do not print input."""


def _shape(value: Any, allowed: set[str], needed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or not needed <= value.keys() or value.keys() - allowed:
        raise ReviewContractError("unexpected review document shape")
    return value


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ReviewContractError("timestamp contract invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewContractError("timestamp contract invalid") from exc
    if parsed.tzinfo is None:
        raise ReviewContractError("timestamp must have timezone")
    return parsed.astimezone(timezone.utc)


def read_document(path: Path) -> dict[str, Any]:
    """Read a bounded file, rejecting symlinks and unknown raw text fields."""
    try:
        if path.is_symlink() or not path.is_file():
            raise ReviewContractError("review file must be a regular local file")
        with path.open("rb") as handle:
            blob = handle.read(MAX_BYTES + 1)
        if len(blob) > MAX_BYTES:
            raise ReviewContractError("review document exceeds size limit")
        value = json.loads(blob.decode("utf-8"))
        if not isinstance(value, dict):
            raise ReviewContractError("review document must be an object")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewContractError("review document cannot be parsed") from exc


def _valid_alias(value: Any) -> bool:
    return isinstance(value, str) and ALIAS.fullmatch(value) is not None


def _records(
    data: Mapping[str, Any], field: str, *,
    keys: set[str], label_key: str,
    allowed_labels: frozenset[str],
) -> dict[str, dict[str, Any]]:
    rows = data.get(field)
    if not isinstance(rows, list) or not 0 <= len(rows) <= 500:
        raise ReviewContractError("review rows must be a bounded list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = _shape(row, keys, keys)
        case_id = record.get("id")
        if not isinstance(case_id, str) or CASE_ID.fullmatch(case_id) is None:
            raise ReviewContractError("anonymous case ID is invalid")
        if case_id in indexed:
            raise ReviewContractError("duplicate review case")
        if record.get(label_key) not in allowed_labels:
            raise ReviewContractError("review decision class is invalid")
        indexed[case_id] = record
    return indexed


def validate_set(data: Any) -> tuple[dict[str, Any], dict[str, set[str]], datetime]:
    source = _shape(data, {
        "contract", "dataset_id", "dataset_kind", "frozen_at",
        "provenance", "cases",
    }, {
        "contract", "dataset_id", "dataset_kind", "frozen_at",
        "provenance", "cases",
    })
    if source["contract"] != REVIEW_SET or not _valid_alias(source["dataset_id"]):
        raise ReviewContractError("review set contract is invalid")
    kind = source["dataset_kind"]
    if kind not in {"synthetic", "approved_real"}:
        raise ReviewContractError("dataset kind invalid")
    provenance = _shape(
        source["provenance"],
        {"source_rights_reviewed", "applicant_data_excluded", "restricted_data_excluded"},
        {"source_rights_reviewed", "applicant_data_excluded", "restricted_data_excluded"},
    )
    if any(type(v) is not bool for v in provenance.values()):
        raise ReviewContractError("provenance gates must be boolean")
    if not provenance["applicant_data_excluded"] or not provenance["restricted_data_excluded"]:
        raise ReviewContractError("PII/restricted content must not enter review report")
    if kind == "approved_real" and not provenance["source_rights_reviewed"]:
        raise ReviewContractError("real examples require separately attested source rights")

    cases = source["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 500:
        raise ReviewContractError("review set must have 1-500 cases")
    indexed: dict[str, set[str]] = {}
    for item in cases:
        case = _shape(item, {"id", "slices"}, {"id", "slices"})
        key, tags = case["id"], case["slices"]
        if not isinstance(key, str) or CASE_ID.fullmatch(key) is None or key in indexed:
            raise ReviewContractError("review set has invalid or duplicate anonymous case ID")
        if (not isinstance(tags, list) or not 1 <= len(tags) <= 5
                or any(not isinstance(t, str) or t not in SLICES for t in tags)
                or len(set(tags)) != len(tags)):
            raise ReviewContractError("review slice labels invalid")
        indexed[key] = set(tags)
    if kind == "approved_real":
        if len(indexed) < 30:
            raise ReviewContractError("real sample requires at least 30 reviewed cases")
        if sum("fi" in tags for tags in indexed.values()) < 5 or sum(
            "en" in tags for tags in indexed.values()
        ) < 5:
            raise ReviewContractError("real sample requires Finnish and English coverage")
    return source, indexed, _time(source["frozen_at"])


def _validate_metadata(
    data: Any, contract: str, dataset_id: str, allowed: set[str],
) -> dict[str, Any]:
    source = _shape(data, allowed, allowed)
    if source["contract"] != contract or source["dataset_id"] != dataset_id:
        raise ReviewContractError("review dataset identity/contract mismatch")
    return source


def _check_set(index: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if index.keys() != expected.keys():
        raise ReviewContractError("incomplete or unexpected case IDs")


def _safe_fraction(numer: int, denom: int) -> float | None:
    return round(numer / denom, 4) if denom else None


def _metrics(rows: list[tuple[str, str]]) -> dict[str, Any]:
    count = len(rows)
    relevant = sum(label == "relevant" for _, label in rows)
    recommended = sum(lane == "recommended" for lane, _ in rows)
    true_recommended = sum(lane == "recommended" and label == "relevant" for lane, label in rows)
    false_recommended = sum(lane == "recommended" and label == "unrelated" for lane, label in rows)
    uncertain_recommended = sum(lane == "recommended" and label == "insufficient" for lane, label in rows)
    related_in_broader = sum(lane == "broader" and label == "related" for lane, label in rows)
    return {
        "cases": count,
        "relevant": relevant,
        "recommended": recommended,
        "relevant_recommended": true_recommended,
        "unrelated_recommended": false_recommended,
        "insufficient_recommended": uncertain_recommended,
        "related_in_broader": related_in_broader,
        "precision_at_recommended_in_reviewed_sample": _safe_fraction(true_recommended, recommended),
        "recall_of_relevant_in_reviewed_sample": _safe_fraction(true_recommended, relevant),
    }


def _reviewer_agreement(first: Mapping[str, str], second: Mapping[str, str]) -> dict[str, Any]:
    total = len(first)
    exact = sum(first[key] == second[key] for key in first)
    a, b = Counter(first.values()), Counter(second.values())
    p = exact / total
    chance = sum((a[label] / total) * (b[label] / total) for label in LABELS)
    kappa = ((p - chance) / (1 - chance)) if chance < 1 else (1.0 if p == 1 else 0.0)
    if not math.isfinite(kappa):
        raise ReviewContractError("reviewer reliability result invalid")
    return {
        "double_labeled_cases": total,
        "exact_agreements": exact,
        "disagreements": total - exact,
        "raw_agreement_rate": round(p, 4),
        "cohen_kappa": round(kappa, 4),
    }


def evaluate_review(
    manifest: dict[str, Any], predictions: dict[str, Any],
    review_a: dict[str, Any], review_b: dict[str, Any],
    adjudication: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute non-identifying evidence; never inspect underlying job content."""
    dataset, cases, frozen_at = validate_set(manifest)
    dataset_id = dataset["dataset_id"]

    pred = _validate_metadata(
        predictions, PREDICTIONS, dataset_id,
        {"contract", "dataset_id", "model_sha", "generated_at", "rows"},
    )
    if not isinstance(pred["model_sha"], str) or SHA.fullmatch(pred["model_sha"]) is None:
        raise ReviewContractError("predictions must pin a full immutable model/code SHA")
    predicted_at = _time(pred["generated_at"])
    if predicted_at < frozen_at:
        raise ReviewContractError("predictions precede dataset freeze")
    predicted = _records(
        pred, "rows", keys={"id", "lane", "qualification_verified"},
        label_key="lane", allowed_labels=LANES,
    )
    _check_set(predicted, cases)
    if any(row["qualification_verified"] is not False for row in predicted.values()):
        raise ReviewContractError("search preferences cannot assert verified qualification")

    reviews: list[dict[str, str]] = []
    reviewer_aliases: list[str] = []
    reviewed_times: list[datetime] = []
    for candidate in (review_a, review_b):
        item = _validate_metadata(
            candidate, REVIEW, dataset_id,
            {"contract", "dataset_id", "reviewer_alias", "reviewed_at", "blind_to_predictions", "rows"},
        )
        if not _valid_alias(item["reviewer_alias"]) or item["blind_to_predictions"] is not True:
            raise ReviewContractError("reviewer alias or declared blindness invalid")
        reviewer_aliases.append(item["reviewer_alias"])
        when = _time(item["reviewed_at"])
        if when < predicted_at:
            raise ReviewContractError("review predates frozen predictions")
        reviewed_times.append(when)
        labeled = _records(
            item, "rows", keys={"id", "relevance"},
            label_key="relevance", allowed_labels=LABELS,
        )
        _check_set(labeled, cases)
        reviews.append({case_id: row["relevance"] for case_id, row in labeled.items()})
    if reviewer_aliases[0] == reviewer_aliases[1]:
        raise ReviewContractError("two independent reviewer aliases are required")

    disagreement_ids = sorted(
        case_id for case_id in cases if reviews[0][case_id] != reviews[1][case_id]
    )
    resolved = dict(reviews[0])
    if adjudication is not None:
        decision = _validate_metadata(
            adjudication, ADJUDICATION, dataset_id,
            {"contract", "dataset_id", "adjudicator_alias", "adjudicated_at", "rows"},
        )
        if (not _valid_alias(decision["adjudicator_alias"])
                or decision["adjudicator_alias"] in reviewer_aliases
                or _time(decision["adjudicated_at"]) < max(reviewed_times)):
            raise ReviewContractError("adjudicator must be distinct and later than reviewers")
        final = _records(
            decision, "rows", keys={"id", "relevance"},
            label_key="relevance", allowed_labels=LABELS,
        )
        if set(final) != set(disagreement_ids):
            raise ReviewContractError("adjudication must cover exactly conflicting cases")
        resolved.update({case_id: row["relevance"] for case_id, row in final.items()})

    agreement = _reviewer_agreement(reviews[0], reviews[1])
    ready = not disagreement_ids or adjudication is not None
    report = {
        "contract": REPORT,
        "dataset_id": dataset_id,
        "dataset_kind": dataset["dataset_kind"],
        "prediction_sha": pred["model_sha"],
        "status": "reviewed_sample_complete" if ready else "requires_adjudication",
        "empirical_population_accuracy_established": False,
        "employer_outcomes_measured": False,
        "qualification_eligibility_verified": False,
        "external_actions_performed": False,
        "reviewer_blindness_independently_verified": False,
        "agreement": agreement,
        "adjudication_needed_count": len(disagreement_ids),
        "adjudication_case_ids": disagreement_ids if not ready else [],
        "metrics": None,
        "slices": {},
    }
    if not ready:
        return report

    pairs = [(predicted[key]["lane"], resolved[key]) for key in cases]
    report["metrics"] = _metrics(pairs)
    for slice_name in sorted({tag for tags in cases.values() for tag in tags}):
        subset = [
            (predicted[key]["lane"], resolved[key])
            for key, tags in cases.items() if slice_name in tags
        ]
        # Suppress tiny real-world slices to avoid inadvertently reporting
        # characteristics of one identifiable job/source in public logs.
        if dataset["dataset_kind"] == "approved_real" and len(subset) < 5:
            report["slices"][slice_name] = {"cases": len(subset), "suppressed": True}
        else:
            report["slices"][slice_name] = _metrics(subset)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline, anonymous two-reviewer relevance evaluation")
    parser.add_argument("--set", type=Path, default=DEFAULT_DIR / "set.json")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_DIR / "predictions.json")
    parser.add_argument("--review-a", type=Path, default=DEFAULT_DIR / "review-a.json")
    parser.add_argument("--review-b", type=Path, default=DEFAULT_DIR / "review-b.json")
    parser.add_argument("--adjudication", type=Path, default=DEFAULT_DIR / "adjudication.json")
    parser.add_argument("--no-adjudication", action="store_true",
                        help="Produce only reviewer agreement and unresolved anonymous case IDs")
    args = parser.parse_args(argv)
    try:
        result = evaluate_review(
            read_document(args.set), read_document(args.predictions),
            read_document(args.review_a), read_document(args.review_b),
            None if args.no_adjudication else read_document(args.adjudication),
        )
    except (ReviewContractError, OSError, ValueError, TypeError, KeyError) as exc:
        # Never echo input, filesystem paths, reviewers' raw notes or CV data.
        print(json.dumps({
            "contract": REPORT, "status": "invalid_evidence",
            "error_category": type(exc).__name__,
        }), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 3 if result["status"] == "requires_adjudication" else 0


if __name__ == "__main__":
    raise SystemExit(main())

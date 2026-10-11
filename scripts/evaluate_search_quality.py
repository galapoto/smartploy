#!/usr/bin/env python3
"""Offline synthetic SmartPloy ranking/qualification evaluation.

Runs without network access, employer applications, database writes, cloud AI,
or user CVs. Case-level output only contains fixture IDs and assertion labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.scoring import score_candidate
from smartploy.search_preferences import revise_preferences, search_jobs


CONTRACT = "smartploy.search-quality.synthetic.v1"
DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/search_quality_fi_en.json"
FIXED_NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
SOURCE = SourcePolicy("synthetic-eval", "Synthetic evaluation", "manual", ("manual",))
CATEGORIES = frozenset({
    "bilingual", "seniority", "language", "location", "work-mode",
    "career-switch", "boundaries", "general", "degree", "evidence",
})


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    """Load a bounded, explicitly synthetic labeled fixture."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("contract") != CONTRACT:
        raise ValueError("unsupported search quality fixture contract")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 500:
        raise ValueError("fixture must contain 1-500 cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("fixture contains a non-object case")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", case_id):
            raise ValueError("fixture case identifier is invalid")
        if case_id in seen:
            raise ValueError("duplicate fixture case identifier")
        seen.add(case_id)
        if case.get("kind") not in {"search", "fit"} or case.get("category") not in CATEGORIES:
            raise ValueError("fixture case kind/category is invalid")
        if not isinstance(case.get("job"), dict) or not isinstance(case.get("expected"), dict):
            raise ValueError("fixture case requires job and expected objects")
        if case["kind"] == "search":
            if not isinstance(case.get("preferences"), dict):
                raise ValueError("search case requires preferences")
            if case["expected"].get("lane") not in {"recommendations", "broader", "all"}:
                raise ValueError("search case requires a valid expected lane")
        elif not isinstance(case.get("facts"), list):
            raise ValueError("fit case requires fact list")
    return payload


def _candidate(case: dict[str, Any]):
    job = case["job"]
    identifier = case["id"]
    url = f"https://jobs.example.invalid/synthetic/{identifier}"
    payload = {
        "company": "Synthetic Evaluation Employer",
        "role_title": job.get("title", ""),
        "description": job.get("description", ""),
        "location": job.get("location", ""),
        "language": job.get("language", ""),
        "work_mode": job.get("work_mode", "review"),
        "requirements": job.get("requirements", []),
        "nice_to_have": job.get("nice_to_have", []),
        "application_url": url,
        # Synthetic fixtures cannot authorize external model forwarding.
        "external_ai_forwarding_allowed": False,
    }
    observation = SourceObservation(
        source_id="synthetic-eval", source_mode="manual", source_url=url,
        raw_text="synthetic evaluation job", payload=payload,
        observed_at="2026-10-11T00:00:00+00:00",
        source_external_id=identifier,
    )
    result = normalize_observation(observation, SOURCE)
    if result.candidate is None:
        raise ValueError(f"synthetic observation could not be normalized: {identifier}")
    return result.candidate


def _text_checks(
    expected: dict[str, Any],
    card: dict[str, Any],
    issues: list[str],
) -> None:
    fields = {
        "reason": "reasons",
        "unknown": "unknown_fields",
        "mismatch": "mismatched_fields",
    }
    for label, actual_field in fields.items():
        values = card.get(actual_field, [])
        if not isinstance(values, list):
            issues.append(f"{label}_shape")
            continue
        for predicate in ("contains", "excludes"):
            key = f"{label}_{predicate}"
            phrases = expected.get(key, [])
            if not isinstance(phrases, list) or any(not isinstance(v, str) for v in phrases):
                issues.append(f"{key}_fixture_shape")
                continue
            for phrase in phrases:
                found = any(phrase in value for value in values)
                if found != (predicate == "contains"):
                    issues.append(key)


def _search_case(case: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    pref = revise_preferences(
        "synthetic-eval", case["preferences"], revision=0,
    )
    result = search_jobs([_candidate(case)], pref)
    found = [
        (name, cards[0])
        for name, cards in (
            ("recommendations", result["recommendations"]),
            ("broader", result["broader"]),
            ("all", result["all_jobs"]),
        )
        if cards
    ]
    observed_lane = found[0][0] if len(found) == 1 else "invalid"
    issues: list[str] = []
    if observed_lane != expected["lane"]:
        issues.append("lane")
    score_kind = (
        "none" if pref.mode == "general"
        else "preference_alignment_not_verified_qualification"
    )
    if result.get("score_kind") != score_kind or (
        "score_kind" in expected and expected["score_kind"] != result.get("score_kind")
    ):
        issues.append("score_kind")
    if len(found) == 1:
        card = found[0][1]
        _text_checks(expected, card, issues)
        if "preference_score" in expected and card.get("preference_score") != expected["preference_score"]:
            issues.append("preference_score")
        if pref.mode == "general" and (
            card.get("preference_score") is not None
            or card.get("reasons")
            or card.get("unknown_fields")
            or card.get("mismatched_fields")
        ):
            issues.append("general_profile_leak")
    else:
        issues.append("candidate_card_count")
    return {
        "id": case["id"], "kind": "search", "category": case["category"],
        "passed": not issues, "failed_checks": sorted(set(issues)),
        "expected_lane": expected["lane"], "observed_lane": observed_lane,
    }


def _fit_case(case: dict[str, Any]) -> dict[str, Any]:
    facts: list[ProfileFact] = []
    for row in case["facts"]:
        if not isinstance(row, dict) or type(row.get("approved", False)) is not bool:
            raise ValueError("synthetic evidence fact has invalid shape")
        facts.append(ProfileFact(
            fact_type=row["fact_type"], value=row["value"],
            source="synthetic-evaluation", approved=row.get("approved", False),
        ))
    profile = CandidateProfile(profile_id="synthetic-eval", facts=tuple(facts))
    score = score_candidate(_candidate(case), profile, now=FIXED_NOW)
    expected = case["expected"]
    issues: list[str] = []
    for key, field in (
        ("mandatory_gaps", score.mandatory_gaps),
        ("matched_requirements", score.matched_requirements),
    ):
        if key in expected and list(field) != expected[key]:
            issues.append(key)
    if ("prepare_recommended" in expected
            and score.prepare_recommended is not expected["prepare_recommended"]):
        issues.append("prepare_recommended")
    if len(score.matched_evidence_ids) < expected.get("min_evidence_count", 0):
        issues.append("evidence_count")
    return {
        "id": case["id"], "kind": "fit", "category": case["category"],
        "passed": not issues, "failed_checks": sorted(set(issues)),
    }


def evaluate_suite(payload: dict[str, Any]) -> dict[str, Any]:
    """Return bounded, content-free evidence; fail on any labeled regression."""
    if payload.get("contract") != CONTRACT or not isinstance(payload.get("cases"), list):
        raise ValueError("search quality fixture contract is invalid")
    cases = payload["cases"]
    results: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    category_passed: Counter[str] = Counter()
    confusion: Counter[str] = Counter()
    for case in cases:
        result = _search_case(case) if case["kind"] == "search" else _fit_case(case)
        results.append(result)
        category = result["category"]
        category_counts[category] += 1
        category_passed[category] += int(result["passed"])
        if result["kind"] == "search" and result["expected_lane"] != "all":
            actual = result["observed_lane"] == "recommendations"
            expected = result["expected_lane"] == "recommendations"
            confusion["tp" if actual and expected else
                      "fp" if actual and not expected else
                      "fn" if expected and not actual else "tn"] += 1
    tp, fp, fn = confusion["tp"], confusion["fp"], confusion["fn"]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    passed = sum(row["passed"] for row in results)
    return {
        "contract": CONTRACT, "dataset_kind": "synthetic_not_empirical",
        "case_count": len(results), "passed": passed,
        "failed": len(results) - passed,
        "search_cases": sum(row["kind"] == "search" for row in results),
        "fit_cases": sum(row["kind"] == "fit" for row in results),
        "recommendation_confusion": {
            key: confusion[key] for key in ("tp", "fp", "fn", "tn")
        },
        "recommendation_precision": round(precision, 4),
        "recommendation_recall": round(recall, 4),
        "categories": {
            name: {"cases": count, "passed": category_passed[name]}
            for name, count in sorted(category_counts.items())
        },
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate synthetic Finnish/English SmartPloy search quality offline"
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args(argv)
    try:
        report = evaluate_suite(load_fixture(args.fixture))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"Search quality evaluation failed to load/run: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    else:
        print(
            f"SYNTHETIC_SEARCH_QUALITY: {report['passed']}/{report['case_count']} PASS; "
            f"precision={report['recommendation_precision']:.4f}; "
            f"recall={report['recommendation_recall']:.4f} "
            "(not real-market accuracy)"
        )
        for row in report["cases"]:
            if not row["passed"]:
                print(f"FAILED: {row['id']} ({','.join(row['failed_checks'])})")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline, synthetic quality gates for job search and approved-evidence matching.

This is NOT a real-world job-fit measurement, employment eligibility check,
live ATS poll or employer application. Fixtures never use a user's CV/account.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from .domain import SourceObservation, SourcePolicy, normalize_observation
from .profile import CandidateProfile, ProfileFact
from .scoring import score_candidate
from .search_preferences import SearchPreferences, revise_preferences, search_jobs

BENCHMARK_SCHEMA = "smartploy.matching-quality-fixtures.v1"
REPORT_SCHEMA = "smartploy.matching-quality-report.v1"
DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "benchmarks" / "matching_quality_fi_en_v1.json"
SOURCE_POLICY = SourcePolicy("synthetic-quality", "Synthetic fixture", "manual", ("manual",))
FIXED_NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema") != BENCHMARK_SCHEMA:
        raise ValueError("Unsupported synthetic matching benchmark schema")
    return payload


def _candidate(spec: Mapping[str, Any], case_id: str, index: int):
    title = str(spec["title"])
    description = str(spec.get("description", ""))
    url = f"https://synthetic.example.invalid/jobs/{case_id}/{index}"
    observation = SourceObservation(
        source_id="synthetic-quality",
        source_mode="manual",
        source_url=url,
        raw_text=title + " " + description,
        observed_at="2026-10-11T10:00:00+00:00",
        posted_at=str(spec.get("posted_at", "")),
        payload={
            "company": "Synthetic Employer",
            "role_title": title,
            "description": description,
            "location": str(spec.get("location", "")),
            "language": str(spec.get("language", "")),
            "work_mode": str(spec.get("work_mode", "review")),
            "requirements": list(spec.get("requirements", [])),
            "nice_to_have": list(spec.get("nice_to_have", [])),
            "application_url": url,
        },
    )
    normalized = normalize_observation(observation, SOURCE_POLICY)
    if normalized.candidate is None:
        raise ValueError(f"Synthetic fixture cannot normalize job: {case_id}/{index}")
    return normalized.candidate


def _difference(
    errors: list[str], name: str, expected: Any, actual: Any,
) -> None:
    if actual != expected:
        errors.append(f"{name}: expected {expected!r}; observed {actual!r}")


def _required_phrases(
    errors: list[str], cards: Mapping[str, Mapping[str, Any]],
    expectations: Mapping[str, Any], *, field: str, key: str,
    inverted: bool = False,
) -> None:
    for title, phrases in expectations.get(key, {}).items():
        if title not in cards:
            errors.append(f"{key}: no job card for {title!r}")
            continue
        texts = [str(part) for part in cards[title].get(field, [])]
        for phrase in phrases:
            found = any(str(phrase).casefold() in text.casefold() for text in texts)
            if found == inverted:
                errors.append(
                    f"{key}: {'unexpected' if inverted else 'missing'} "
                    f"{phrase!r} for {title!r}"
                )


def _check_discovery(case: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = case["kind"]
    if kind == "first_use":
        preferences = SearchPreferences(profile_id="synthetic-quality")
    elif kind == "search":
        preferences = revise_preferences(
            "synthetic-quality", case["preferences"], revision=0,
        )
    else:
        raise ValueError("Unknown discovery benchmark kind")

    jobs = [_candidate(spec, str(case["id"]), i) for i, spec in enumerate(case["jobs"])]
    titles = [job.job.role_title for job in jobs]
    if len(titles) != len(set(titles)):
        raise ValueError("Benchmark job titles must be unique within each case")

    result = search_jobs(jobs, preferences)
    expected = case["expect"]
    expected_lanes = dict(expected["lanes"])
    cards = {
        row["job"]["role_title"]: row
        for lane in ("recommendations", "broader", "all_jobs")
        for row in result[lane]
    }
    actual_lanes = {title: row["lane"] for title, row in cards.items()}
    _difference(errors, "job lanes", expected_lanes, actual_lanes)
    _difference(errors, "mode", expected["mode"], result["mode"])
    _difference(errors, "available count", len(jobs), result["available_count"])

    if result["mode"] in {"general", "setup_required"}:
        _difference(errors, "score kind", "none", result["score_kind"])
        for title, item in cards.items():
            if item.get("preference_score") is not None or item.get("reasons"):
                errors.append(f"Unprofiled {result['mode']} result scored job {title!r}")
    elif result["mode"] == "personalized":
        _difference(
            errors, "score kind",
            "preference_alignment_not_verified_qualification", result["score_kind"],
        )
        for title, item in cards.items():
            score = item.get("preference_score")
            if type(score) is not int or not 0 <= score <= 100:
                errors.append(f"Invalid preference alignment score for {title!r}")
    else:
        errors.append("Unknown discovery result mode")

    for lane, ordered in expected.get("ordered_lanes", {}).items():
        actual = [row["job"]["role_title"] for row in result[lane]]
        _difference(errors, f"{lane} order", ordered, actual)

    for title, upper in expected.get("score_below", {}).items():
        score = cards.get(title, {}).get("preference_score")
        if type(score) is not int or score >= upper:
            errors.append(f"Expected {title!r} preference score below {upper}; got {score!r}")

    for field, key, inverted in (
        ("unknown_fields", "unknown_contains", False),
        ("mismatched_fields", "mismatch_contains", False),
        ("reasons", "reason_contains", False),
        ("reasons", "reason_excludes", True),
    ):
        _required_phrases(errors, cards, expected, field=field, key=key, inverted=inverted)

    if preferences.to_dict()["verified_qualification_fit"] is not False:
        errors.append("Search preferences must never assert verified qualification")
    return errors


def _check_evidence(case: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    candidate = _candidate(case["job"], str(case["id"]), 0)
    facts = tuple(
        ProfileFact(
            fact_type=str(spec["type"]),
            value=str(spec["value"]),
            source="synthetic-fixture",
            approved=spec.get("approved") is True,
            tags=tuple(spec.get("tags", ())),
        ).normalized()
        for spec in case.get("facts", [])
    )
    profile = CandidateProfile(profile_id="synthetic-quality", facts=facts)
    result = score_candidate(candidate, profile, now=FIXED_NOW)
    expected = case["expect"]
    for key in ("mandatory_gaps", "matched_requirements"):
        if key in expected:
            _difference(errors, key, expected[key], list(getattr(result, key)))
    if expected.get("no_auto_prepare") and result.prepare_recommended:
        errors.append("Mandatory qualification uncertainty cannot auto-prepare a draft")
    if expected.get("no_evidence_credit") and result.matched_evidence_ids:
        errors.append("Unapproved or unrelated facts received matching evidence credit")
    if not 0 <= result.fit_score <= 100 or not 0 <= result.priority_score <= 100:
        errors.append("Evidence scores must be bounded to 0..100")
    if result.prepare_recommended and result.mandatory_gaps:
        errors.append("A result with mandatory gaps cannot recommend automatic draft preparation")
    return errors


def evaluate_fixture(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return full synthetic regression evidence without network or storage writes."""
    if payload.get("schema") != BENCHMARK_SCHEMA:
        raise ValueError("Unsupported synthetic matching benchmark schema")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Synthetic benchmark requires a nonempty case list")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Synthetic benchmark IDs must be unique")

    categories = Counter(str(case["category"]) for case in cases)
    required = set(payload.get("required_categories", []))
    if not required or required - categories.keys():
        raise ValueError("Synthetic benchmark is missing required category coverage")

    failures: list[dict[str, str]] = []
    passed: Counter[str] = Counter()
    for case in cases:
        case_id, category, kind = case["id"], case["category"], case["kind"]
        try:
            if kind in {"first_use", "search"}:
                errors = _check_discovery(case)
            elif kind == "evidence":
                errors = _check_evidence(case)
            else:
                errors = ["Unknown benchmark kind"]
        except (ValueError, TypeError, KeyError) as exc:
            errors = [f"Invalid synthetic fixture or evaluator contract: {type(exc).__name__}"]
        if errors:
            failures.append({
                "case_id": case_id, "category": category,
                "details": " | ".join(errors[:8]),
            })
        else:
            passed[category] += 1

    return {
        "schema": REPORT_SCHEMA,
        "fixture_schema": BENCHMARK_SCHEMA,
        "synthetic_only": True,
        "real_world_match_accuracy_measured": False,
        "real_employer_qualification_verified": False,
        "external_actions_performed": False,
        "total_cases": len(cases),
        "passed_cases": len(cases) - len(failures),
        "failed_cases": len(failures),
        "categories": {
            name: {"passed": passed[name], "total": categories[name]}
            for name in sorted(categories)
        },
        "failures": failures,
    }

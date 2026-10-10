"""Strict, evidence-bound v2 application document contract.

Candidate facts are untrusted unless their ids belong to the immutable approved snapshot.
All printable candidate sections require evidence ids; empty sections are allowed.
"""
from __future__ import annotations

import json
from typing import Any

from .preparations import PreparationResultError, approved_evidence_ids

V2_PACKAGE_CONTRACT = "smartploy.application.package.v2"
V2_DRAFT_SCHEMA = "smartploy.application.draft.v2"
V2_ACTION = "application_package_v2"
MAX_DRAFT_BYTES = 256_000
MAX_TEXT_LENGTH = 8_000
MAX_ENTRIES = 100


def _object(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise PreparationResultError(f"{field} must be an object")
    return value


def _text(value: Any, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH or (required and not value.strip()):
        raise PreparationResultError(f"{field} must be a bounded nonempty string")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise PreparationResultError(f"{field} contains control characters")
    return value


def _list(value: Any, field: str) -> list:
    if not isinstance(value, list) or len(value) > MAX_ENTRIES:
        raise PreparationResultError(f"{field} must be a bounded list")
    return value


def _evidence(row: dict, allowed: set[str], field: str) -> None:
    ids = _list(row.get("evidence_fact_ids"), field + ".evidence_fact_ids")
    if not ids or not all(isinstance(item, str) and item and len(item) < 128 for item in ids):
        raise PreparationResultError(f"{field} needs evidence_fact_ids")
    if not set(ids).issubset(allowed):
        raise PreparationResultError(f"{field} references evidence outside approved snapshot")


def _claim(value: Any, allowed: set[str], field: str) -> None:
    row = _object(value, field)
    _text(row.get("text"), field + ".text")
    _evidence(row, allowed, field)


def _claims(value: Any, allowed: set[str], field: str) -> None:
    for index, row in enumerate(_list(value, field)):
        _claim(row, allowed, f"{field}[{index}]")


def _snapshot_types(snapshot: dict) -> dict[str, set[str]]:
    types: dict[str, set[str]] = {}
    for kind, facts in _object(snapshot.get("facts"), "snapshot.facts").items():
        if not isinstance(facts, list):
            raise PreparationResultError("snapshot facts must be lists")
        for fact in facts:
            record = _object(fact, "snapshot.fact")
            fact_id = record.get("fact_id")
            if isinstance(fact_id, str):
                types.setdefault(fact_id, set()).add(kind)
    return types


def parse_v2_draft(output_text: str, evidence_snapshot: dict) -> dict[str, Any]:
    if not isinstance(output_text, str) or len(output_text.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise PreparationResultError("v2 draft is missing or exceeds maximum size")
    try:
        value = json.loads(output_text)
    except (ValueError, TypeError) as exc:
        raise PreparationResultError("v2 draft must be a JSON object") from exc
    root = _object(value, "draft")
    if root.get("schema") != V2_DRAFT_SCHEMA:
        raise PreparationResultError("v2 draft schema mismatch")
    allowed = approved_evidence_ids(evidence_snapshot)
    fact_types = _snapshot_types(evidence_snapshot)
    if not allowed:
        raise PreparationResultError("approved evidence snapshot is empty")

    cv = _object(root.get("cv"), "cv")
    _text(cv.get("headline"), "cv.headline")
    _claim(cv.get("professional_summary"), allowed, "cv.professional_summary")
    for field in ("skills", "education", "certifications", "projects", "languages"):
        _claims(cv.get(field), allowed, "cv." + field)

    for index, value in enumerate(_list(cv.get("experience"), "cv.experience")):
        item = _object(value, f"cv.experience[{index}]")
        _claim(item.get("position"), allowed, f"cv.experience[{index}].position")
        _claims(item.get("bullets"), allowed, f"cv.experience[{index}].bullets")

    for index, value in enumerate(_list(cv.get("header"), "cv.header")):
        field = f"cv.header[{index}]"
        item = _object(value, field)
        kind = _text(item.get("kind"), field + ".kind")
        if kind not in {"name", "email", "phone", "linkedin", "github", "portfolio", "location"}:
            raise PreparationResultError("unsupported CV header field")
        _text(item.get("text"), field + ".text")
        _evidence(item, allowed, field)
        expected = {"name": {"identity"}, "location": {"location", "contact"}}.get(kind, {"contact"})
        for evidence_id in item["evidence_fact_ids"]:
            if not fact_types.get(evidence_id, set()).intersection(expected):
                raise PreparationResultError("CV header has incorrect evidence type")
            matched = [
                fact for category, facts in evidence_snapshot["facts"].items()
                if category in expected for fact in facts
                if fact.get("fact_id") == evidence_id
            ]
            if not any(item["text"].strip() == str(fact.get("value", "")).strip() for fact in matched):
                raise PreparationResultError("CV header must equal approved identity/contact fact value")

    for text in _list(cv.get("do_not_claim"), "cv.do_not_claim"):
        _text(text, "cv.do_not_claim item")
    cover = _object(root.get("cover_letter"), "cover_letter")
    _claims(cover.get("paragraphs"), allowed, "cover_letter.paragraphs")
    for field in ("risks", "review_checklist"):
        for line in _list(root.get(field), field):
            _text(line, field + " item")
    return root


V2_DRAFT_INSTRUCTIONS = """Return JSON only with schema smartploy.application.draft.v2.
Required keys: schema, cv, cover_letter, risks, review_checklist.
cv: headline string, professional_summary {text,evidence_fact_ids},
header [{kind,text,evidence_fact_ids}], skills/education/certifications/projects/languages
[{text,evidence_fact_ids}], experience [{position:{text,evidence_fact_ids},
bullets:[{text,evidence_fact_ids}]}], do_not_claim [string].
cover_letter: {paragraphs:[{text,evidence_fact_ids}]}.
Each personal claim must cite actual approved immutable candidate_evidence fact IDs.
Header strings must match exact approved identity/contact/location fact values.
Omit unsupported facts instead of inventing personal information or results.
Do not browse, upload, submit, email, click or claim consequential external action.
Human review is mandatory. Final submit authority is false."""

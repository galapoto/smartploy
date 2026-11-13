"""Explicit, reusable employer-question answers from the applicant's existing profile.

An answer is saved once per signed-in account and reused only for an EXACT,
ordinary question. Different/changed questions and sensitive disclosures are
always returned for human review. This module never submits or uploads data.
"""
from __future__ import annotations

import json
from hashlib import sha256
import re
import unicodedata
from typing import Any

SCHEMA = "smartploy.profile_answer.v1"
MAX_QUESTION = 150
MAX_ANSWER = 480
MAX_PACKET_ANSWERS = 16
# Conservative policy. No "generic" user answer may smuggle protected or
# legal disclosures into an ordinary employer form field.
SENSITIVE = re.compile(
    r"\b(?:visa|immigration|citizen|citizenship|nationality|passport|"
    r"work (?:permit|authori[sz]ation)|sponsor|salary|compensation|wage|"
    r"pay expectation|gender|sex|sexual|male|female|non.binary|race|"
    r"ethnic|black|white|asian|hispanic|religion|disability|disabled|"
    r"health|medical|veteran|criminal|background check|"
    r"privacy|consent|gdpr|legal|agreement|attest|signature|"
    r"birth|age|social security|government id|tax id|bank account|"
    r"työlupa|oleskelulupa|kansalaisuus|sukupuoli|uskonto|palkka|"
    r"henkilötunnus|suostumus|arbetstillstånd|medborgarskap|"
    r"personnummer|samtycke|lön)\b",
    re.IGNORECASE,
)


def _text(raw: Any, *, maximum: int, field: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"Application answer {field} must be text")
    value = unicodedata.normalize("NFKC", raw).strip()
    if not value or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"Application answer {field} is missing or invalid")
    return value


def canonical_question(value: str) -> str:
    """Never fuzzy-match similar but materially different employer questions."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def decode_profile_answer(raw: str) -> dict[str, str]:
    try:
        if not isinstance(raw, str) or len(raw) > 700:
            raise ValueError
        row = json.loads(raw)
        if not isinstance(row, dict) or set(row) != {"schema", "question", "answer"} or row["schema"] != SCHEMA:
            raise ValueError
        question = _text(row["question"], maximum=MAX_QUESTION, field="question")
        answer = _text(row["answer"], maximum=MAX_ANSWER, field="answer")
        if SENSITIVE.search(question) or SENSITIVE.search(answer):
            raise ValueError("Sensitive, legal and protected answers must be handled on the employer form")
        return {"question": question, "answer": answer}
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Use a valid saved application question and answer") from exc
    except ValueError as exc:
        if str(exc):
            raise
        raise ValueError("Use a valid saved application question and answer") from exc


def encode_profile_answer(raw: str) -> str:
    row = decode_profile_answer(raw)
    return json.dumps({"schema": SCHEMA, **row}, ensure_ascii=False, separators=(",", ":"))


def approved_answers_for_packet(profile: Any) -> list[dict[str, str]]:
    """Return only unique non-sensitive account-approved Q/A; conflicts fail closed.

    Never take unapproved values, arbitrary CV prose, or duplicate conflicting
    answers. The browser must still ask the applicant before each employer fill.
    """
    choices: dict[str, list[dict[str, str]]] = {}
    for fact in profile.approved_facts:
        if fact.fact_type != "application_answer":
            continue
        try:
            row = decode_profile_answer(fact.value)
        except ValueError:
            continue
        key = canonical_question(row["question"])
        choices.setdefault(key, []).append(row)
    result: list[dict[str, str]] = []
    for key in sorted(choices):
        unique = {item["answer"] for item in choices[key]}
        if len(choices[key]) != 1 or len(unique) != 1:
            # Old and new competing entries require the user to resolve them.
            continue
        result.append(choices[key][0])
    return result[:MAX_PACKET_ANSWERS]


def saved_answers_sha256(answers: list[dict[str, str]]) -> str:
    """Cross-language stable SHA of the actual Q/A, not just document metadata.

    Bind it to the signed-in owner's latest approved answer set. The
    independent MV3 browser checks this after every new private review.
    """
    rows = [
        {"question": row["question"], "answer": row["answer"]}
        for row in answers
    ]
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return sha256(("smartploy.saved.answers.v1\0" + encoded).encode("utf-8")).hexdigest()

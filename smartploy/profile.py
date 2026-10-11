"""Approved-evidence candidate profile model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib
import re
from urllib.parse import urlsplit

from .domain import canonical_json, normalize_identity_text, normalize_space, utc_now_iso


FACT_TYPES = {
    "identity",
    "contact",
    "email",
    "phone",
    "linkedin",
    "github",
    "skill",
    "language",
    "education",
    "experience",
    "domain",
    "certification",
    "project",
    "location",
    "work_authorization",
    "preference",
}


@dataclass(frozen=True)
class ProfileFact:
    fact_type: str
    value: str
    source: str
    approved: bool = False
    confidence: float = 1.0
    tags: tuple[str, ...] = ()
    fact_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ProfileFact":
        fact_type = normalize_identity_text(self.fact_type).replace(" ", "_")
        if fact_type not in FACT_TYPES:
            raise ValueError(f"unsupported profile fact type: {fact_type}")
        value = normalize_space(self.value)
        source = normalize_space(self.source)
        if not value:
            raise ValueError("profile fact value is required")
        if fact_type == "email":
            if len(value) > 254 or not re.fullmatch(
                r"[^\\s@]+@[^\\s@]+\\.[^\\s@]+", value
            ):
                raise ValueError("Please provide a valid email address")
        if fact_type == "phone":
            if not (5 <= len(value) <= 40) or len(re.findall(r"\\d", value)) < 5 or not re.fullmatch(
                r"[+\\d() .-]+", value
            ):
                raise ValueError("Please provide a valid phone number")
        if fact_type in {"linkedin", "github"}:
            parsed = urlsplit(value)
            allowed_hosts = (
                {"linkedin.com", "www.linkedin.com"} if fact_type == "linkedin"
                else {"github.com", "www.github.com"}
            )
            if (
                parsed.scheme != "https" or parsed.hostname not in allowed_hosts
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not parsed.path or parsed.path == "/"
            ):
                raise ValueError("Please provide a public HTTPS profile URL")

        if not source:
            raise ValueError("profile fact source is required")
        confidence = float(self.confidence)
        if confidence < 0 or confidence > 1:
            raise ValueError("profile fact confidence must be between 0 and 1")
        tags = tuple(sorted({normalize_identity_text(item) for item in self.tags if normalize_identity_text(item)}))
        fact_id = str(self.fact_id or "").strip()
        if not fact_id:
            material = canonical_json(
                {
                    "fact_type": fact_type,
                    "value": normalize_identity_text(value),
                    "source": source,
                    "tags": tags,
                }
            )
            fact_id = f"fact-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"
        return ProfileFact(
            fact_type=fact_type,
            value=value,
            source=source,
            approved=bool(self.approved),
            confidence=confidence,
            tags=tags,
            fact_id=fact_id,
            created_at=str(self.created_at or utc_now_iso()),
            metadata=dict(self.metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "fact_id": item.fact_id,
            "fact_type": item.fact_type,
            "value": item.value,
            "normalized_value": normalize_identity_text(item.value),
            "source": item.source,
            "approved": item.approved,
            "confidence": item.confidence,
            "tags": list(item.tags),
            "created_at": item.created_at,
            "metadata": dict(item.metadata),
        }


@dataclass(frozen=True)
class CandidateProfile:
    profile_id: str = "default"
    facts: tuple[ProfileFact, ...] = ()

    @property
    def approved_facts(self) -> tuple[ProfileFact, ...]:
        return tuple(item.normalized() for item in self.facts if item.normalized().approved)

    def approved_evidence(self) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for fact in self.approved_facts:
            grouped.setdefault(fact.fact_type, []).append(
                {
                    "fact_id": fact.fact_id,
                    "value": fact.value,
                    "tags": list(fact.tags),
                    "source": fact.source,
                    "confidence": fact.confidence,
                }
            )
        return {
            "contract": "smartploy.profile.evidence.v1",
            "profile_id": self.profile_id,
            "facts": grouped,
            "approved_fact_count": sum(len(items) for items in grouped.values()),
        }

    def summary(self) -> dict[str, Any]:
        normalized = tuple(item.normalized() for item in self.facts)
        return {
            "profile_id": self.profile_id,
            "fact_count": len(normalized),
            "approved_fact_count": sum(1 for item in normalized if item.approved),
            "fact_types": sorted({item.fact_type for item in normalized}),
        }


def facts_from_json(value: Any) -> list[ProfileFact]:
    rows = value.get("facts") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ValueError("profile JSON must be a list or an object with a facts list")
    facts: list[ProfileFact] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each profile fact must be an object")
        facts.append(
            ProfileFact(
                fact_id=str(row.get("fact_id") or ""),
                fact_type=str(row.get("fact_type") or ""),
                value=str(row.get("value") or ""),
                source=str(row.get("source") or ""),
                approved=bool(row.get("approved", False)),
                confidence=float(row.get("confidence", 1.0)),
                tags=tuple(str(item) for item in row.get("tags", [])),
                created_at=str(row.get("created_at") or utc_now_iso()),
                metadata=dict(row.get("metadata") or {}),
            ).normalized()
        )
    return facts

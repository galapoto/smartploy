"""Curated Finland trainee/training destinations, distinct from live job postings.

These are provider landing pages, NEVER claims that an intake is currently open.
No scraping, external requests, user identity, ATS application or CV processing.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlsplit

REGISTRY = Path(__file__).resolve().parents[1] / "config" / "finland_training_program_directory.json"
ALLOWED_DOMAINS = frozenset({
    "www.saranen.fi", "www.academicwork.fi", "www.siemens.com",
    "www.nokia.com", "www.kuntarekry.fi", "valtiolle.fi",
    "tyomarkkinatori.fi",
})
ALLOWED_KINDS = frozenset({
    "recruitment_training", "academy", "employer_trainee", "internship_portal",
})
ALLOWED_FIELDS = frozenset({
    "id", "provider", "title", "kind", "region", "url", "focus", "eligibility_note",
})


class TrainingDirectoryError(ValueError):
    pass


def load_training_programs(registry: Path = REGISTRY) -> list[dict[str, object]]:
    """Validate entire immutable source directory before exposing anything."""
    try:
        entries = json.loads(registry.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise TrainingDirectoryError("training provider directory unavailable") from exc
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise TrainingDirectoryError("invalid training programme directory")
    ids: set[str] = set()
    verified: list[dict[str, object]] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != ALLOWED_FIELDS:
            raise TrainingDirectoryError("unexpected training provider fields")
        uid = item.get("id")
        if not isinstance(uid, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,80}", uid):
            raise TrainingDirectoryError("invalid programme identifier")
        if uid in ids:
            raise TrainingDirectoryError("duplicate programme identifier")
        ids.add(uid)
        for key in ("provider", "title", "region", "eligibility_note"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 500:
                raise TrainingDirectoryError("invalid programme field")
        if item.get("kind") not in ALLOWED_KINDS:
            raise TrainingDirectoryError("unsupported programme kind")
        url = item.get("url")
        if not isinstance(url, str) or len(url) > 800:
            raise TrainingDirectoryError("invalid provider URL")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise TrainingDirectoryError("invalid provider URL") from exc
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOMAINS
                or parsed.username or parsed.password or port is not None
                or not parsed.path.startswith("/") or parsed.fragment):
            raise TrainingDirectoryError("unreviewed training provider domain")
        focus = item.get("focus")
        if (not isinstance(focus, list) or not 1 <= len(focus) <= 8
                or not all(isinstance(tag, str) and 1 <= len(tag.strip()) <= 60
                           for tag in focus)):
            raise TrainingDirectoryError("invalid programme focus")
        verified.append({
            "id": uid, "provider": item["provider"], "title": item["title"],
            "kind": item["kind"], "region": item["region"], "url": url,
            "focus": list(focus), "eligibility_note": item["eligibility_note"],
            "opening_status": "check_provider",
            "listing_type": "directory_link",
            "counts_as_live_job": False,
            "automatic_application_authorized": False,
        })
    return verified

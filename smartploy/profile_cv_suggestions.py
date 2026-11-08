"""SP116: conservative, local CV-to-profile suggestions (never auto-approved).

Only information already in the applicant's PRIVATE uploaded CV is parsed.
No ObumAI call, third-party inference, employer networking or approval.
Extract exact contact syntax and limited literal skill names, not legal status,
education claims or guesses about identity; user must explicitly approve.
"""
from __future__ import annotations

import re

from .profile import ProfileFact

EMAIL = re.compile(r"(?<![\w@])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,20}\b")
PROFILE_URL = re.compile(
    r"https://(?:www\.)?(?:linkedin\.com/in|github\.com)/[A-Za-z0-9_.~%/-]+",
    re.IGNORECASE,
)
PHONE_LINE = re.compile(
    r"(?im)^\s*(?:phone|telephone|mobile|puhelin|tel\.?)\s*:\s*"
    r"(\+?\d[\d() .-]{5,35}\d)\s*$"
)
# Explicit lexical evidence only. Suggestions cannot become verified facts
# until the applicant personally accepts them. Keep a bounded allowlist.
TECH = (
    "Python", "SQL", "Power BI", "Excel", "PostgreSQL", "Docker",
    "Azure", "AWS", "TypeScript", "JavaScript", "React", "Node.js",
    "Java", "C#", "C++", "Git", "Jira", "Scrum", "Cypress",
    "Robot Framework", "Linux", "Tableau", "Kubernetes",
)


def _skill_mentioned(text: str, skill: str) -> bool:
    pattern = re.escape(skill).replace(r"\ ", r"\s+")
    return re.search(
        r"(?<![\w+#])" + pattern + r"(?![\w+#])", text, re.IGNORECASE,
    ) is not None


def cv_review_suggestions(text: str) -> list[ProfileFact]:
    if not isinstance(text, str) or not text.strip():
        return []
    # Imported text is already bounded; scan only limited text in memory.
    source = text[:30_000]
    suggestions: list[ProfileFact] = []
    emails = sorted(set(EMAIL.findall(source)), key=str.casefold)
    if len(emails) == 1:
        suggestions.append(ProfileFact(
            "email", emails[0], "cv-suggestion", approved=False, confidence=0.5,
        ))
    urls = PROFILE_URL.findall(source)
    for fact_type, prefix in (
        ("linkedin", "linkedin.com/in/"), ("github", "github.com/"),
    ):
        matched = sorted({
            url.rstrip("/.,;")
            for url in urls if prefix in url.lower()
        }, key=str.casefold)
        if len(matched) == 1:
            suggestions.append(ProfileFact(
                fact_type, matched[0], "cv-suggestion",
                approved=False, confidence=0.5,
            ))
    phones = set(PHONE_LINE.findall(source))
    if len(phones) == 1:
        suggestions.append(ProfileFact(
            "phone", next(iter(phones)), "cv-suggestion",
            approved=False, confidence=0.5,
        ))
    for skill in TECH:
        if _skill_mentioned(source, skill):
            suggestions.append(ProfileFact(
                "skill", skill, "cv-suggestion",
                approved=False, confidence=0.35,
            ))
    # If CV is ambiguous, do NOT generate a "best guess".
    unique: dict[tuple[str, str], ProfileFact] = {}
    for fact in suggestions:
        try:
            item = fact.normalized()
        except ValueError:
            continue
        unique[(item.fact_type, item.value.casefold())] = item
    return list(unique.values())[:25]

"""CV-first discovery from this account's existing local CV and shared live jobs.

Reuses the current bounded PDF/DOCX extraction, job ledger, Finnish bilingual
title matching and the pure search_preferences ranker. This module ONLY derives
suggested search signals from unapproved CV text: it never approves a career
fact, asserts employer eligibility, sends CV data to a model or takes employer
actions. No new table, model dependency or external network request.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from .cv_storage import StoredCV
from .domain import JobCandidate
from .search_preferences import SearchPreferences, _mentions_phrase, search_jobs

# These are retrieval cues, not claims about experience or credentials.
# Prefer explicit role phrases; single generic words like "IT", "work",
# "project" and "office" must not create a false job qualification.
ROLE_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Suunnittelija", ("suunnittelija", "suunnittelijana", "planner", "planning specialist")),
    ("IT-suunnittelija", ("it-suunnittelija", "ict-suunnittelija", "IT planner", "ICT planner")),
    ("Toimistosuunnittelija", ("toimistosuunnittelija", "office planner", "office coordinator")),
    ("Hallinnon suunnittelija", ("hallinnon suunnittelija", "hallintokoordinaattori", "administrative coordinator")),
    ("Projektikoordinaattori", ("projektikoordinaattori", "project coordinator", "project planner")),
    ("Kehittämisasiantuntija", ("kehittämisasiantuntija", "kehittämissuunnittelija", "development specialist")),
    ("Tietohallinnon asiantuntija", ("tietohallinnon asiantuntija", "information management specialist")),
    ("Viestintäkoordinaattori", ("viestintäkoordinaattori", "communications coordinator")),
    ("Data Analyst", ("data analyst", "data analyytikko", "data-analyytikko", "data analysis")),
    ("Data Engineer", ("data engineer", "tietoinsinööri", "data engineering")),
    ("Business Analyst", ("business analyst", "business analysis", "liiketoiminta-analyytikko")),
    ("Software Tester", ("software tester", "software testing", "test engineer", "ohjelmistotestaaja", "qa tester")),
    ("IT Support", ("IT support", "ICT support", "IT-tuki", "IT-tukihenkilö", "service desk")),
    ("Software Developer", ("software developer", "software engineer", "ohjelmistokehittäjä")),
    ("Cybersecurity Specialist", ("cybersecurity", "cyber security", "tietoturva", "information security")),
    ("Nurse", ("registered nurse", "sairaanhoitaja", "nursing degree")),
    ("Environmental Engineer", ("environmental engineer", "ympäristöinsinööri")),
)
SKILL_CUES: tuple[str, ...] = (
    "Power BI", "SQL", "Python", "Excel", "SharePoint", "Microsoft 365",
    "Microsoft Teams", "Azure", "Data analytics", "Data visualization",
    "Project management", "Documentation", "Intranet", "Web content",
    "Software testing", "Business analysis", "Information management",
    "Process development", "Cybersecurity", "React", "JavaScript",
    "Customer service", "Administrative planning",
)


def detected_cv_signals(cv_text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Bounded, deterministic text retrieval; not inferred employment history."""
    text = str(cv_text or "")[:60000]
    roles = tuple(canonical for canonical, aliases in ROLE_CUES
                  if any(_mentions_phrase(text, word) for word in aliases))[:12]
    topics = tuple(word for word in SKILL_CUES if _mentions_phrase(text, word))[:12]
    return roles, topics


def cv_job_matches(
    cv: StoredCV | None,
    jobs: Sequence[JobCandidate],
    *,
    profile_id: str,
    max_items: int = 120,
    recommended_offset: int = 0,
    other_offset: int = 0,
    query: str = "",
    selected_job_key: str = "",
) -> dict[str, object]:
    """Return source-current jobs ranked from CV text, with honest uncertainty.

    This is pure matching; the caller must authenticate and scope the CV to
    profile_id using the existing tenant_context/owner CV repository.
    """
    if type(max_items) is not int or not 1 <= max_items <= 300:
        raise ValueError("Invalid CV job result limit")
    if any(type(offset) is not int or not 0 <= offset <= 100000
           for offset in (recommended_offset, other_offset)):
        raise ValueError("Invalid CV job result offset")
    if (not isinstance(query, str) or len(query) > 120
            or any(ord(char) < 32 for char in query)):
        raise ValueError("Invalid CV job search query")
    if (not isinstance(selected_job_key, str) or len(selected_job_key) > 160
            or any(ord(char) < 32 for char in selected_job_key)):
        raise ValueError("Invalid selected job key")
    if cv is not None and cv.profile_id != profile_id:
        raise ValueError("CV owner does not match signed-in profile")
    current = [item for item in jobs if item.source_current]
    if cv is None:
        return {
            "cv_present": False, "cv_filename": "", "match_mode": "upload_cv",
            "detected_roles": [], "detected_topics": [],
            "recommended": [], "other_jobs": [],
            "current_jobs_count": len(current), "recommended_count": 0,
            "other_jobs_count": 0, "selected_job": None,
            "matched_from": "none", "qualifications_verified": False,
            "employer_actions_performed": False,
        }

    roles, topics = detected_cv_signals(cv.text)
    has_signals = bool(roles or topics)
    base = SearchPreferences(
        profile_id=profile_id, completed=True,
        mode="personalized" if has_signals else "general",
    )
    preferences = replace(
        base, roles=roles,
        # A skill-only CV still retrieves postings that mention those skills,
        # without silently converting a tool into a claimed job title.
        keywords=topics[:8] if not roles else (),
        skills=topics,
    )
    result = search_jobs(current, preferences)
    recommended = result["recommendations"] if has_signals else []
    other = result["broader"] if has_signals else result["all_jobs"]
    # Preserve the selected job even when it is outside both page windows.
    # Its identity must be an exact current source ledger key, not a guessed
    # URL or a title search; the owner must still review before preparing.
    selected_job = next(
        (row for row in recommended + other
         if row["canonical_key"] == selected_job_key), None
    ) if selected_job_key else None

    # Filter across ALL current ranked results before slicing any page.
    # Filtering the browser's first 80/120 rows would silently hide later
    # vacancies even when their title or employer matches the user's query.
    needle = query.strip().casefold()
    if needle:
        def matches(row: dict[str, object]) -> bool:
            job = row["job"]
            return any(
                needle in str(job.get(field, "") or "").casefold()
                for field in ("role_title", "company", "location")
            )
        recommended = [row for row in recommended if matches(row)]
        other = [row for row in other if matches(row)]

    # Never turn incidental keyword overlap into an asserted qualification.
    # Preserve broader/weak results for exploration, clearly separate.
    return {
        "cv_present": True, "cv_filename": cv.filename,
        "match_mode": "cv_text_signals" if has_signals else "no_recognized_cv_signals",
        "detected_roles": list(roles), "detected_topics": list(topics),
        "recommended": recommended[recommended_offset:recommended_offset + max_items],
        "other_jobs": other[other_offset:other_offset + max_items],
        "current_jobs_count": len(current),
        "recommended_count": len(recommended),
        "other_jobs_count": len(other),
        "selected_job": selected_job,
        "matched_from": "local_cv_text_not_approved_evidence",
        "qualifications_verified": False,
        "employer_actions_performed": False,
    }

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
) -> dict[str, object]:
    """Return source-current jobs ranked from CV text, with honest uncertainty.

    This is pure matching; the caller must authenticate and scope the CV to
    profile_id using the existing tenant_context/owner CV repository.
    """
    if not isinstance(max_items, int) or not 1 <= max_items <= 300:
        raise ValueError("Invalid CV job result limit")
    if cv is not None and cv.profile_id != profile_id:
        raise ValueError("CV owner does not match signed-in profile")
    current = [item for item in jobs if item.source_current]
    if cv is None:
        return {
            "cv_present": False, "cv_filename": "", "match_mode": "upload_cv",
            "detected_roles": [], "detected_topics": [],
            "recommended": [], "other_jobs": [],
            "current_jobs_count": len(current), "recommended_count": 0,
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
    # Never turn incidental keyword overlap into an asserted qualification.
    # Preserve broader/weak results for exploration, clearly separate.
    return {
        "cv_present": True, "cv_filename": cv.filename,
        "match_mode": "cv_text_signals" if has_signals else "no_recognized_cv_signals",
        "detected_roles": list(roles), "detected_topics": list(topics),
        "recommended": recommended[:max_items],
        "other_jobs": other[:max_items],
        "current_jobs_count": len(current),
        "recommended_count": len(recommended),
        "matched_from": "local_cv_text_not_approved_evidence",
        "qualifications_verified": False,
        "employer_actions_performed": False,
    }

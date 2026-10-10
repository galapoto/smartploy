"""Explainable deterministic Fit and Priority scoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import re

from .domain import JobCandidate, normalize_identity_text, normalize_work_mode
from .profile import CandidateProfile, ProfileFact


ALIASES = {
    "python": ("python",),
    "sql": ("sql",),
    "power_bi": ("power bi", "powerbi"),
    "excel": ("excel",),
    "azure": ("azure",),
    "gcp": ("gcp", "google cloud"),
    "aws": ("aws", "amazon web services"),
    "api": ("api", "rest api", "rajapinta"),
    "etl": ("etl", "data pipeline", "datapipeline", "tietoputki"),
    "testing": ("testing", "software testing", "testaus", "ohjelmistotestaus", "qa", "quality assurance"),
    "selenium": ("selenium",),
    "robot_framework": ("robot framework",),
    "jira": ("jira",),
    "scrum": ("scrum", "agile", "kettera"),
    "data_analysis": ("data analysis", "data analytics", "analytiikka", "data analyysi", "data-analyysi"),
    "business_analysis": ("business analyst", "business analysis", "liiketoiminta-analyysi"),
    "compliance": ("compliance", "vaatimustenmukaisuus", "regulatory", "sääntely"),
    "healthcare": ("healthcare", "health care", "terveydenhuolto", "sote"),
    "environment": ("environmental", "environment", "ympäristö", "ymparisto"),
    "finnish": ("finnish", "suomi", "suomen kieli", "suomenkielinen"),
    "english": ("english", "englanti", "englannin kieli", "englanninkielinen"),
}
STOPWORDS = {
    "and", "or", "with", "the", "a", "an", "of", "for", "to", "in", "on", "is", "are",
    "ja", "tai", "sekä", "seka", "kanssa", "että", "etta", "osaaminen", "kokemus", "experience",
    "skills", "skill", "knowledge", "tuntemus", "hyvä", "hyva", "good", "required", "requirement",
}


@dataclass(frozen=True)
class ScoreResult:
    canonical_key: str
    fit_score: int
    priority_score: int
    queue: str
    fit_breakdown: dict[str, int]
    priority_breakdown: dict[str, int]
    matched_evidence_ids: tuple[str, ...]
    matched_requirements: tuple[str, ...]
    mandatory_gaps: tuple[str, ...]
    preferred_gaps: tuple[str, ...]
    prepare_recommended: bool
    status: str = "scored"

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_key": self.canonical_key,
            "fit_score": self.fit_score,
            "priority_score": self.priority_score,
            "queue": self.queue,
            "fit_breakdown": dict(self.fit_breakdown),
            "priority_breakdown": dict(self.priority_breakdown),
            "matched_evidence_ids": list(self.matched_evidence_ids),
            "matched_requirements": list(self.matched_requirements),
            "mandatory_gaps": list(self.mandatory_gaps),
            "preferred_gaps": list(self.preferred_gaps),
            "prepare_recommended": self.prepare_recommended,
            "status": self.status,
        }


def _concepts(value: str) -> set[str]:
    text = normalize_identity_text(value)
    found = {
        concept
        for concept, aliases in ALIASES.items()
        if any(normalize_identity_text(alias) in text for alias in aliases)
    }
    tokens = {
        token
        for token in re.findall(r"[a-z0-9åäö]+", text)
        if len(token) >= 3 and token not in STOPWORDS
    }
    return found | tokens


def _fact_concepts(fact: ProfileFact) -> set[str]:
    return _concepts(" ".join((fact.value, *fact.tags)))


def _requirement_match(requirement: str, facts: tuple[ProfileFact, ...]) -> tuple[bool, tuple[str, ...]]:
    needed = _concepts(requirement)
    if not needed:
        return False, ()
    matched_ids: list[str] = []
    covered: set[str] = set()
    for fact in facts:
        overlap = needed & _fact_concepts(fact)
        if overlap:
            covered |= overlap
            matched_ids.append(fact.fact_id)
    ratio = len(covered) / len(needed)
    return ratio >= 0.6, tuple(sorted(set(matched_ids)))


def _requirement_component(
    requirements: tuple[str, ...],
    facts: tuple[ProfileFact, ...],
) -> tuple[int | None, list[str], list[str], set[str]]:
    if not requirements:
        return None, [], [], set()
    matches: list[str] = []
    gaps: list[str] = []
    evidence_ids: set[str] = set()
    for requirement in requirements:
        matched, ids = _requirement_match(requirement, facts)
        if matched:
            matches.append(requirement)
            evidence_ids.update(ids)
        else:
            gaps.append(requirement)
    return round(100 * len(matches) / len(requirements)), matches, gaps, evidence_ids


def _facts_of(profile: CandidateProfile, *types: str) -> tuple[ProfileFact, ...]:
    accepted = set(types)
    return tuple(fact for fact in profile.approved_facts if fact.fact_type in accepted)


def _text_component(target: str, facts: tuple[ProfileFact, ...]) -> tuple[int | None, set[str]]:
    if not normalize_identity_text(target) or not facts:
        return None, set()
    needed = _concepts(target)
    if not needed:
        return None, set()
    evidence: set[str] = set()
    covered: set[str] = set()
    for fact in facts:
        concepts = _fact_concepts(fact)
        overlap = needed & concepts
        if overlap:
            covered |= overlap
            evidence.add(fact.fact_id)
    return round(100 * len(covered) / len(needed)), evidence


def _known_skill_component(candidate: JobCandidate, facts: tuple[ProfileFact, ...]) -> tuple[int | None, set[str]]:
    job_concepts = _concepts(
        " ".join(
            (
                candidate.job.role_title,
                candidate.job.description,
                " ".join(candidate.job.requirements),
                " ".join(candidate.job.nice_to_have),
            )
        )
    )
    known = job_concepts & set(ALIASES)
    if not known:
        return None, set()
    profile_map: dict[str, set[str]] = {}
    for fact in facts:
        for concept in _fact_concepts(fact):
            profile_map.setdefault(concept, set()).add(fact.fact_id)
    matched = known & set(profile_map)
    evidence = {fact_id for concept in matched for fact_id in profile_map[concept]}
    return round(100 * len(matched) / len(known)), evidence


def _seniority_component(candidate: JobCandidate, profile: CandidateProfile) -> tuple[int | None, set[str]]:
    target = normalize_identity_text(str(candidate.job.raw.get("seniority") or ""))
    facts = tuple(
        fact
        for fact in profile.approved_facts
        if fact.fact_type == "preference" and ("seniority" in fact.tags or "seniority" in normalize_identity_text(fact.value))
    )
    if not target or target == "unspecified" or not facts:
        return None, set()
    values = {normalize_identity_text(fact.value) for fact in facts}
    ids = {fact.fact_id for fact in facts}
    if target in values:
        return 100, ids
    if target == "senior" and any(value in {"junior", "entry", "trainee"} for value in values):
        return 0, ids
    if target in {"junior", "mid", "mid level"} and any(value in {"junior", "mid", "mid level"} for value in values):
        return 85, ids
    return 50, ids


def _location_component(candidate: JobCandidate, profile: CandidateProfile) -> tuple[int | None, set[str]]:
    facts = _facts_of(profile, "location", "preference")
    location_facts = tuple(
        fact for fact in facts if fact.fact_type == "location" or "location" in fact.tags
    )
    if not candidate.job.location or not location_facts:
        return None, set()
    target = normalize_identity_text(candidate.job.location)
    best = 0
    ids: set[str] = set()
    for fact in location_facts:
        value = normalize_identity_text(fact.value)
        if value and (value in target or target in value):
            best = 100
            ids.add(fact.fact_id)
    return best, ids


def _work_mode_component(candidate: JobCandidate, profile: CandidateProfile) -> tuple[int | None, set[str]]:
    target = normalize_work_mode(candidate.job.work_mode)
    facts = tuple(
        fact for fact in profile.approved_facts
        if fact.fact_type == "preference" and "work_mode" in fact.tags
    )
    if target == "review" or not facts:
        return None, set()
    values = {normalize_work_mode(fact.value) for fact in facts}
    ids = {fact.fact_id for fact in facts}
    return (100 if target in values else 50), ids


def _weighted(components: dict[str, tuple[int | None, int]]) -> tuple[int, dict[str, int]]:
    active = {name: (score, weight) for name, (score, weight) in components.items() if score is not None}
    if not active:
        return 0, {}
    total_weight = sum(weight for _, weight in active.values())
    result = round(sum(score * weight for score, weight in active.values()) / total_weight)
    return max(0, min(100, result)), {name: int(score) for name, (score, _) in active.items()}


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _freshness(candidate: JobCandidate, now: datetime) -> int:
    stamp = _parse_time(candidate.posted_at) or _parse_time(candidate.first_seen_at)
    if stamp is None:
        return 50
    hours = max(0.0, (now - stamp.astimezone(timezone.utc)).total_seconds() / 3600)
    if hours <= 24:
        return 100
    if hours <= 72:
        return 85
    if hours <= 168:
        return 65
    if hours <= 336:
        return 40
    return 20


def _deadline(candidate: JobCandidate, now: datetime) -> int:
    stamp = _parse_time(candidate.job.deadline)
    if stamp is None:
        return 50
    days = (stamp.astimezone(timezone.utc) - now).total_seconds() / 86400
    if days < 0:
        return 0
    if days <= 2:
        return 100
    if days <= 7:
        return 90
    if days <= 14:
        return 75
    if days <= 30:
        return 60
    return 45


def _source_confidence(candidate: JobCandidate) -> int:
    source_class = normalize_identity_text(str(candidate.metadata.get("source_class") or ""))
    if source_class in {"company careers", "official", "public sector jobs"}:
        return 100
    if source_class in {"api", "feed", "verified search"}:
        return 85
    if source_class == "manual":
        return 65
    return 60


def _career_alignment(candidate: JobCandidate, profile: CandidateProfile) -> int:
    facts = tuple(
        fact for fact in profile.approved_facts
        if fact.fact_type == "preference" and ("role" in fact.tags or "career" in fact.tags)
    )
    if not facts:
        return 50
    target = _concepts(candidate.job.role_title)
    best = 0.0
    for fact in facts:
        concepts = _fact_concepts(fact)
        if concepts:
            best = max(best, len(target & concepts) / max(1, len(target)))
    return round(100 * min(1.0, best))


def _application_effort(candidate: JobCandidate) -> int:
    burden = len(candidate.job.required_documents) + len(candidate.job.questions)
    if burden <= 1:
        return 100
    if burden <= 3:
        return 80
    if burden <= 6:
        return 60
    return 40


def _queue(fit: int, priority: int, mandatory_gaps: tuple[str, ...]) -> str:
    if mandatory_gaps:
        if fit >= 72:
            return "review"
        return "possible" if fit >= 60 else "low"
    if fit >= 90 and priority >= 90:
        return "exceptional"
    if fit >= 82 and priority >= 82:
        return "auto_prepare"
    if fit >= 72 and priority >= 72:
        return "review"
    if fit >= 60:
        return "possible"
    return "low"


def score_candidate(
    candidate: JobCandidate,
    profile: CandidateProfile,
    *,
    now: datetime | None = None,
) -> ScoreResult:
    approved = profile.approved_facts
    if not approved:
        return ScoreResult(
            canonical_key=candidate.canonical_key,
            fit_score=0,
            priority_score=0,
            queue="low",
            fit_breakdown={},
            priority_breakdown={},
            matched_evidence_ids=(),
            matched_requirements=(),
            mandatory_gaps=tuple(candidate.job.requirements),
            preferred_gaps=tuple(candidate.job.nice_to_have),
            prepare_recommended=False,
            status="insufficient_evidence",
        )

    mandatory_score, mandatory_matches, mandatory_gaps, mandatory_ids = _requirement_component(
        tuple(candidate.job.requirements), approved
    )
    preferred_score, preferred_matches, preferred_gaps, preferred_ids = _requirement_component(
        tuple(candidate.job.nice_to_have), approved
    )
    skill_score, skill_ids = _known_skill_component(candidate, _facts_of(profile, "skill", "project", "experience"))
    language_score, language_ids = _text_component(candidate.job.language, _facts_of(profile, "language"))
    seniority_score, seniority_ids = _seniority_component(candidate, profile)
    location_score, location_ids = _location_component(candidate, profile)
    work_mode_score, work_mode_ids = _work_mode_component(candidate, profile)
    domain_target = " ".join(
        (
            str(candidate.job.raw.get("sector") or ""),
            candidate.job.role_title,
        )
    )
    domain_score, domain_ids = _text_component(domain_target, _facts_of(profile, "domain", "education", "experience"))
    evidence_quality = round(100 * sum(fact.confidence for fact in approved) / len(approved))

    fit, fit_breakdown = _weighted(
        {
            "mandatory_requirements": (mandatory_score, 35),
            "preferred_requirements": (preferred_score, 10),
            "skill_overlap": (skill_score, 20),
            "language": (language_score, 10),
            "seniority": (seniority_score, 8),
            "location": (location_score, 5),
            "work_mode": (work_mode_score, 4),
            "education_domain": (domain_score, 4),
            "evidence_quality": (evidence_quality, 4),
        }
    )

    now_value = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    freshness = _freshness(candidate, now_value)
    deadline = _deadline(candidate, now_value)
    source_confidence = _source_confidence(candidate)
    career_alignment = _career_alignment(candidate, profile)
    application_effort = _application_effort(candidate)
    priority, priority_breakdown = _weighted(
        {
            "fit": (fit, 65),
            "freshness": (freshness, 15),
            "deadline": (deadline, 8),
            "source_confidence": (source_confidence, 5),
            "career_alignment": (career_alignment, 5),
            "application_effort": (application_effort, 2),
        }
    )

    evidence_ids = (
        mandatory_ids
        | preferred_ids
        | skill_ids
        | language_ids
        | seniority_ids
        | location_ids
        | work_mode_ids
        | domain_ids
    )
    mandatory_gap_tuple = tuple(mandatory_gaps)
    queue = _queue(fit, priority, mandatory_gap_tuple)
    return ScoreResult(
        canonical_key=candidate.canonical_key,
        fit_score=fit,
        priority_score=priority,
        queue=queue,
        fit_breakdown=fit_breakdown,
        priority_breakdown=priority_breakdown,
        matched_evidence_ids=tuple(sorted(evidence_ids)),
        matched_requirements=tuple(mandatory_matches + preferred_matches),
        mandatory_gaps=mandatory_gap_tuple,
        preferred_gaps=tuple(preferred_gaps),
        prepare_recommended=queue in {"exceptional", "auto_prepare"},
    )


def rank_candidates(
    candidates: list[JobCandidate],
    profile: CandidateProfile,
    *,
    now: datetime | None = None,
) -> list[ScoreResult]:
    results = [score_candidate(item, profile, now=now) for item in candidates]
    return sorted(
        results,
        key=lambda item: (item.priority_score, item.fit_score, item.canonical_key),
        reverse=True,
    )

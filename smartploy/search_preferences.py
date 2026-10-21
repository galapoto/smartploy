"""Explicit, per-user search preferences and honest job search alignment.

Search preferences never modify approved CV facts and are never forwarded to
employers or LLMs. General search does not profile or calculate fit scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Sequence

from .career_scope import career_area, title_experience
from .domain import JobCandidate, utc_now_iso

SEARCH_MODES = frozenset({"personalized", "general"})
SENIORITY_LEVELS = frozenset({"any", "entry", "mid", "senior"})
LANGUAGE_OPTIONS = frozenset({"english", "finnish", "swedish"})
WORK_MODE_OPTIONS = frozenset({"remote", "hybrid", "onsite"})
# Conservative bilingual title pairs, not a generic translation or qualification engine.
ROLE_EQUIVALENTS = (
    ("data analyst", "data-analyytikko"),
    ("business analyst", "liiketoiminta-analyytikko"),
    ("software tester", "ohjelmistotestaaja"),
    ("project coordinator", "projektikoordinaattori"),
)
LANGUAGE_LABELS = {
    "english": frozenset({"english", "englanti", "englanninkielinen", "englanniksi", "en"}),
    "finnish": frozenset({"finnish", "suomi", "suomeksi", "suomenkielinen", "fi"}),
    "swedish": frozenset({"swedish", "svenska", "ruotsi", "ruotsiksi", "ruotsinkielinen", "sv"}),
}
STOPWORDS = frozenset({
    "and", "or", "in", "at", "for", "the", "with", "of", "a", "an",
    "junior", "senior", "entry", "level", "graduate", "trainee",
    "harjoittelija", "kokenut", "experienced", "lead", "associate",
    "juniori", "nuorempi", "vanhempi",
    "part", "time", "full", "tyo", "ja", "tai",
})


class SearchPreferenceError(ValueError):
    pass


class SearchPreferenceConflict(SearchPreferenceError):
    pass


def _items(
    values: Sequence[str], *, field: str, maximum: int, size: int,
    allowed: frozenset[str] | None = None,
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > maximum:
        raise SearchPreferenceError(f"{field} must be a list of at most {maximum} items")
    results: list[str] = []
    seen: set[str] = set()
    for original in values:
        if not isinstance(original, str):
            raise SearchPreferenceError(f"{field} items must be text")
        value = " ".join(original.split()).strip()
        if not value or len(value) > size or any(ord(ch) < 32 for ch in value):
            raise SearchPreferenceError(f"{field} contains an invalid value")
        if allowed is not None:
            value = value.casefold()
            if value not in allowed:
                raise SearchPreferenceError(f"{field} contains an unsupported choice")
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            results.append(value)
    return tuple(results)


@dataclass(frozen=True)
class SearchPreferences:
    profile_id: str
    completed: bool = False
    mode: str = "personalized"
    roles: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    seniority: str = "any"
    auto_draft_enabled: bool = False
    revision: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed": self.completed, "mode": self.mode,
            "roles": list(self.roles), "locations": list(self.locations),
            "languages": list(self.languages), "work_modes": list(self.work_modes),
            "keywords": list(self.keywords), "skills": list(self.skills),
            "seniority": self.seniority,
            "auto_draft_enabled": self.auto_draft_enabled,
            "auto_draft_external_actions_authorized": False,
            "revision": self.revision, "updated_at": self.updated_at,
            "verified_qualification_fit": False,
        }


def revise_preferences(
    profile_id: str, data: Mapping[str, Any], *, revision: int,
) -> SearchPreferences:
    mode = data.get("mode")
    if mode not in SEARCH_MODES:
        raise SearchPreferenceError("Choose personalized or general search")
    seniority = data.get("seniority", "any")
    if seniority not in SENIORITY_LEVELS:
        raise SearchPreferenceError("Choose a supported experience level")
    roles = _items(data.get("roles", []), field="roles", maximum=12, size=90)
    locations = _items(data.get("locations", []), field="locations", maximum=12, size=90)
    languages = _items(data.get("languages", []), field="languages", maximum=3,
                       size=20, allowed=LANGUAGE_OPTIONS)
    work_modes = _items(data.get("work_modes", []), field="work_modes", maximum=3,
                        size=12, allowed=WORK_MODE_OPTIONS)
    keywords = _items(data.get("keywords", []), field="keywords", maximum=12, size=60)
    skills = _items(data.get("skills", []), field="skills", maximum=16, size=60)
    if mode == "personalized" and not roles and not keywords:
        raise SearchPreferenceError("Personalized search needs at least one job title or keyword")
    auto_draft = data.get("auto_draft_enabled", False)
    if type(auto_draft) is not bool:
        raise SearchPreferenceError("Automatic draft preparation requires an explicit boolean choice")
    if auto_draft and mode != "personalized":
        raise SearchPreferenceError("Automatic drafts require personalized role targets")
    if auto_draft and not roles:
        raise SearchPreferenceError("Automatic drafts require explicit target job roles")
    if revision < 0:
        raise SearchPreferenceError("Preference revision cannot be negative")
    return SearchPreferences(
        profile_id=profile_id, completed=True, mode=mode, roles=roles,
        locations=locations, languages=languages, work_modes=work_modes,
        keywords=keywords, skills=skills, seniority=seniority,
        auto_draft_enabled=auto_draft,
        revision=revision + 1, updated_at=utc_now_iso(),
    )


def _tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[^\W\d_]+", text.casefold(), re.UNICODE)
            if len(word) >= 2 and word not in STOPWORDS}


def _translated_role_match(title: str, target: str) -> bool:
    """Only promote explicit, near-exact bilingual title equivalents.

    A target like "Data Analyst Manager" must not become "data-analyytikko"
    just because both contain a shorter role phrase. Seniority words are
    deliberately ignored here and evaluated independently when requested.
    """
    tokens = _tokens(target)
    return any(
        (tokens == _tokens(english) and _mentions_phrase(title, finnish))
        or (tokens == _tokens(finnish) and _mentions_phrase(title, english))
        for english, finnish in ROLE_EQUIVALENTS
    )


def _role_alignment(title: str, roles: tuple[str, ...]) -> tuple[float, str]:
    if not roles:
        return 0.0, ""
    title_words = _tokens(title)
    strongest = (0.0, "")
    for term in roles:
        wanted = _tokens(term)
        overlap = len(title_words & wanted) / len(wanted) if wanted else 0.0
        # A target such as "AI" must not match "Paid". Whole-phrase matching
        # also retains punctuation-only tokens like "C++" and title separators.
        if _mentions_phrase(title, term) or _translated_role_match(title, term):
            overlap = 1.0
        if overlap > strongest[0]:
            strongest = overlap, term
    return strongest


def _seniority(title: str) -> str | None:
    # Keep junior/senior markers here even though broad search-token matching
    # intentionally ignores those adjectives.
    words = set(re.findall(r"[^\W\d_]+", title.casefold(), re.UNICODE))
    text = title.casefold()
    if words & {"senior", "principal", "lead", "johtava", "päällikkö", "head", "vanhempi"} or "sr." in text:
        return "senior"
    if words & {"intern", "internship", "trainee", "junior", "graduate", "harjoittelija", "kesätyö", "juniori", "nuorempi"}:
        return "entry"
    if words & {"mid", "midlevel", "intermediate", "keskitaso"}:
        return "mid"
    # Many postings omit experience level. Do not fabricate it.
    return None


def _explicit_target_title_level(job_title: str, roles: tuple[str, ...]) -> str | None:
    """Use a job-title seniority hint only if all matching targets agree.

    A user who selected both "Junior Data Analyst" and "Data Analyst" has
    explicitly included the broader family and must not be narrowed down.
    No experience level is inferred from CV, unapproved facts or job body.
    """
    matching = [
        _seniority(target)
        for target in roles
        if _role_alignment(job_title, (target,))[0] >= 0.75
    ]
    levels = set(matching)
    return next(iter(levels)) if len(levels) == 1 else None


def _mentions_phrase(text: str, phrase: str) -> bool:
    """Match literal, complete keywords rather than incidental substrings.

    For example AI must not match 'paid', SQL must not match 'NoSQL', and
    Go must not match 'ongoing'. Spaces, slashes, hyphens and underscores
    can separate words in a multiword phrase. User text is always regex-
    escaped, preserving punctuation in phrases such as C++ and Node.js.
    """
    parts = phrase.split()
    if not parts:
        return False
    pattern = r"(?<!\w)" + r"[\s/_-]+".join(re.escape(part.casefold()) for part in parts) + r"(?!\w)"
    return re.search(pattern, text.casefold()) is not None

def _recognized_languages(value: str) -> frozenset[str]:
    """Recognize explicit language names/codes, not accidental substrings.

    Unknown language labels stay unknown; neither a score nor an employer
    qualification is inferred from the posting's body text.
    """
    tokens = set(re.findall(r"[^\W\d_]+", value.casefold(), re.UNICODE))
    return frozenset(
        name for name, aliases in LANGUAGE_LABELS.items() if tokens & aliases
    )


def _job_card(candidate: JobCandidate) -> dict[str, Any]:
    job = candidate.job
    return {
        "company": job.company, "role_title": job.role_title,
        # Browse categories reflect the published title only. They are
        # not qualification/experience or employer-permission claims.
        "career_area": career_area(job.role_title),
        "title_experience": title_experience(job.role_title),
        "location": job.location, "work_mode": job.work_mode,
        "language": job.language, "deadline": job.deadline,
        "application_url": job.application_url,
        "employer_sector": str(job.raw.get("employer_sector") or "unknown"),
        "source_ids": list(candidate.source_ids),
        "posted_at": candidate.posted_at, "first_seen_at": candidate.first_seen_at,
        "last_seen_at": candidate.last_seen_at, "source_current": candidate.source_current,
        "source_attribution": str(job.raw.get("source_attribution") or ""),
        "ai_preparation_allowed": job.raw.get("external_ai_forwarding_allowed") is not False,
    }


def _alignment(
    candidate: JobCandidate, pref: SearchPreferences,
) -> tuple[int, list[str], list[str], list[str], bool]:
    """Compare explicit search choices against observed job details.

    Missing information is unknown; an observed mismatch is never silently
    presented as a positive match. Neither result verifies qualifications.
    """
    job = candidate.job
    earned = 0.0
    weight = 0.0
    reasons: list[str] = []
    unknown: list[str] = []
    mismatches: list[str] = []
    role_fraction, target = _role_alignment(job.role_title, pref.roles)
    if pref.roles:
        weight += 60
        earned += 60 * role_fraction
        if role_fraction == 1:
            suffix = " (English/Finnish equivalent)" if _translated_role_match(job.role_title, target) else ""
            reasons.append(f"Job title matches {target}{suffix}")
        elif role_fraction > 0:
            reasons.append(f"Job title overlaps with {target}")

    if pref.locations:
        weight += 16
        place = job.location.casefold()
        if not place or place in {"remote", "anywhere", "unspecified", "not specified"}:
            unknown.append("Location not provided")
        elif any(_mentions_phrase(place, location) or _mentions_phrase(location, place)
                 for location in pref.locations):
            earned += 16
            reasons.append("Preferred location")
        else:
            mismatches.append("Location differs from preferred locations")

    if pref.work_modes:
        weight += 12
        if job.work_mode == "review":
            unknown.append("Work arrangement not stated")
        elif job.work_mode in pref.work_modes:
            earned += 12
            reasons.append("Preferred work arrangement")
        else:
            mismatches.append("Work arrangement differs from preferred arrangements")

    if pref.languages:
        weight += 6
        language = job.language.casefold()
        if not language:
            unknown.append("Job language not specified")
        elif not _recognized_languages(language):
            unknown.append("Job language label not recognized")
        elif _recognized_languages(language).intersection(pref.languages):
            earned += 6
            reasons.append("Preferred job language")
        else:
            mismatches.append("Advertised language differs from preferred languages")

    explicit_seniority_conflict = False
    inferred_title_level = (
        _explicit_target_title_level(job.role_title, pref.roles)
        if pref.seniority == "any" else None
    )
    chosen_level = pref.seniority if pref.seniority != "any" else inferred_title_level
    if chosen_level is not None and chosen_level != "any":
        weight += 6
        level = _seniority(job.role_title)
        if level is None:
            unknown.append("Experience level not specified")
        elif level == chosen_level:
            earned += 6
            reasons.append("Preferred experience level")
        else:
            explicit_seniority_conflict = True
            basis = (
                "experience preference" if pref.seniority != "any"
                else "experience level stated in your target job title"
            )
            mismatches.append(f"Listed {level} role differs from your {chosen_level} {basis}")

    matched_keywords: list[str] = []
    if pref.keywords:
        weight += 20
        searchable = (job.role_title + " " + job.description[:4000]).casefold()
        matched_keywords = [word for word in pref.keywords if _mentions_phrase(searchable, word)]
        earned += 20 * len(matched_keywords) / len(pref.keywords)
        if matched_keywords:
            reasons.append("Keywords: " + ", ".join(matched_keywords[:4]))

    if pref.skills:
        weight += 18
        job_body = (job.role_title + " " + job.description[:4000] + " " + " ".join(job.requirements)).casefold()
        matched_skills = [skill for skill in pref.skills if _mentions_phrase(job_body, skill)]
        earned += 18 * len(matched_skills) / len(pref.skills)
        if matched_skills:
            reasons.append("Your stated skills mentioned: " + ", ".join(matched_skills[:4]))

    score = round(100 * earned / weight) if weight else 0
    # Either a target title OR an explicit keyword can identify a promising
    # opportunity; previously titles wrongly overrode keyword matches.
    # An explicit experience-level conflict belongs in Explore more, but
    # must never hide the job from the user or pretend they are qualified.
    # One shared token in a two-word title (for example "Analyst" alone)
    # is too weak for the recommendation lane. Show weak overlaps in Explore.
    primary = (role_fraction >= 0.75 if pref.roles else False) or bool(matched_keywords)
    primary = bool(primary and not explicit_seniority_conflict)
    # An ad for a driver may mention Python, data or apps in its BODY.
    # Such an incidental keyword must not promote the unrelated title
    # when the user's explicit role targets are IT / planning roles.
    # Preserve it in Explore more, and respect searches that explicitly
    # target careers outside IT / planning.
    focused_target = any(
        career_area(role) != "other" for role in pref.roles
    )
    if focused_target and career_area(job.role_title) == "other":
        primary = False
        if matched_keywords:
            mismatches.append("Job title is outside your IT or planning career targets")
    return max(0, min(100, score)), reasons, unknown, mismatches, primary

def _published_order(candidate: JobCandidate) -> tuple[float, float, str]:
    """Order by genuine posting/discovery date, NOT by a poll's last-seen time.

    All feed items refreshed in one worker poll otherwise look equally new
    and general search becomes an arbitrary canonical-key ordering.
    """
    def unix(value: str) -> float:
        if not value:
            return 0.0
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (ValueError, OverflowError, TypeError):
            return 0.0

    return (
        unix(candidate.posted_at) or unix(candidate.first_seen_at),
        unix(candidate.first_seen_at), candidate.canonical_key,
    )


def search_jobs(candidates: Sequence[JobCandidate], pref: SearchPreferences) -> dict[str, Any]:
    current = [item for item in candidates if item.source_current]
    current.sort(key=_published_order, reverse=True)
    if not pref.completed:
        return {
            "mode": "setup_required", "completed": False,
            "recommendations": [], "broader": [], "all_jobs": [],
            "available_count": len(current), "score_kind": "none",
        }
    if pref.mode == "general":
        return {
            "mode": "general", "completed": True, "recommendations": [],
            "broader": [], "all_jobs": [
                {"canonical_key": j.canonical_key, "job": _job_card(j),
                 "preference_score": None, "reasons": [], "unknown_fields": [],
                 "mismatched_fields": [], "lane": "all"} for j in current
            ],
            "available_count": len(current), "score_kind": "none",
        }

    ranked: list[tuple[int, bool, JobCandidate, list[str], list[str], list[str]]] = []
    for candidate in current:
        score, reasons, unknown, mismatches, primary = _alignment(candidate, pref)
        ranked.append((score, primary, candidate, reasons, unknown, mismatches))
    ranked.sort(key=lambda x: (x[0], _published_order(x[2])), reverse=True)

    def cards(group: list[tuple[int, bool, JobCandidate, list[str], list[str], list[str]]], lane: str) -> list[dict[str, Any]]:
        return [{
            "canonical_key": candidate.canonical_key,
            "job": _job_card(candidate),
            "preference_score": score,
            "reasons": reasons,
            "unknown_fields": unknown,
            "mismatched_fields": mismatches,
            "lane": lane,
        } for score, _, candidate, reasons, unknown, mismatches in group]

    top = [item for item in ranked if item[1]]
    broader = [item for item in ranked if not item[1]]
    return {
        "mode": "personalized", "completed": True,
        "recommendations": cards(top, "recommended"),
        "broader": cards(broader, "broader"),
        "all_jobs": [], "available_count": len(current),
        "score_kind": "preference_alignment_not_verified_qualification",
    }

"""Complete, deterministic Finnish/English application-letter drafts.

The current CV-first workspace still starts with the legacy review-marked
template. This module is used only by the explicit, revision-checked
letter-proposal action: a completed text is not an employer submission or a
review/approval token. Source requirements are NEVER instructions to the
composer, and only job-matched approved evidence can become candidate claims.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .domain import JobCandidate
from .profile import CandidateProfile, ProfileFact
from .scoring import score_candidate

Language = Literal["fi", "en"]

_PRIORITY = {
    "skill": 0,
    "experience": 1,
    "project": 2,
    "certification": 3,
    "education": 4,
    "domain": 5,
    "language": 6,
}
_MAX_FACT_LENGTH = 260


@dataclass(frozen=True)
class CompletedLetter:
    text: str
    language: Language
    complete: bool
    evidence_fact_ids: tuple[str, ...]
    missing_information: tuple[str, ...]
    review_notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "cover_letter": self.text,
            "language": self.language,
            "complete": self.complete,
            "evidence_fact_ids": list(self.evidence_fact_ids),
            "missing_information": list(self.missing_information),
            "review_notes": list(self.review_notes),
        }


def _display(value: str, fallback: str) -> str:
    """Keep user-visible job metadata bounded; never use its body as a command."""
    result = re.sub(r"\s+", " ", str(value or "")).strip()
    return result[:150] or fallback


def _join(values: list[str], language: Language) -> str:
    if len(values) == 1:
        return values[0]
    conjunction = " ja " if language == "fi" else " and "
    return ", ".join(values[:-1]) + conjunction + values[-1]


def _sentence(kind: str, values: list[str], language: Language) -> str:
    """Use the ORIGINAL facts rather than adding invented duration or impact."""
    label = {
        "en": {
            "skill": "My relevant skills include",
            "experience": "My professional experience includes",
            "project": "My project work includes",
            "certification": "My certifications include",
            "education": "My educational background includes",
            "domain": "My areas of expertise include",
            "language": "My language skills include",
        },
        "fi": {
            "skill": "Tehtävään liittyvään osaamiseeni kuuluu",
            "experience": "Työkokemukseeni kuuluu",
            "project": "Olen työskennellyt projekteissa, joihin kuuluu",
            "certification": "Sertifikaatteihini kuuluu",
            "education": "Koulutukseeni kuuluu",
            "domain": "Erityisosaamiseeni kuuluu",
            "language": "Kielitaitooni kuuluu",
        },
    }[language][kind]
    # Facts may already contain punctuation; do not cut or reinterpret them.
    original = _join(values, language).rstrip()
    return label + " " + original + ("" if original.endswith((".", "!", "?")) else ".")


def compose_completed_letter(
    candidate: JobCandidate,
    profile: CandidateProfile,
    *,
    language: Language,
) -> CompletedLetter:
    """Produce real letter prose or an explicitly incomplete, editable draft.

    No model, employer request, user document write or profile mutation occurs.
    No facts are copied from employer instructions or unapproved CV text.
    """
    if language not in {"fi", "en"}:
        raise ValueError("Letter language must be fi or en")

    matched_ids = set(score_candidate(candidate, profile).matched_evidence_ids)
    eligible: list[ProfileFact] = [
        fact for fact in profile.approved_facts
        if fact.fact_type in _PRIORITY
        and fact.fact_id in matched_ids
        and 1 <= len(fact.value) <= _MAX_FACT_LENGTH
    ]
    eligible.sort(key=lambda fact: (_PRIORITY[fact.fact_type], fact.fact_id))
    # A convincing letter must not bury the applicant's actual project or
    # experience behind three unrelated skills. Keep the original matched
    # evidence, with bounded diversity and no invented achievements.
    selected: list[ProfileFact] = []
    caps = {"skill": 3, "experience": 2, "project": 2,
            "certification": 1, "education": 1, "domain": 1, "language": 1}
    counts: dict[str, int] = {}
    # Prefer demonstrated work and projects when present; the final prose
    # keeps a natural skill -> example -> qualification structure.
    for kind in ("experience", "project", "skill", "education",
                 "certification", "domain", "language"):
        for fact in eligible:
            if fact.fact_type != kind or counts.get(kind, 0) >= caps[kind]:
                continue
            if len(selected) >= 7:
                break
            selected.append(fact)
            counts[kind] = counts.get(kind, 0) + 1
    used = selected
    names = sorted({
        fact.value.strip() for fact in profile.approved_facts
        if fact.fact_type == "identity" and fact.value.strip()
    })
    name = names[0] if len(names) == 1 else ""
    role = _display(candidate.job.role_title, "the advertised role" if language == "en" else "avoin tehtävä")
    company = _display(candidate.job.company, "your organisation" if language == "en" else "organisaationne")

    missing: list[str] = []
    if not used:
        missing.append(
            "Confirm a role-relevant skill, project or experience example."
            if language == "en" else
            "Vahvista tehtävään liittyvä taito, projekti tai työkokemusesimerkki."
        )
    if not name:
        missing.append(
            "Confirm one full name for the signature."
            if language == "en" else
            "Vahvista yksi koko nimi allekirjoitusta varten."
        )

    grouped: dict[str, list[str]] = {}
    for fact in used:
        grouped.setdefault(fact.fact_type, []).append(fact.value)

    # Don't turn a list of approved facts into an invented employment history.
    # Group the applicant's actual words into short, readable paragraphs.
    skill_kinds = ("skill", "domain", "language")
    example_kinds = ("experience", "project")
    qualification_kinds = ("education", "certification")
    def paragraph(kinds: tuple[str, ...]) -> str:
        return " ".join(
            _sentence(kind, grouped[kind], language)
            for kind in kinds if kind in grouped
        )

    skills = paragraph(skill_kinds)
    examples = paragraph(example_kinds)
    qualifications = paragraph(qualification_kinds)
    if language == "fi":
        paragraphs = [
            "Hei rekrytointitiimi,",
            f"Haen tehtävää {role} organisaatiossa {company}. "
            "Haluaisin hyödyntää osaamistani tässä tehtävässä ja "
            "kehittää sitä osana tiimiänne.",
        ]
        if skills:
            paragraphs.append(skills)
        if examples:
            paragraphs.append(examples)
        if qualifications:
            paragraphs.append(qualifications)
        paragraphs.append(
            "Kuulisin mielelläni lisää tehtävän tavoitteista ja kertoisin, "
            "miten voisin hyödyntää tätä osaamista työssänne. "
            "Kiitos ajastanne ja hakemukseni käsittelystä."
        )
        paragraphs.append("Ystävällisin terveisin,\n" + name if name else "Ystävällisin terveisin,")
    else:
        paragraphs = [
            "Dear Hiring Team,",
            f"I am applying for the {role} position at {company}. "
            "I am interested in the opportunity to put my relevant "
            "background to work and continue developing with your team.",
        ]
        if skills:
            paragraphs.append(skills)
        if examples:
            paragraphs.append(examples)
        if qualifications:
            paragraphs.append(qualifications)
        paragraphs.append(
            "I would welcome the opportunity to discuss the role's priorities "
            "and how I could put these strengths to work. "
            "Thank you for considering my application."
        )
        paragraphs.append("Kind regards,\n" + name if name else "Kind regards,")

    return CompletedLetter(
        text="\n\n".join(paragraphs),
        language=language,
        complete=not missing,
        evidence_fact_ids=tuple(fact.fact_id for fact in used),
        missing_information=tuple(missing),
        review_notes=(
            "Only approved facts matched to the job are quoted. No achievements, years, or employer interest were invented.",
            "For a more distinctive letter, add a verified project outcome and your personal reason for applying.",
            "Review, edit and explicitly save before using this letter. No employer has been contacted.",
        ),
    )

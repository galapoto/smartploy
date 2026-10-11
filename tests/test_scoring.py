from datetime import datetime, timezone

from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.scoring import _concepts, rank_candidates, score_candidate


def candidate(posted_at="2026-10-10T01:00:00+00:00", mandatory=("Python", "SQL")):
    result = normalize_observation(
        SourceObservation(
            source_id="kuntarekry",
            source_mode="feed",
            source_url="https://www.kuntarekry.fi/fi/tyopaikat/data-analyst-42/",
            raw_text="Data Analyst Python SQL Power BI",
            payload={
                "company": "Example City",
                "role_title": "Junior Data Analyst",
                "description": "Data analysis with Python, SQL and Power BI",
                "location": "Helsinki",
                "work_mode": "hybrid",
                "language": "Finnish, English",
                "requirements": list(mandatory),
                "nice_to_have": ["Power BI"],
                "application_url": "https://www.kuntarekry.fi/fi/tyopaikat/data-analyst-42/",
                "sector": "Technology",
                "seniority": "junior",
            },
            observed_at="2026-10-10T01:00:00+00:00",
            posted_at=posted_at,
        ),
        SourcePolicy("kuntarekry", "Kuntarekry", "public_sector_jobs", ("feed",)),
    )
    assert result.candidate is not None
    return result.candidate


def profile(include_power_bi=False):
    facts = [
        ProfileFact("skill", "Python", "cv", approved=True),
        ProfileFact("skill", "SQL", "cv", approved=True),
        ProfileFact("language", "Finnish", "confirmed", approved=True),
        ProfileFact("language", "English", "confirmed", approved=True),
        ProfileFact("location", "Helsinki", "confirmed", approved=True, tags=("location",)),
        ProfileFact("preference", "hybrid", "confirmed", approved=True, tags=("work_mode",)),
        ProfileFact("preference", "junior", "confirmed", approved=True, tags=("seniority",)),
        ProfileFact("preference", "Data Analyst", "confirmed", approved=True, tags=("role", "career")),
        ProfileFact("domain", "data analytics", "cv", approved=True),
        ProfileFact("skill", "Power BI", "note", approved=include_power_bi),
    ]
    return CandidateProfile(facts=tuple(facts))


def test_fit_distinguishes_mandatory_and_preferred_and_ignores_unapproved():
    result = score_candidate(
        candidate(),
        profile(include_power_bi=False),
        now=datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc),
    )
    assert result.fit_breakdown["mandatory_requirements"] == 100
    assert result.fit_breakdown["preferred_requirements"] == 0
    assert result.mandatory_gaps == ()
    assert result.preferred_gaps == ("Power BI",)
    assert all("power" not in item.casefold() for item in result.matched_evidence_ids)


def test_missing_mandatory_requirement_blocks_auto_prepare():
    result = score_candidate(
        candidate(mandatory=("Python", "SQL", "Azure")),
        profile(),
        now=datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc),
    )
    assert "Azure" in result.mandatory_gaps
    assert result.queue not in {"exceptional", "auto_prepare"}
    assert result.prepare_recommended is False


def test_freshness_changes_priority_not_fit():
    now = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
    fresh = candidate("2026-10-10T01:00:00+00:00")
    stale = candidate("2026-09-20T01:00:00+00:00")
    fresh_score = score_candidate(fresh, profile(), now=now)
    stale_score = score_candidate(stale, profile(), now=now)
    assert fresh_score.fit_score == stale_score.fit_score
    assert fresh_score.priority_score > stale_score.priority_score


def test_rank_candidates_uses_priority_then_fit():
    now = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
    fresh = candidate("2026-10-10T01:00:00+00:00")
    stale = candidate("2026-09-20T01:00:00+00:00")
    ranked = rank_candidates([stale, fresh], profile(), now=now)
    assert ranked[0].priority_score >= ranked[1].priority_score


def test_skill_aliases_use_word_boundaries_not_incidental_substrings():
    assert "sql" not in _concepts("NoSQL databases")
    assert "python" not in _concepts("pythonic style")
    assert "sql" in _concepts("SQL / Python")
    assert "python" in _concepts("SQL / Python")
    assert "power_bi" in _concepts("Power-BI dashboard")

    only_nosql = CandidateProfile(facts=(
        ProfileFact("skill", "NoSQL", "cv", approved=True),
    ))
    result = score_candidate(candidate(mandatory=("SQL",)), only_nosql)
    assert result.mandatory_gaps == ("SQL",)
    assert result.prepare_recommended is False
    assert result.fit_breakdown["mandatory_requirements"] == 0


def test_higher_degree_requirement_cannot_be_fulfilled_by_bachelor_or_unrelated_skills():
    requirement = "Master's degree in Data Science"
    bachelor = CandidateProfile(facts=(
        ProfileFact("education", "Bachelor of Science in Data Science", "cv", approved=True),
        ProfileFact("skill", "Data Science", "cv", approved=True),
        ProfileFact("experience", "Data Science projects", "cv", approved=True),
    ))
    result = score_candidate(candidate(mandatory=(requirement,)), bachelor)
    assert result.mandatory_gaps == (requirement,)
    assert result.prepare_recommended is False
    assert result.queue not in {"exceptional", "auto_prepare"}


def test_degree_qualification_requires_same_level_and_field_in_one_approved_fact():
    requirement = "Master's degree in Data Science"
    unrelated = CandidateProfile(facts=(
        ProfileFact("education", "MSc in Business Administration", "cv", approved=True),
        ProfileFact("education", "Bachelor in Data Science", "cv", approved=True),
    ))
    unrelated_result = score_candidate(candidate(mandatory=(requirement,)), unrelated)
    assert unrelated_result.mandatory_gaps == (requirement,)

    correct = CandidateProfile(facts=(
        ProfileFact("education", "MSc in Data Science", "cv", approved=True),
    ))
    valid_result = score_candidate(candidate(mandatory=(requirement,)), correct)
    assert valid_result.mandatory_gaps == ()
    assert valid_result.matched_requirements == (requirement,)
    assert len(valid_result.matched_evidence_ids) >= 1

    unapproved = CandidateProfile(facts=(
        ProfileFact("education", "MSc in Data Science", "unreviewed", approved=False),
    ))
    unavailable = score_candidate(candidate(mandatory=(requirement,)), unapproved)
    assert unavailable.mandatory_gaps == (requirement,)
    assert unavailable.prepare_recommended is False


def test_degree_guard_does_not_confuse_skill_mastery_with_a_degree():
    # "Master Python scripts" is a skill phrase, not an MSc credential.
    from smartploy.scoring import _degree_level
    assert _degree_level("Master Python scripts") is None
    assert _degree_level("Master's degree in Data Science") == "master"
    assert _degree_level("M.Sc. Data Science") == "master"
    assert _degree_level("Bachelor in Nursing") == "bachelor"
    assert _degree_level("PhD in Physics") == "doctorate"

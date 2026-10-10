from datetime import datetime, timezone

from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.scoring import rank_candidates, score_candidate


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

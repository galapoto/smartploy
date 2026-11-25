from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation


def test_employer_sector_is_explicit_and_unknown_is_not_guessed():
    private = normalize_observation(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Oy Data Analyst",
            payload={
                "company": "Example Oy",
                "role_title": "Data Analyst",
                "employer_sector": "private",
            },
            observed_at="2026-10-10T00:00:00+00:00",
        ),
        SourcePolicy("manual", "Manual", "manual", ("manual",)),
    )
    unknown = normalize_observation(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Organisation Analyst",
            payload={
                "company": "Example Organisation",
                "role_title": "Analyst",
            },
            observed_at="2026-10-10T00:00:00+00:00",
        ),
        SourcePolicy("manual", "Manual", "manual", ("manual",)),
    )

    assert private.candidate is not None
    assert unknown.candidate is not None
    assert private.candidate.job.raw["employer_sector"] == "private"
    assert unknown.candidate.job.raw["employer_sector"] == "unknown"


def test_dashboard_projects_only_bounded_cards_from_one_ranked_snapshot(monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import Mock

    from smartploy.service import SmartployService

    normalized = normalize_observation(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Oy Data Analyst",
            payload={"company": "Example Oy", "role_title": "Data Analyst"},
            observed_at="2026-10-10T00:00:00+00:00",
        ),
        SourcePolicy("manual", "Manual", "manual", ("manual",)),
    )
    assert normalized.candidate is not None
    candidates = [
        replace(normalized.candidate, canonical_key=f"synthetic-{index}")
        for index in range(1200)
    ]
    scores = [
        SimpleNamespace(
            canonical_key=candidate.canonical_key,
            queue="review" if index < 600 else "possible",
            to_dict=lambda candidate=candidate: {"canonical_key": candidate.canonical_key},
        )
        for index, candidate in enumerate(candidates)
    ]
    rank = Mock(return_value=scores)
    monkeypatch.setattr("smartploy.service.rank_candidates", rank)
    service = SmartployService()
    ledger = Mock(return_value=candidates)
    lookup = Mock(side_effect=AssertionError("Unexpected individual job lookup"))
    monkeypatch.setattr(service, "list_jobs", ledger)
    monkeypatch.setattr(service, "get_job", lookup)

    dashboard = service.dashboard()

    ledger.assert_called_once_with()
    lookup.assert_not_called()
    rank.assert_called_once()
    assert rank.call_args.args[0] is candidates
    assert [row["canonical_key"] for row in dashboard["top_matches"]] == [
        f"synthetic-{index}" for index in range(50)
    ]
    assert [row["canonical_key"] for row in dashboard["possible_matches"]] == [
        f"synthetic-{index}" for index in range(600, 700)
    ]
    assert all(
        row["job"]["company"] == "Example Oy"
        for row in dashboard["top_matches"] + dashboard["possible_matches"]
    )
    assert dashboard["external_actions_authorized"] is False



def test_lightweight_dashboard_never_reads_or_ranks_job_catalogue(monkeypatch):
    from unittest.mock import Mock

    from smartploy.service import SmartployService

    service = SmartployService()
    read = Mock(side_effect=AssertionError("startup must not read the full catalogue"))
    rank = Mock(side_effect=AssertionError("startup must not rank the catalogue"))
    monkeypatch.setattr(service, "list_jobs", read)
    monkeypatch.setattr("smartploy.service.rank_candidates", rank)

    result = service.dashboard(include_rankings=False)

    read.assert_not_called()
    rank.assert_not_called()
    assert result["rankings_loaded"] is False
    assert result["top_matches"] == []
    assert result["possible_matches"] == []
    assert result["external_actions_authorized"] is False
    assert "applications" in result
    assert "profile" in result

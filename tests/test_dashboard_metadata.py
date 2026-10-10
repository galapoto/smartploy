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

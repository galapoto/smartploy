from smartploy.domain import (
    JobDiscoveryIndex,
    JobSearchFilters,
    SourceObservation,
    SourcePolicy,
    canonicalize_url,
    normalize_observation,
)


def policies():
    return (
        SourcePolicy(
            source_id="company-careers",
            display_name="Company Careers",
            source_class="company_careers",
            allowed_modes=("feed", "api"),
        ),
        SourcePolicy(
            source_id="verified-search",
            display_name="Verified Search",
            source_class="verified_search",
            allowed_modes=("search",),
        ),
    )


def payload():
    return {
        "company": "Example Oy",
        "role_title": "Junior Data Analyst",
        "description": "Analyse data with Python and SQL. Build reports for business teams.",
        "location": "Helsinki, Finland",
        "work_mode": "hybrid",
        "language": "Finnish, English",
        "requirements": ["Python", "SQL"],
        "nice_to_have": ["Power BI"],
        "application_url": "https://jobs.example.fi/roles/42?utm_campaign=jobs",
        "sector": "Technology",
        "seniority": "junior",
        "salary_min_eur": 3200,
    }


def observation(source_id, source_mode, source_url, observed_at, data=None):
    return SourceObservation(
        source_id=source_id,
        source_mode=source_mode,
        source_url=source_url,
        raw_text="Example Oy Junior Data Analyst Python SQL Helsinki",
        payload=data or payload(),
        observed_at=observed_at,
        posted_at="2026-10-09T12:00:00+00:00",
        source_external_id="42",
    )


def test_canonical_url_removes_tracking_and_rejects_bad_port():
    assert (
        canonicalize_url("https://jobs.example.fi/roles/42/?utm_source=test&gclid=x#apply")
        == "https://jobs.example.fi/roles/42"
    )
    assert canonicalize_url("https://jobs.example.fi:not-a-port/roles/42") == ""


def test_cross_source_dedupe_and_freshness():
    company, aggregator = policies()
    first = observation(
        "company-careers",
        "feed",
        "https://jobs.example.fi/roles/42?utm_source=feed",
        "2026-10-10T00:00:00+00:00",
    )
    second_data = {**payload(), "application_url": "https://search.example.net/result/9001?ref=board"}
    second = observation(
        "verified-search",
        "search",
        "https://search.example.net/result/9001?utm_medium=listing",
        "2026-10-10T02:00:00+00:00",
        second_data,
    )

    left = normalize_observation(first, company)
    right = normalize_observation(second, aggregator)
    assert left.discovered and right.discovered
    assert left.candidate is not None and right.candidate is not None
    assert left.candidate.canonical_key == right.candidate.canonical_key

    filters = JobSearchFilters(
        sectors=("technology",),
        languages=("finnish",),
        locations=("helsinki",),
        work_modes=("hybrid",),
        seniority=("junior",),
        minimum_salary_eur=3000,
        include_unknown=False,
    )
    index = JobDiscoveryIndex()
    one = index.ingest(first, company, filters)
    assert one.discovered and one.candidate is not None
    two = index.ingest(second, aggregator, filters)
    assert two.discovered and two.candidate is not None

    merged = two.candidate
    assert merged.first_seen_at == "2026-10-10T00:00:00+00:00"
    assert merged.last_seen_at == "2026-10-10T02:00:00+00:00"
    assert set(merged.source_ids) == {"company-careers", "verified-search"}
    assert len(index.values()) == 1


def test_raw_hash_changes_only_when_raw_content_changes():
    company, _ = policies()
    first = observation(
        "company-careers",
        "feed",
        "https://jobs.example.fi/roles/42?utm_source=a",
        "2026-10-10T00:00:00+00:00",
    )
    again = observation(
        "company-careers",
        "feed",
        "https://jobs.example.fi/roles/42?utm_source=b",
        "2026-10-10T01:00:00+00:00",
    )
    changed = SourceObservation(
        **{**first.__dict__, "raw_text": first.raw_text + " changed"}
    )
    assert first.raw_sha256 == again.raw_sha256
    assert first.raw_sha256 != changed.raw_sha256
    assert normalize_observation(first, company).discovered


def test_hard_filter_and_blocked_policy_fail_closed():
    company, _ = policies()
    first = observation(
        "company-careers",
        "feed",
        "https://jobs.example.fi/roles/42",
        "2026-10-10T00:00:00+00:00",
    )
    index = JobDiscoveryIndex()
    filtered = index.ingest(
        first,
        company,
        JobSearchFilters(locations=("tampere",), include_unknown=False),
    )
    assert filtered.status == "filtered"

    blocked_policy = SourcePolicy(
        source_id="company-careers",
        display_name="Company Careers",
        source_class="company_careers",
        allowed_modes=("feed",),
        terms_review_status="blocked",
    )
    blocked = normalize_observation(first, blocked_policy)
    assert blocked.status == "blocked"


def test_closed_job_handoff_never_authorizes_external_action():
    company, _ = policies()
    first = observation(
        "company-careers",
        "feed",
        "https://jobs.example.fi/roles/42",
        "2026-10-10T00:00:00+00:00",
    )
    index = JobDiscoveryIndex()
    result = index.ingest(first, company)
    assert result.candidate is not None
    closed = index.mark_closed(result.candidate.canonical_key, closed_at="2026-10-10T03:00:00+00:00")
    handoff = closed.to_obumai_handoff()
    assert handoff["status"] == "blocked_source_not_current"
    assert handoff["authority"]["may_upload"] is False
    assert handoff["authority"]["may_submit"] is False
    assert handoff["authority"]["external_action_authorized"] is False

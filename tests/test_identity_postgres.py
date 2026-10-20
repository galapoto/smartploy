import os

import pytest
from psycopg import connect

from smartploy.application_storage import PostgresApplicationRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import (
    AuthenticatedPrincipal,
    PostgresIdentityRepository,
    stable_profile_id,
    stable_user_id,
)
from smartploy.preparation_storage import PostgresPreparationRepository
from smartploy.preparations import build_preparation
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.scoring import ScoreResult
from smartploy.storage import PostgresJobRepository


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="SMARTPLOY_TEST_DATABASE_URL not configured")


@pytest.fixture()
def clean_db():
    jobs = PostgresJobRepository(DSN)
    jobs.migrate()
    with connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE smartploy_autodraft_settings,
                         smartploy_oidc_state,
                         smartploy_sessions,
                         smartploy_application_events,
                         smartploy_applications,
                         smartploy_application_preparations,
                         smartploy_source_observations,
                         smartploy_source_health,
                         smartploy_profile_facts,
                         smartploy_user_profiles,
                         smartploy_user_identities,
                         smartploy_users,
                         smartploy_jobs
                RESTART IDENTITY
                """
            )
        conn.commit()
    return jobs


def principal(subject: str, email: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer="https://auth.obumai.com",
        subject=subject,
        email=email,
        auth_source="oidc",
    )


def candidate(jobs: PostgresJobRepository):
    normalized = normalize_observation(
        SourceObservation(
            source_id="manual",
            source_mode="manual",
            source_url="",
            raw_text="Example Data Analyst Python SQL",
            payload={
                "company": "Example Oy",
                "role_title": "Data Analyst",
                "description": "Python SQL analytics",
                "requirements": ["Python", "SQL"],
            },
            observed_at="2026-10-10T08:00:00+00:00",
        ),
        SourcePolicy("manual", "Manual", "manual", ("manual",)),
    )
    assert normalized.candidate is not None
    return jobs.upsert(normalized.candidate)


def score_for(canonical_key: str, evidence_id: str) -> ScoreResult:
    return ScoreResult(
        canonical_key=canonical_key,
        fit_score=92,
        priority_score=91,
        queue="auto_prepare",
        fit_breakdown={"skill_overlap": 100},
        priority_breakdown={"fit": 92},
        matched_evidence_ids=(evidence_id,),
        matched_requirements=("Python",),
        mandatory_gaps=(),
        preferred_gaps=(),
        prepare_recommended=True,
    )


def test_two_principals_get_distinct_stable_user_and_profile_ids(clean_db):
    identities = PostgresIdentityRepository(DSN)
    one = identities.resolve_or_create(principal("sub-one", "one@example.com"))
    two = identities.resolve_or_create(principal("sub-two", "two@example.com"))

    assert one.user_id == stable_user_id("https://auth.obumai.com", "sub-one")
    assert one.profile_id == stable_profile_id(one.user_id)
    assert two.user_id == stable_user_id("https://auth.obumai.com", "sub-two")
    assert two.profile_id == stable_profile_id(two.user_id)
    assert one.user_id != two.user_id
    assert one.profile_id != two.profile_id

    again = identities.resolve_or_create(principal("sub-one", "updated@example.com"))
    assert again.user_id == one.user_id
    assert again.profile_id == one.profile_id
    assert again.email == "updated@example.com"


def test_explicit_identity_alias_keeps_same_smartploy_user_and_profile(clean_db):
    identities = PostgresIdentityRepository(DSN)
    access_principal = AuthenticatedPrincipal(
        issuer="https://example.cloudflareaccess.com",
        subject="cloudflare-subject",
        email="owner@example.com",
        auth_source="cloudflare_access",
    )
    oidc_principal = AuthenticatedPrincipal(
        issuer="https://auth.obumai.com",
        subject="obum-user-subject",
        email="owner@example.com",
        auth_source="oidc",
    )

    original = identities.resolve_or_create(access_principal)
    linked = identities.link_identity(original.user_id, oidc_principal)
    resolved_again = identities.resolve_or_create(oidc_principal)

    assert linked.user_id == original.user_id
    assert linked.profile_id == original.profile_id
    assert resolved_again.user_id == original.user_id
    assert resolved_again.profile_id == original.profile_id

    other = identities.resolve_or_create(
        AuthenticatedPrincipal(
            issuer="https://auth.obumai.com",
            subject="other-user",
            email="other@example.com",
            auth_source="oidc",
        )
    )
    with pytest.raises(ValueError, match="already linked"):
        identities.link_identity(other.user_id, oidc_principal)


def test_profile_facts_are_isolated_by_resolved_profile(clean_db):
    identities = PostgresIdentityRepository(DSN)
    one = identities.resolve_or_create(principal("sub-one", "one@example.com"))
    two = identities.resolve_or_create(principal("sub-two", "two@example.com"))

    repo_one = PostgresProfileRepository(DSN, profile_id=one.profile_id)
    repo_two = PostgresProfileRepository(DSN, profile_id=two.profile_id)

    repo_one.upsert_fact(ProfileFact("skill", "Python", "cv-one", approved=True))
    repo_two.upsert_fact(ProfileFact("skill", "SQL", "cv-two", approved=True))

    assert [fact.value for fact in repo_one.list_facts()] == ["Python"]
    assert [fact.value for fact in repo_two.list_facts()] == ["SQL"]


def test_same_job_has_independent_preparations_and_applications_per_profile(clean_db):
    jobs = clean_db
    identities = PostgresIdentityRepository(DSN)
    one = identities.resolve_or_create(principal("sub-one", "one@example.com"))
    two = identities.resolve_or_create(principal("sub-two", "two@example.com"))
    job = candidate(jobs)

    shared_fact = ProfileFact("skill", "Python", "verified-cv", approved=True).normalized()
    profile_one = CandidateProfile(profile_id=one.profile_id, facts=(shared_fact,))
    profile_two = CandidateProfile(profile_id=two.profile_id, facts=(shared_fact,))

    prep_one = build_preparation(
        job,
        profile_one,
        score_for(job.canonical_key, shared_fact.fact_id),
        requested_at="2026-10-10T09:00:00+00:00",
    )
    prep_two = build_preparation(
        job,
        profile_two,
        score_for(job.canonical_key, shared_fact.fact_id),
        requested_at="2026-10-10T09:00:00+00:00",
    )

    assert prep_one.package_id != prep_two.package_id

    preps_one = PostgresPreparationRepository(DSN, profile_id=one.profile_id)
    preps_two = PostgresPreparationRepository(DSN, profile_id=two.profile_id)
    stored_one, created_one = preps_one.create_or_get(prep_one)
    stored_two, created_two = preps_two.create_or_get(prep_two)
    assert created_one is True
    assert created_two is True

    apps_one = PostgresApplicationRepository(DSN, profile_id=one.profile_id)
    apps_two = PostgresApplicationRepository(DSN, profile_id=two.profile_id)
    app_one = apps_one.sync_preparation(stored_one)
    app_two = apps_two.sync_preparation(stored_two)

    assert app_one.application_id != app_two.application_id
    assert app_one.canonical_key == app_two.canonical_key
    assert app_one.profile_id == one.profile_id
    assert app_two.profile_id == two.profile_id

    assert apps_one.get(app_two.application_id) is None
    assert apps_two.get(app_one.application_id) is None
    assert preps_one.get(prep_two.package_id) is None
    assert preps_two.get(prep_one.package_id) is None

    assert [item.application_id for item in apps_one.list()] == [app_one.application_id]
    assert [item.application_id for item in apps_two.list()] == [app_two.application_id]
    assert len(apps_one.events(app_two.application_id)) == 0
    assert len(apps_two.events(app_one.application_id)) == 0


def test_legacy_default_profile_is_not_auto_claimed_and_claim_is_one_time(clean_db):
    default_repo = PostgresProfileRepository(DSN, profile_id="default")
    default_repo.upsert_fact(
        ProfileFact("skill", "Legacy Python", "legacy-cv", approved=True)
    )

    identities = PostgresIdentityRepository(DSN)
    one_principal = principal("sub-one", "one@example.com")
    two_principal = principal("sub-two", "two@example.com")

    one = identities.resolve_or_create(one_principal)
    assert one.profile_id != "default"
    assert PostgresProfileRepository(DSN, profile_id=one.profile_id).list_facts() == []
    assert [fact.value for fact in default_repo.list_facts()] == ["Legacy Python"]

    claimed = identities.claim_legacy_profile(one_principal)
    assert claimed.profile_id == "default"
    assert [fact.value for fact in PostgresProfileRepository(DSN, profile_id=claimed.profile_id).list_facts()] == [
        "Legacy Python"
    ]

    identities.resolve_or_create(two_principal)
    with pytest.raises(ValueError, match="already claimed"):
        identities.claim_legacy_profile(two_principal)

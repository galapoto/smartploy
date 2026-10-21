"""SP15j: automatic per-account IT discovery and LOCAL application drafts.

Tests use original SmartPloy matching, evidence, CV and workspace products.
No network, ObumAI or employer final-submit engine is mocked in or invoked.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest

from smartploy.auto_draft_shortlist import prepare_profile_shortlist
from smartploy.application_workspace_storage import MemoryWorkspaceRepository, PostgresWorkspaceRepository
from smartploy.cv_storage import MemoryCVRepository, PostgresCVRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.profile import ProfileFact
from smartploy.profile_storage import MemoryProfileRepository, PostgresProfileRepository
from smartploy.search_preferences import SearchPreferenceError
from smartploy.search_preference_storage import (
    MemorySearchPreferenceRepository, PostgresSearchPreferenceRepository,
)
from smartploy.storage import MemoryJobRepository, PostgresJobRepository


def candidate(title: str, *, url: str = "", requirements: list[str] | None = None):
    slug = title.casefold().replace(" ", "-")
    href = url or "https://careers.example.fi/jobs/" + slug
    observed = normalize_observation(
        SourceObservation(
            source_id="lever-global-synthetic-firm", source_mode="api",
            source_url=href, raw_text=title + " vacancy",
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            payload={
                "company":"Synthetic Employer", "role_title":title,
                "description":"Python data analysis and SQL business reporting",
                "location":"Helsinki","application_url":href,
                "requirements":requirements or [],
            },
        ),
        SourcePolicy("lever-global-synthetic-firm", "Synthetic ATS",
                     "direct_employer_ats", ("api",)),
    )
    assert observed.candidate
    return observed.candidate


def fixture():
    owner = "synthetic-it-user"
    prefs = MemorySearchPreferenceRepository()
    repo = MemoryJobRepository()
    profile = MemoryProfileRepository(profile_id=owner)
    for skill in ("Python", "SQL", "data analysis"):
        profile.upsert_fact(ProfileFact(
            "skill", skill, "user-entered", approved=True
        ))
    cv = MemoryCVRepository()
    spaces = MemoryWorkspaceRepository()
    pref_payload = {
        "mode":"personalized", "roles":["Data Analyst"], "locations":[],
        "languages":[], "work_modes":[], "skills":[], "keywords":[],
        "seniority":"any", "auto_draft_enabled":True,
    }
    prefs.save(owner,pref_payload,expected_revision=0)
    for j in (candidate("Junior Data Analyst"),candidate("Senior Marketing Manager")):
        repo.upsert(j)
    return owner,prefs,repo,profile,cv,spaces,pref_payload


def run_local(f):
    pid,prefs,jobs,profile,cv,spaces,_=f
    return prepare_profile_shortlist(
        pid,preferences_repository=prefs,job_repository=jobs,
        profile_repository=profile,cv_repository=cv,workspace_repository=spaces,
    )


def test_explicit_approved_it_target_automatically_builds_only_the_matched_private_draft():
    fx = fixture()
    outcome = run_local(fx)
    assert outcome.status == "prepared"
    assert outcome.created == 1
    assert outcome.checked == 1
    assert outcome.public_counts()["employer_actions_performed"] is False
    assert outcome.public_counts()["provider_calls"] == 0
    assert all("example.fi" not in str(value) for value in outcome.public_counts().values())
    spaces = fx[5].list(fx[0])
    assert len(spaces) == 1
    assert spaces[0].role_title == "Junior Data Analyst"
    assert spaces[0].status == "draft"
    assert spaces[0].to_dict()["authority"]["may_submit_to_employer"] is False
    again = run_local(fx)
    assert again.created == 0 and again.already_prepared == 1
    assert len(fx[5].list(fx[0])) == 1


def test_general_mode_unapproved_evidence_and_optout_never_create():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,settings=fx
    prefs.save(pid,{**settings,"auto_draft_enabled":False},expected_revision=1)
    assert run_local(fx).status=="disabled"
    with pytest.raises(SearchPreferenceError):
        prefs.save(pid,{**settings,"mode":"general"},expected_revision=2)
    with pytest.raises(SearchPreferenceError):
        prefs.save(pid,{**settings,"auto_draft_enabled":1},expected_revision=2)
    prefs.save(pid,{**settings,"mode":"general","auto_draft_enabled":False},expected_revision=2)
    assert run_local(fx).status=="disabled"
    prefs.save(pid,settings,expected_revision=3)
    empty=MemoryProfileRepository(profile_id=pid)
    result=prepare_profile_shortlist(pid,preferences_repository=prefs,
        job_repository=jobs,profile_repository=empty,
        cv_repository=cv,workspace_repository=spaces)
    assert result.status=="needs_approved_profile"
    assert spaces.list(pid)==[]


def test_revoked_optin_between_scoring_and_creation_stops_all_writes():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,settings=fx
    original=prefs.auto_draft_guard
    from contextlib import contextmanager
    @contextmanager
    def revoke_before_guard(profile_id,revision):
        prefs.save(pid,{**settings,"auto_draft_enabled":False},expected_revision=revision)
        with original(profile_id,revision) as allowed:
            yield allowed
    prefs.auto_draft_guard=revoke_before_guard
    result=run_local(fx)
    assert result.stopped_on_opt_out is True
    assert result.created==0
    assert spaces.list(pid)==[]


def test_expired_posting_and_https_safety_never_create_offsite_application():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,_=fx
    good=next(j for j in jobs.values() if j.job.role_title=="Junior Data Analyst")
    jobs.mark_closed(good.canonical_key)
    outcome=run_local(fx)
    assert outcome.created==0
    for url in (
        "http://careers.example.fi/job/100",
        "https://localhost/jobs/123",
        "https://person:secret@careers.example.fi/jobs/1",
        "https://careers.example.fi:444/jobs/123",
        "https://8.8.8.8/jobs/123",
        "https://printer.local/jobs/123",
        "https://[2001:db8::1]/jobs/123",
    ):
        # The upstream canonicalizer normally STRIPS userinfo from URLs
        # before storage. Inject the uncanonicalized record directly to
        # verify this additional safe-final-link gate itself.
        original=candidate("Junior Data Analyst")
        j=replace(original,job=replace(original.job,application_url=url))
        assert prepare_profile_shortlist(
            pid,preferences_repository=prefs,
            job_repository=MemoryJobRepositoryWith(j),
            profile_repository=profile,cv_repository=cv,
            workspace_repository=spaces,
        ).created==0


class MemoryJobRepositoryWith(MemoryJobRepository):
    def __init__(self, job):
        super().__init__()
        self.upsert(job)


def test_incomplete_approved_skills_are_not_upgraded_to_high_fit():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,_=fx
    weak=MemoryProfileRepository(profile_id=pid)
    weak.upsert_fact(ProfileFact("skill","Python","user-entered",approved=True))
    result=prepare_profile_shortlist(
        pid,preferences_repository=prefs,job_repository=jobs,
        profile_repository=weak,cv_repository=cv,workspace_repository=spaces,
    )
    assert result.status=="prepared"
    assert result.created==0
    assert spaces.list(pid)==[]


def test_mismatched_profile_id_does_not_cross_account_or_copy_cv():
    fx=fixture()
    pid,prefs,jobs,profile,cv,spaces,_=fx
    other = MemoryProfileRepository(profile_id="other-user")
    other.upsert_fact(ProfileFact("skill","Python","user-entered",approved=True))
    result=prepare_profile_shortlist(
        pid,preferences_repository=prefs,job_repository=jobs,
        profile_repository=other,cv_repository=cv,workspace_repository=spaces,
    )
    assert result.status=="owner_mismatch"
    assert spaces.list(pid)==[]


DSN=os.getenv("SMARTPLOY_TEST_DATABASE_URL","")


@pytest.mark.skipif(not DSN,reason="requires real PostgreSQL")
def test_actual_postgres_only_lists_active_opted_in_accounts_and_persists_one_draft():
    from psycopg import connect
    PostgresJobRepository(DSN).migrate()
    unique=uuid4().hex
    identities=PostgresIdentityRepository(DSN)
    owner=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://synthetic.example.invalid",
        subject="auto-draft-"+unique,email="auto@example.invalid",auth_source="oidc",
    ))
    other=identities.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://synthetic.example.invalid",
        subject="not-opted-"+unique,email="auto@example.invalid",auth_source="oidc",
    ))
    prefs=PostgresSearchPreferenceRepository(DSN)
    jobs=PostgresJobRepository(DSN)
    profiles=PostgresProfileRepository(DSN,profile_id=owner.profile_id)
    spaces=PostgresWorkspaceRepository(DSN)
    cv=PostgresCVRepository(DSN)
    job=candidate("Junior Data Analyst",url="https://careers.example.fi/jobs/"+unique)
    try:
        for skill in ("Python", "SQL", "data analysis"):
            profiles.upsert_fact(ProfileFact("skill",skill,"user-entered",approved=True))
        jobs.upsert(job)
        config={"mode":"personalized","roles":["Data Analyst"],
                "auto_draft_enabled":True}
        saved=prefs.save(owner.profile_id,config,expected_revision=0)
        prefs.save(other.profile_id,{**config,"auto_draft_enabled":False},expected_revision=0)
        listed=prefs.list_auto_draft_profiles(limit=500)
        assert owner.profile_id in listed
        assert other.profile_id not in listed
        first=prepare_profile_shortlist(
            owner.profile_id,preferences_repository=prefs,job_repository=jobs,
            profile_repository=profiles,cv_repository=cv,workspace_repository=spaces,
            candidates=[job],
        )
        assert first.created>=1 and first.public_counts()["provider_calls"]==0
        assert spaces.get(owner.profile_id,spaces.list(owner.profile_id)[0].workspace_id)
        assert spaces.list(other.profile_id)==[]
        assert prepare_profile_shortlist(
            owner.profile_id,preferences_repository=prefs,job_repository=jobs,
            profile_repository=profiles,cv_repository=cv,workspace_repository=spaces,
            candidates=[job],
        ).created==0
        # SP16's least-recently-scanned queue design prevents starvation.
        second_saved=prefs.save(other.profile_id,config,expected_revision=1)
        assert prefs.mark_auto_draft_checked(owner.profile_id,saved.revision)
        scan_order=prefs.list_auto_draft_profiles(limit=500)
        assert scan_order.index(other.profile_id) < scan_order.index(owner.profile_id)
        assert not prefs.mark_auto_draft_checked(owner.profile_id,saved.revision+1)
        prefs.save(other.profile_id,{**config,"auto_draft_enabled":False},
                   expected_revision=second_saved.revision)
        with prefs.auto_draft_guard(owner.profile_id,saved.revision) as allowed:
            assert allowed
        prefs.save(owner.profile_id,{**config,"auto_draft_enabled":False},
                   expected_revision=saved.revision)
        with prefs.auto_draft_guard(owner.profile_id,saved.revision) as allowed:
            assert not allowed
        assert owner.profile_id not in prefs.list_auto_draft_profiles(limit=500)
        assert not prefs.mark_auto_draft_checked(owner.profile_id,saved.revision)
        assert prepare_profile_shortlist(
            owner.profile_id,preferences_repository=prefs,job_repository=jobs,
            profile_repository=profiles,cv_repository=cv,workspace_repository=spaces,
            candidates=[job],
        ).created==0
    finally:
        with connect(DSN) as conn:
            with conn.cursor() as cur:
                for pid in (owner.profile_id,other.profile_id):
                    cur.execute("DELETE FROM smartploy_application_workspaces WHERE profile_id=%s",(pid,))
                    cur.execute("DELETE FROM smartploy_search_preferences WHERE profile_id=%s",(pid,))
                    cur.execute("DELETE FROM smartploy_profile_facts WHERE profile_id=%s",(pid,))


def test_worker_cycle_isolates_one_account_failure_and_reports_only_aggregate_counts(monkeypatch):
    """A broken account must not prevent the next user's applications."""
    from types import SimpleNamespace
    from smartploy import auto_draft_shortlist as module
    from smartploy.auto_draft_shortlist import AutoDraftSummary

    class Preferences:
        def __init__(self):
            self.marked = []

        def list_auto_draft_profiles(self, limit):
            assert limit == 7
            return ["private-broken", "private-healthy"]

        def get(self, profile_id):
            return SimpleNamespace(revision=4)

        def mark_auto_draft_checked(self, profile_id, revision):
            self.marked.append((profile_id, revision))
            return True

    prefs = Preferences()
    monkeypatch.setattr(module, "PostgresSearchPreferenceRepository", lambda dsn: prefs)
    monkeypatch.setattr(
        module, "PostgresJobRepository",
        lambda dsn: SimpleNamespace(values=lambda: []),
    )
    monkeypatch.setattr(module, "PostgresWorkspaceRepository", lambda dsn: object())
    monkeypatch.setattr(module, "PostgresCVRepository", lambda dsn: object())
    monkeypatch.setattr(module, "PostgresProfileRepository", lambda dsn, profile_id: object())

    def fake_prepare(profile_id, **kwargs):
        if profile_id == "private-broken":
            raise ValueError("private-broken: sensitive CV content")
        return AutoDraftSummary("prepared", checked=2, eligible=1, created=1)

    monkeypatch.setattr(module, "prepare_profile_shortlist", fake_prepare)
    result = module.prepare_worker_shortlists("synthetic", profile_limit=7, total_new_limit=4)
    assert result["profiles_checked"] == 2
    assert result["profiles_failed"] == 1
    assert result["drafts_created"] == 1
    assert prefs.marked == [("private-broken", 4), ("private-healthy", 4)]
    assert "private-broken" not in str(result)
    assert "sensitive CV" not in str(result)
    assert result["model_calls"] == 0
    assert result["employer_actions_performed"] is False


def test_deadline_parser_reuses_iso_finnish_dates_without_ambiguous_timezone():
    from datetime import datetime, timezone
    from smartploy.auto_draft_shortlist import _deadline_open
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    assert _deadline_open("", now=now)
    assert _deadline_open("2026-10-20", now=now)
    assert _deadline_open("20.10.2026", now=now)
    assert not _deadline_open("2026-10-20T15:00:00+03:00", now=now)
    assert _deadline_open("2026-10-20T15:01:00+03:00", now=now)
    assert not _deadline_open("2026-10-19", now=now)
    assert not _deadline_open("19.10.2026", now=now)
    assert not _deadline_open("not-confirmed", now=now)
    assert not _deadline_open("2026-10-20T18:00:00", now=now)


def test_auto_draft_skips_expired_or_unparseable_deadlines_but_accepts_future():
    fx = fixture()
    pid, prefs, jobs, profile, cv, spaces, _ = fx
    base = candidate("Junior Data Analyst")
    for deadline in ("2000-01-01", "01.01.2000", "2000-01-01T00:00:00Z", "unknown date"):
        old = replace(base, job=replace(base.job, deadline=deadline))
        result = prepare_profile_shortlist(
            pid, preferences_repository=prefs,
            job_repository=MemoryJobRepositoryWith(old),
            profile_repository=profile, cv_repository=cv,
            workspace_repository=spaces,
        )
        assert result.created == 0
    assert spaces.list(pid) == []
    future = replace(base, job=replace(base.job, deadline="2099-12-31"))
    result = prepare_profile_shortlist(
        pid, preferences_repository=prefs,
        job_repository=MemoryJobRepositoryWith(future),
        profile_repository=profile, cv_repository=cv,
        workspace_repository=spaces,
    )
    assert result.created == 1
    assert spaces.list(pid)[0].role_title == "Junior Data Analyst"


def test_auto_draft_rechecks_employer_url_role_requirements_after_source_race():
    """Reuse source fingerprint, but do not trust fields it never hashed."""
    fx = fixture()
    pid, prefs, jobs, profile, cv, spaces, _ = fx
    original = candidate("Junior Data Analyst")
    changes = (
        {"application_url": "https://another.example.fi/jobs/redirect"},
        {"company": "An unrelated employer"},
        {"role_title": "Senior Manager"},
        {"location": "Overseas"},
        {"deadline": "2099-12-31"},
        {"requirements": ("Unapproved license",)},
    )

    class ChangedAfterRanking(MemoryJobRepository):
        def __init__(self, stale, changed):
            super().__init__()
            self.upsert(stale)
            self.changed = changed

        def get(self, canonical_key):
            return self.changed

    for change in changes:
        latest = replace(original, job=replace(original.job, **change))
        assert latest.description_fingerprint == original.description_fingerprint
        assert prepare_profile_shortlist(
            pid, preferences_repository=prefs,
            job_repository=ChangedAfterRanking(original, latest),
            profile_repository=profile, cv_repository=cv,
            workspace_repository=spaces,
        ).created == 0
    assert spaces.list(pid) == []


def test_recently_verified_source_uses_observation_not_posting_date():
    from smartploy.auto_draft_shortlist import MAX_VERIFIED_AGE, _recently_verified
    fixed_now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    job = candidate("Junior Data Analyst")
    fresh = replace(job, posted_at="2023-01-01T00:00:00Z",
                    last_verified_at="2026-10-21T11:59:00Z",
                    last_seen_at="2026-10-21T11:59:00Z")
    assert _recently_verified(fresh, now=fixed_now)
    at_boundary = replace(fresh, last_verified_at=(fixed_now - MAX_VERIFIED_AGE).isoformat())
    assert _recently_verified(at_boundary, now=fixed_now)
    assert not _recently_verified(
        replace(fresh, last_verified_at=(fixed_now - MAX_VERIFIED_AGE - timedelta(seconds=1)).isoformat()),
        now=fixed_now
    )
    for stamp in ("2026-10-21T12:00:01Z", "bad clock", "2026-10-21T11:00:00"):
        assert not _recently_verified(replace(fresh, last_verified_at=stamp), now=fixed_now)
    assert not _recently_verified(
        replace(fresh, last_verified_at="", last_seen_at=""), now=fixed_now
    )
    assert _recently_verified(replace(fresh, last_verified_at=""), now=fixed_now)


def test_source_current_flag_alone_cannot_create_from_expired_cache():
    fx = fixture()
    pid, prefs, jobs, profile, cv, spaces, _ = fx
    base = candidate("Junior Data Analyst")
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    stale = replace(base, last_verified_at=old, last_seen_at=old, first_seen_at=old)
    assert stale.source_current  # Exactly the failure mode after a stuck poller.
    result = prepare_profile_shortlist(
        pid, preferences_repository=prefs,
        job_repository=MemoryJobRepositoryWith(stale),
        profile_repository=profile, cv_repository=cv,
        workspace_repository=spaces,
    )
    assert result.status == "needs_source_refresh"
    assert result.stale_skipped == 1
    assert result.public_counts()["stale_skipped"] == 1
    assert result.public_counts()["employer_actions_performed"] is False
    assert result.created == 0
    assert spaces.list(pid) == []
    ready = prepare_profile_shortlist(
        pid, preferences_repository=prefs,
        job_repository=MemoryJobRepositoryWith(base),
        profile_repository=profile, cv_repository=cv,
        workspace_repository=spaces,
    )
    assert ready.status == "prepared"
    assert ready.created == 1


def test_source_refresh_race_is_rechecked_inside_user_optin_guard():
    fx = fixture()
    pid, prefs, jobs, profile, cv, spaces, _ = fx
    base = candidate("Junior Data Analyst")
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    stale = replace(base, last_verified_at=old, last_seen_at=old, first_seen_at=old)

    class StaleAfterScoring(MemoryJobRepository):
        def __init__(self):
            super().__init__()
            self.upsert(base)

        def get(self, canonical_key):
            return stale

    result = prepare_profile_shortlist(
        pid, preferences_repository=prefs,
        job_repository=StaleAfterScoring(),
        profile_repository=profile, cv_repository=cv,
        workspace_repository=spaces,
    )
    assert result.status == "needs_source_refresh"
    assert result.created == 0
    assert result.stale_skipped == 1
    assert spaces.list(pid) == []



def test_manual_or_unknown_search_feeds_never_create_unattended_private_drafts():
    """A manual bookmark's recent timestamp is not employer-source verification."""
    fx = fixture()
    pid,prefs,_,profile,cv,spaces,_=fx
    inputs = (
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
        SourcePolicy("lever-global-fake", "Unreviewed Search",
                     "community_search", ("api",)),
    )
    for policy in inputs:
        unsafe = normalize_observation(
            SourceObservation(
                source_id=policy.source_id,
                source_mode=policy.allowed_modes[0],
                source_url="https://careers.example.fi/jobs/junior-data-analyst",
                raw_text="Junior Data Analyst vacancy",
                observed_at=datetime.now(timezone.utc).isoformat(),
                payload={
                    "company": "Synthetic Employer",
                    "role_title": "Junior Data Analyst",
                    "description": "Python data analysis and SQL business reporting",
                    "location": "Helsinki",
                    "application_url": "https://careers.example.fi/jobs/junior-data-analyst",
                },
            ),
            policy,
        )
        assert unsafe.candidate is not None
        result = prepare_profile_shortlist(
            pid, preferences_repository=prefs,
            job_repository=MemoryJobRepositoryWith(unsafe.candidate),
            profile_repository=profile, cv_repository=cv,
            workspace_repository=spaces,
        )
        assert result.status == "needs_trusted_source"
        assert result.created == 0
        assert result.unverified_source_skipped == 1
        assert result.public_counts()["employer_actions_performed"] is False
        assert "careers.example.fi" not in str(result.public_counts())
    assert spaces.list(pid) == []


def test_both_existing_finnish_public_feed_policy_types_remain_usable_for_drafts():
    """Reuse real JobMarket Finland/Kuntarekry policy types, not a Lever-only gate."""
    from smartploy.auto_draft_shortlist import _approved_source_for_auto_draft
    original = candidate("Junior Data Analyst")
    assert _approved_source_for_auto_draft(original)
    choices = (
        ("national_job_market", "api", "job-market-finland"),
        ("public_sector_jobs", "feed", "kuntarekry"),
    )
    for source_class, mode, sid in choices:
        job = replace(original.job, source=sid, raw={
            **original.job.raw, "source_class": source_class, "source_mode": mode,
        })
        record = replace(original, job=job, source_ids=(sid,), metadata={
            **original.metadata, "source_class": source_class, "source_mode": mode,
        })
        assert _approved_source_for_auto_draft(record), (source_class, mode, sid)
        fx=fixture()
        pid,prefs,_,profile,cv,spaces,_=fx
        outcome = prepare_profile_shortlist(
            pid, preferences_repository=prefs,
            job_repository=MemoryJobRepositoryWith(record),
            profile_repository=profile, cv_repository=cv,
            workspace_repository=spaces,
        )
        assert outcome.created == 1 and outcome.status == "prepared"
        assert len(spaces.list(pid)) == 1


def test_mixed_or_conflicting_provenance_does_not_inherit_ats_draft_authority():
    """Original merge_candidates may keep an older job body but newer source metadata."""
    from smartploy.auto_draft_shortlist import _approved_source_for_auto_draft
    from smartploy.domain import merge_candidates
    original = candidate("Junior Data Analyst")
    manual = normalize_observation(
        SourceObservation(
            source_id="manual-import", source_mode="manual",
            source_url="https://careers.example.fi/jobs/junior-data-analyst",
            raw_text="Junior Data Analyst vacancy",
            observed_at=datetime.now(timezone.utc).isoformat(),
            payload={
                "company": "Synthetic Employer",
                "role_title": "Junior Data Analyst",
                "description": "Python data analysis and SQL business reporting",
                "location": "Helsinki",
                "application_url": "https://careers.example.fi/jobs/junior-data-analyst",
            },
        ),
        SourcePolicy("manual-import", "Manual", "manual", ("manual",)),
    ).candidate
    assert manual is not None
    assert manual.canonical_key == original.canonical_key
    assert not _approved_source_for_auto_draft(merge_candidates(original, manual))
    assert not _approved_source_for_auto_draft(merge_candidates(manual, original))
    # A forged source ID with an inconsistent policy/body never becomes trusted.
    assert not _approved_source_for_auto_draft(
        replace(original, source_ids=("lever-global-synthetic-firm", "manual-import"))
    )
    assert not _approved_source_for_auto_draft(
        replace(original, metadata={**original.metadata, "source_class": "manual"})
    )
    assert not _approved_source_for_auto_draft(
        replace(original, job=replace(original.job, raw={}))
    )


def test_source_provenance_rechecked_after_race_but_before_workspace_creation():
    fx = fixture()
    pid,prefs,_,profile,cv,spaces,_=fx
    current = candidate("Junior Data Analyst")
    compromised = replace(
        current, metadata={**current.metadata, "source_mode": "manual"},
    )

    class ChangedSourceAfterRanking(MemoryJobRepository):
        def __init__(self):
            super().__init__()
            self.upsert(current)

        def get(self, canonical_key):
            return compromised

    result = prepare_profile_shortlist(
        pid, preferences_repository=prefs,
        job_repository=ChangedSourceAfterRanking(),
        profile_repository=profile,
        cv_repository=cv, workspace_repository=spaces,
    )
    assert result.status == "needs_trusted_source"
    assert result.unverified_source_skipped == 1
    assert result.created == 0
    assert spaces.list(pid) == []

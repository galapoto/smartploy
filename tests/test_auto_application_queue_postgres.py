"""Real PostgreSQL two-account opt-in and scheduled IT draft integration.

The original worker/source/profile/identity/workspace code is executed with
a synthetic vacancy. No applicant CV is sent to any provider/employer.
"""
from __future__ import annotations

import os
import uuid

import pytest
from psycopg import connect

from smartploy.application_workspace_storage import PostgresWorkspaceRepository
from smartploy.domain import SourceObservation, SourcePolicy, normalize_observation
from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository
from smartploy.profile import ProfileFact
from smartploy.profile_storage import PostgresProfileRepository
from smartploy.search_preference_storage import PostgresSearchPreferenceRepository
from smartploy.storage import PostgresJobRepository
from smartploy.worker_runtime import build_worker_task_specs


DSN = os.getenv("SMARTPLOY_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DSN,reason="PostgreSQL test database required")


def _preferences(enabled=True, mode="personalized"):
    return {
        "mode":mode,
        "roles":["Auto Queue Synthetic IT Analyst"],
        "locations":["Helsinki"],
        "languages":["english"],"work_modes":["remote"],
        "seniority":"entry","auto_drafts_enabled":enabled,
    }


def test_scheduled_auto_matching_uses_only_live_owner_consent_and_never_submits(monkeypatch):
    repo=PostgresJobRepository(DSN)
    repo.migrate()
    nonce=uuid.uuid4().hex[:10]
    title="Auto Queue Synthetic IT Analyst"
    result=normalize_observation(SourceObservation(
        source_id="synthetic-it-discovery",source_mode="manual",
        source_url=f"https://jobs.example.invalid/it-{nonce}",
        raw_text=f"{title} Helsinki Python SQL",
        payload={
            "company":"Synthetic Employer Oy",
            "role_title":title,"description":"SQL Python data reporting",
            "location":"Helsinki","language":"English","work_mode":"remote",
            "application_url":f"https://jobs.example.invalid/it-{nonce}",
        },
    ),SourcePolicy("synthetic-it-discovery","Synthetic","manual",("manual",)))
    assert result.candidate is not None
    job=repo.upsert(result.candidate)
    identity=PostgresIdentityRepository(DSN)
    a=identity.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://test-idp.invalid",subject="opt-in-"+nonce,
        email="one@example.invalid",auth_source="oidc",
    ))
    b=identity.resolve_or_create(AuthenticatedPrincipal(
        issuer="https://test-idp.invalid",subject="no-opt-in-"+nonce,
        email="two@example.invalid",auth_source="oidc",
    ))
    prefs=PostgresSearchPreferenceRepository(DSN)
    work=PostgresWorkspaceRepository(DSN)
    pa=PostgresProfileRepository(DSN,profile_id=a.profile_id)
    pb=PostgresProfileRepository(DSN,profile_id=b.profile_id)
    try:
        pa.upsert_fact(ProfileFact(
            "identity","Synthetic Candidate A","user-entered",approved=True
        ).normalized())
        pb.upsert_fact(ProfileFact(
            "identity","Synthetic Candidate B","user-entered",approved=True
        ).normalized())
        prefs.save(a.profile_id,_preferences(),expected_revision=0)
        prefs.save(b.profile_id,_preferences(False),expected_revision=0)
        chosen=prefs.list_auto_draft_profiles(limit=100)
        assert (a.user_id,a.profile_id) in chosen
        assert (b.user_id,b.profile_id) not in chosen

        for key in (
            "KUNTAREKRY_FEED_URL","JOBMARKET_FINLAND_API_ENABLED",
            "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON","SMARTPLOY_PUBLIC_ATS_SOURCES_FILE",
            "OBUMAI_BASE_URL","SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED",
        ):
            monkeypatch.delenv(key,raising=False)
        monkeypatch.setenv("SMARTPLOY_ENVIRONMENT","production")
        monkeypatch.setenv("SMARTPLOY_WORKER_LOCAL_AUTO_DRAFT_ENABLED","true")
        specs=build_worker_task_specs(DSN)
        task=next(s for s in specs if s.task_id=="application:auto-draft-matches")
        response=task.runner()
        assert response.status in {"healthy","degraded"}
        assert response.details["external_actions_authorized"] is False
        assert response.details["external_ai_forwarding_performed"] is False
        assert response.details["employer_submissions"]==0

        kits=work.list(a.profile_id)
        assert any(w.canonical_key==job.canonical_key for w in kits)
        assert not work.list(b.profile_id)
        current=next(w for w in kits if w.canonical_key==job.canonical_key)
        assert current.status=="draft"
        assert "Synthetic Candidate A" in current.cv_text
        assert "Synthetic Candidate B" not in current.cv_text

        before=len(kits)
        task.runner()
        assert len(work.list(a.profile_id))==before
        # General mode automatically disarms background matching immediately
        # after an owner preference revision.
        prefs.save(a.profile_id,_preferences(False,"general"),expected_revision=1)
        assert (a.user_id,a.profile_id) not in prefs.list_auto_draft_profiles(limit=100)
        task.runner()
        assert len(work.list(a.profile_id))==before
    finally:
        for user in (a,b):
            for kit in work.list(user.profile_id):
                work.delete(user.profile_id,kit.workspace_id)
        with connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM smartploy_search_preferences WHERE profile_id IN (%s,%s)",
                            (a.profile_id,b.profile_id))
                cur.execute("DELETE FROM smartploy_profile_facts WHERE profile_id IN (%s,%s)",
                            (a.profile_id,b.profile_id))
                cur.execute("DELETE FROM smartploy_users WHERE user_id IN (%s,%s)",
                            (a.user_id,b.user_id))
                cur.execute("DELETE FROM smartploy_jobs WHERE canonical_key=%s",(job.canonical_key,))

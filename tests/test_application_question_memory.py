"""SP116: original profile tenancy + durable safe employer question memory.

No external employer forms, users, browser or AI system involved.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from smartploy.application_question_memory import (
    MemoryApplicationQuestionRepository,
    PostgresApplicationQuestionRepository,
    QuestionMemoryError,
    safe_question,
    scope_for_question,
)
from smartploy.profile import CandidateProfile, ProfileFact
from smartploy.storage import apply_migrations


@pytest.mark.parametrize("label,identifier", [
    ("Do you require visa sponsorship?", ""),
    ("Salary expectation", ""),
    ("Work authorization", ""),
    ("Do you agree to our privacy policy?", ""),
    ("Kansalaisuus ja oleskelulupa", ""),
    ("What is your previous medical condition?", ""),
    ("Project details", "salaryExpectation"),
    ("Python experience", "visaStatus"),
    ("Languages", "GDPRConsent"),
    ("Full name", "genderIdentity"),
    ("Email your CV to private@example.invalid", ""),
    ("https://external.example.invalid/private", ""),
])
def test_sensitive_or_private_questions_are_never_saved(label, identifier):
    with pytest.raises(QuestionMemoryError):
        safe_question(label, (identifier,))


def test_original_safe_question_identity_deduplicated_and_pending():
    memory = MemoryApplicationQuestionRepository()
    rows, skipped = memory.observe(
        "profile-A",
        ["Describe a project you led", "  Describe   a  project you led  ",
         "What data tools have you used?"],
    )
    assert len(rows) == 2 and skipped == 1
    assert rows[0].answer == "" and rows[0].approved_for_reuse is False
    assert len(rows[0].question_key) == 64
    again, skipped = memory.observe(
        "profile-A", ["Describe a project you led"],
    )
    assert skipped == 0 and again[0].question_key == rows[0].question_key
    assert len(memory.list("profile-A")) == 2


def test_profile_mode_cv_only_never_auto_creates_an_answer():
    memory = MemoryApplicationQuestionRepository()
    assert memory.mode("profile-A") == "guided"
    assert memory.set_mode("profile-A", "cv_only") == "cv_only"
    assert memory.mode("profile-B") == "guided"
    with pytest.raises(QuestionMemoryError):
        memory.set_mode("profile-A", "unsupported")
    # The endpoint refuses prompt observation in CV-only mode. The repository
    # must ALSO deny programmatic writes if the preference changes meanwhile.
    with pytest.raises(QuestionMemoryError):
        memory.observe("profile-A", ["Describe a project you led"])


def test_approved_answers_only_after_user_review_and_revision_cas():
    memory = MemoryApplicationQuestionRepository()
    rows, _ = memory.observe("owner", ["Describe a project you led"])
    key = rows[0].question_key
    item = memory.save("owner", key, "Led a documented analytics project.", 1, True)
    assert item.approved_for_reuse is True
    assert item.version == 2
    assert memory.observe("owner", [item.label])[0][0] == item
    with pytest.raises(QuestionMemoryError, match="version"):
        memory.save("owner", key, "Wrong replacement", 1, True)
    assert memory.list("owner")[0].answer == "Led a documented analytics project."
    assert memory.list("other") == []
    with pytest.raises(QuestionMemoryError):
        memory.save("other", key, "Not my question", 1, True)


def test_job_specific_answers_must_remain_manual_and_not_portable():
    memory = MemoryApplicationQuestionRepository()
    label = "Why do you want to work for our company?"
    assert scope_for_question(label) == "manual_only"
    record = memory.observe("owner", [label])[0][0]
    with pytest.raises(QuestionMemoryError, match="Job-specific"):
        memory.save("owner", record.question_key, "Specific company reason", 1, True)
    saved = memory.save("owner", record.question_key, "Specific company reason", 1, False)
    assert saved.approved_for_reuse is False
    assert saved.reusable_scope == "manual_only"


def test_profile_memory_deletion_is_owner_scoped():
    memory = MemoryApplicationQuestionRepository()
    a = memory.observe("owner-a", ["How many data tools have you used?"])[0][0]
    b = memory.observe("owner-b", ["How many data tools have you used?"])[0][0]
    assert a.question_key == b.question_key
    assert memory.delete("owner-b", a.question_key)
    assert len(memory.list("owner-a")) == 1
    assert memory.delete("owner-b", a.question_key) is False


def test_manual_only_applicant_facts_not_exported_to_default_automated_evidence():
    profile = CandidateProfile(facts=(
        ProfileFact("skill", "Python", "confirmed-by-applicant", approved=True),
        ProfileFact("work_authorization", "Private status", "confirmed", approved=True),
        ProfileFact("salary_expectation", "Private expectation", "confirmed", approved=True),
        ProfileFact("notice_period", "Private timeline", "confirmed", approved=True),
        ProfileFact("references", "Private referee", "confirmed", approved=True),
    ))
    approval = profile.approved_evidence()
    assert approval["approved_fact_count"] == 1
    assert set(approval["facts"]) == {"skill"}
    assert profile.summary()["approved_fact_count"] == 5


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="PostgreSQL required")
def test_postgres_profile_question_cas_mode_and_cross_user_isolation():
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    apply_migrations(dsn)
    repo = PostgresApplicationQuestionRepository(dsn)
    pa = "profile-sp116-a-" + uuid4().hex
    pb = "profile-sp116-b-" + uuid4().hex
    try:
        assert repo.mode(pa) == "guided"
        observed = repo.observe(pa, ["Describe a data project you led"])[0][0]
        assert repo.list(pb) == []
        new_instance = PostgresApplicationQuestionRepository(dsn)
        saved = new_instance.save(
            pa, observed.question_key, "Verified synthetic project.", 1, True,
        )
        assert new_instance.list(pa)[0] == saved
        assert new_instance.list(pb) == []
        with pytest.raises(QuestionMemoryError):
            repo.save(pa, observed.question_key, "Changed", 1, True)
        assert repo.set_mode(pa, "cv_only") == "cv_only"
        assert repo.mode(pa) == "cv_only"
        with pytest.raises(QuestionMemoryError):
            repo.save(pa, observed.question_key, "Changed", 2, True)
        assert repo.mode(pb) == "guided"
    finally:
        from psycopg import connect
        with connect(dsn) as conn:
            conn.execute(
                "DELETE FROM smartploy_application_profile_questions "
                "WHERE profile_id IN (%s,%s)", (pa, pb),
            )
            conn.execute(
                "DELETE FROM smartploy_application_profile_settings "
                "WHERE profile_id IN (%s,%s)", (pa, pb),
            )

"""Offline negative controls for SmartPloy feature-first production promotion."""
from __future__ import annotations

from copy import deepcopy
import pytest

from scripts.feature_first_ci_attestation import (
    REQUIRED_JOBS, PromotionDenied, validate_jobs, validate_run,
)


SHA = "a" * 40
REPO = "galapoto/smartploy"
WORKFLOW_RUN = {
    "name": "Smartploy CI", "event": "push", "head_branch": "main",
    "status": "completed", "conclusion": "success", "head_sha": SHA,
    "head_repository": {"full_name": REPO}, "id": 41881720668,
}
EVENT = {"action": "completed", "repository": {"full_name": REPO},
         "workflow_run": WORKFLOW_RUN}
JOBS = [{"name": name, "status": "completed", "conclusion": "success"}
        for name in sorted(REQUIRED_JOBS)]


def test_accepts_only_exact_main_push_and_all_five_green_jobs():
    assert validate_run(EVENT, REPO) == (SHA, 41881720668)
    validate_jobs(JOBS)


@pytest.mark.parametrize("field,value", [
    ("name", "Attack workflow"),
    ("event", "pull_request"),
    ("event", "workflow_dispatch"),
    ("head_branch", "feature/unreviewed"),
    ("head_branch", "refs/pull/1/merge"),
    ("status", "in_progress"),
    ("conclusion", "skipped"),
    ("conclusion", "failure"),
    ("head_sha", "a" * 12),
    ("head_sha", "b" * 40 + "\nssh"),
    ("id", True),
    ("id", -1),
])
def test_rejects_untrusted_or_incomplete_workflow_metadata(field, value):
    event = deepcopy(EVENT)
    event["workflow_run"][field] = value
    with pytest.raises(PromotionDenied):
        validate_run(event, REPO)


def test_rejects_wrong_repo_and_incomplete_action():
    event = deepcopy(EVENT)
    event["workflow_run"]["head_repository"]["full_name"] = "someone/fork"
    with pytest.raises(PromotionDenied):
        validate_run(event, REPO)
    event = deepcopy(EVENT)
    event["repository"]["full_name"] = "someone/fork"
    with pytest.raises(PromotionDenied):
        validate_run(event, REPO)
    event = deepcopy(EVENT)
    event["action"] = "requested"
    with pytest.raises(PromotionDenied):
        validate_run(event, REPO)


@pytest.mark.parametrize("broken", [
    [],
    JOBS[:-1],
    JOBS + [JOBS[0]],
    [dict(x, conclusion="failure") if x["name"] == "web" else x for x in JOBS],
    [dict(x, conclusion="skipped") if x["name"] == "browser" else x for x in JOBS],
    [dict(x, status="in_progress") if x["name"] == "test" else x for x in JOBS],
])
def test_rejects_missing_duplicate_failed_or_skipped_ci_jobs(broken):
    with pytest.raises(PromotionDenied):
        validate_jobs(broken)


def test_unrelated_successful_job_cannot_replace_required_gate():
    with pytest.raises(PromotionDenied):
        validate_jobs([{"name": "fake-release", "status": "completed",
                        "conclusion": "success"}])

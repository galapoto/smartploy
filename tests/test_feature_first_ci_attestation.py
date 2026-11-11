"""Offline negative controls for SmartPloy feature-first production promotion."""
from __future__ import annotations

from copy import deepcopy
import json
import pytest

from scripts.feature_first_ci_attestation import (
    REQUIRED_JOBS, PromotionDenied, fetch_qualified_main_run,
    select_qualified_main_run, validate_jobs, validate_run,
    validate_manual_request,
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


MANUAL_EVENT = {
    "ref": "refs/heads/main", "repository": {"full_name": REPO},
    "inputs": {"release_sha": SHA}
}


def test_manual_commissioning_retry_requires_same_sha_and_main():
    assert validate_manual_request(MANUAL_EVENT, REPO, SHA) == SHA
    for changes in (
        {"ref": "refs/heads/unreviewed"},
        {"ref": "refs/pull/9/merge"},
        {"repository": {"full_name": "attacker/fork"}},
        {"inputs": {"release_sha": "b" * 40}},
        {"inputs": {"release_sha": "main"}},
        {"inputs": {}},
    ):
        event = deepcopy(MANUAL_EVENT)
        event.update(changes)
        with pytest.raises(PromotionDenied):
            validate_manual_request(event, REPO, SHA)
    for unsafe_sha in ("main", "a" * 12, SHA + "; id", "", 3):
        with pytest.raises(PromotionDenied):
            validate_manual_request(MANUAL_EVENT, REPO, unsafe_sha)


def test_manual_retry_never_reuses_pr_fork_or_dispatch_ci_runs():
    run = deepcopy(WORKFLOW_RUN)
    assert select_qualified_main_run([run], REPO, SHA) == run["id"]
    candidates = []
    for key, changed in (
        ("event", "pull_request"), ("event", "workflow_dispatch"),
        ("head_branch", "feature/private"), ("head_sha", "b" * 40),
        ("status", "in_progress"), ("conclusion", "failure"),
        ("name", "Fake CI"), ("id", True),
        ("head_repository", {"full_name": "attacker/fork"}),
    ):
        wrong = deepcopy(run)
        wrong[key] = changed
        candidates.append(wrong)
    with pytest.raises(PromotionDenied):
        select_qualified_main_run(candidates, REPO, SHA)
    candidates.append(deepcopy(run))
    assert select_qualified_main_run(candidates, REPO, SHA) == run["id"]


def test_manual_retry_fetches_only_exact_sha_main_push_history(monkeypatch):
    observed: list[str] = []
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, _limit):
            return json.dumps({
                "workflow_runs": [WORKFLOW_RUN],
                "total_count": 1,
            }).encode("utf-8")
    def fake_urlopen(req, timeout):
        assert timeout == 15
        assert req.get_header("Authorization") == "Bearer synthetic-read-token"
        observed.append(req.full_url)
        return FakeResponse()
    monkeypatch.setattr(
        "scripts.feature_first_ci_attestation.urlopen", fake_urlopen
    )
    assert fetch_qualified_main_run(REPO, SHA, "synthetic-read-token") == WORKFLOW_RUN["id"]
    assert len(observed) == 1
    assert "head_sha=" + SHA in observed[0]
    assert "branch=main" in observed[0] and "event=push" in observed[0]
    with pytest.raises(PromotionDenied):
        fetch_qualified_main_run(REPO, "main", "synthetic-read-token")
    with pytest.raises(PromotionDenied):
        fetch_qualified_main_run(REPO, SHA, "")


def test_manual_retry_rejects_successful_workflow_with_incomplete_jobs():
    # A valid historical run ID is only step one; every job still matters.
    run_id = select_qualified_main_run([deepcopy(WORKFLOW_RUN)], REPO, SHA)
    assert run_id == WORKFLOW_RUN["id"]
    with pytest.raises(PromotionDenied):
        validate_jobs(JOBS[:-1])

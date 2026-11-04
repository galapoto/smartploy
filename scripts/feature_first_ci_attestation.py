"""Fail-closed GitHub main-push CI proof for FEATURE-FIRST-001 production promotion.

This gate never deploys. It establishes that one immutable merged source SHA
has five successful CI jobs from the *main push*, not a PR-only or synthetic
stack receipt. Production still requires native Woodpecker, approvals,
trusted SSH credentials, guarded host deploy and live evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SHA40 = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED_JOBS = frozenset({
    "test",
    "web",
    "browser",
    "deploy-stack",
    "Exact-checkout review receipt (not release approval)",
})


class PromotionDenied(ValueError):
    """There is no valid, reviewed main-push CI qualification."""


def validate_run(event: dict[str, Any], repository: str) -> tuple[str, int]:
    """Accept only a successful CI main push originating in our own repo."""
    if not repository or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise PromotionDenied("Expected a valid exact repository name")
    if not isinstance(event, dict) or event.get("action") != "completed":
        raise PromotionDenied("Only completed workflow_run events can promote")
    workflow = event.get("workflow_run")
    if not isinstance(workflow, dict):
        raise PromotionDenied("Workflow-run evidence missing")
    if workflow.get("name") != "Smartploy CI":
        raise PromotionDenied("Unrecognized upstream CI workflow")
    if (workflow.get("event") != "push" or
            workflow.get("head_branch") != "main" or
            workflow.get("status") != "completed" or
            workflow.get("conclusion") != "success"):
        raise PromotionDenied("No successful main-push qualification")
    head_repo = workflow.get("head_repository") or {}
    event_repo = event.get("repository") or {}
    if (not isinstance(head_repo, dict) or not isinstance(event_repo, dict)
            or head_repo.get("full_name") != repository
            or event_repo.get("full_name") != repository):
        raise PromotionDenied("CI event originated from another repository")
    sha = workflow.get("head_sha")
    run_id = workflow.get("id")
    if not isinstance(sha, str) or not SHA40.fullmatch(sha):
        raise PromotionDenied("Immutable 40-character SHA required")
    if type(run_id) is not int or run_id < 1:
        raise PromotionDenied("Invalid CI run identity")
    return sha, run_id


def validate_jobs(jobs: list[dict[str, Any]]) -> None:
    """Require every exact CI job once, with actual successful completion."""
    if not isinstance(jobs, list):
        raise PromotionDenied("No CI jobs available")
    by_name: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise PromotionDenied("Invalid CI job receipt")
        name = job.get("name")
        if name not in REQUIRED_JOBS:
            continue
        if name in by_name:
            raise PromotionDenied("Duplicate named CI gate: " + name)
        by_name[name] = job
    missing = REQUIRED_JOBS - by_name.keys()
    if missing:
        raise PromotionDenied("Missing CI gates: " + ", ".join(sorted(missing)))
    for name in REQUIRED_JOBS:
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise PromotionDenied("CI gate is not successful: " + name)


def fetch_jobs(repository: str, run_id: int, token: str) -> list[dict[str, Any]]:
    """Get only the latest-attempt jobs, with bounded pagination and no secrets."""
    if not token:
        raise PromotionDenied("GitHub read-only Actions token is required")
    all_jobs: list[dict[str, Any]] = []
    for page in range(1, 5):
        url = (
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs"
            f"?per_page=100&page={page}&filter=latest"
        )
        req = Request(url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urlopen(req, timeout=15) as response:
                raw = response.read(2_000_000)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise PromotionDenied("Unable to verify upstream CI jobs") from exc
        try:
            data = json.loads(raw)
            batch = data["jobs"]
            total = data["total_count"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PromotionDenied("Invalid GitHub CI jobs response") from exc
        if not isinstance(batch, list) or type(total) is not int:
            raise PromotionDenied("Invalid CI job response types")
        all_jobs.extend(batch)
        if len(all_jobs) >= total:
            return all_jobs
    raise PromotionDenied("CI jobs pagination exceeded safe verification limit")


def main() -> int:
    try:
        path = os.environ.get("GITHUB_EVENT_PATH", "")
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        event = json.loads(Path(path).read_text(encoding="utf-8"))
        sha, run_id = validate_run(event, repository)
        jobs = fetch_jobs(repository, run_id, os.environ.get("GH_TOKEN", ""))
        validate_jobs(jobs)
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise PromotionDenied("Trusted GitHub output file is required")
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"sha={sha}\n")
            handle.write(f"ci_run_id={run_id}\n")
            handle.write("qualified=true\n")
        print(f"FEATURE_FIRST_GITHUB_MAIN_QUALIFIED sha={sha} ci_run_id={run_id}")
        print("FEATURE_FIRST_PRODUCTION_RELEASE_PENDING_NATIVE_AND_APPROVAL")
        return 0
    except (PromotionDenied, OSError, ValueError, TypeError, KeyError) as exc:
        print("FEATURE_FIRST_PROMOTION_DENIED: " + str(exc), file=sys.stderr)
        return 43


if __name__ == "__main__":
    raise SystemExit(main())

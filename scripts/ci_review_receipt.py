"""Produce a small, read-only exact-checkout receipt after all SmartPloy CI gates.

A successful receipt is evidence of automated tests, **not** a human review,
production release approval, live SSO acceptance or employer submission.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


FORMAT = "smartploy-ci-review-receipt-v1"
REQUIRED_JOBS = ("test", "web", "browser", "deploy-stack")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_EVENTS = {"pull_request", "push", "workflow_dispatch"}


def _sha(value: str, label: str) -> str:
    if not _SHA.fullmatch(value):
        raise ValueError(f"{label} must be a full lowercase 40-character Git SHA")
    return value


def create_receipt(
    *,
    repository: str,
    event: str,
    run_id: str,
    run_attempt: str,
    checkout_sha: str,
    checkout_tree: str,
    expected_checkout_sha: str,
    pull_request_head_sha: str,
    job_results: dict[str, str],
) -> dict[str, object]:
    """Construct a receipt only when every unchanged CI gate succeeded.

    On PR events GitHub may check out a *synthetic merge commit*. Do not
    mistake the PR head SHA for the tested checkout SHA. Both are recorded.
    """
    if not _REPOSITORY.fullmatch(repository) or any(
        part in {".", ".."} for part in repository.split("/")
    ):
        raise ValueError("invalid GitHub repository")
    if event not in _EVENTS:
        raise ValueError("unsupported CI event")
    if not run_id.isdecimal() or int(run_id) < 1:
        raise ValueError("invalid workflow run ID")
    if not run_attempt.isdecimal() or int(run_attempt) < 1:
        raise ValueError("invalid workflow attempt")
    tested_sha = _sha(checkout_sha, "tested checkout SHA")
    tree_sha = _sha(checkout_tree, "tested checkout tree SHA")
    if tested_sha != _sha(expected_checkout_sha, "GitHub event SHA"):
        raise ValueError("checkout SHA differs from GitHub event SHA")
    if set(job_results) != set(REQUIRED_JOBS):
        raise ValueError("CI job results must contain exactly the four required gates")
    if any(job_results[name] != "success" for name in REQUIRED_JOBS):
        raise ValueError("a required CI job did not succeed")
    if event == "pull_request":
        pr_head = _sha(pull_request_head_sha, "pull request head SHA")
    else:
        if pull_request_head_sha:
            raise ValueError("a non-PR run must not claim a PR head")
        pr_head = None

    return {
        "format": FORMAT,
        "repository": repository,
        "workflow": {
            "event": event,
            "run_id": int(run_id),
            "attempt": int(run_attempt),
            "url": f"https://github.com/{repository}/actions/runs/{int(run_id)}",
        },
        "tested_checkout": {
            "commit_sha": tested_sha,
            "tree_sha": tree_sha,
            "is_pull_request_merge_ref_possible": event == "pull_request",
        },
        "pull_request_head_sha": pr_head,
        "required_job_results": {key: job_results[key] for key in REQUIRED_JOBS},
        "automated_ci_passed": True,
        "not_verified_by_ci": {
            "independent_human_security_review": True,
            "owner_approval_to_merge_or_deploy": True,
            "live_two_account_browser_acceptance": True,
            "first_party_oidc_cutover_acceptance": True,
            "production_backup_and_rollback": True,
            "fresh_finnish_ats_poll": True,
            "external_employer_submission": True,
        },
        "authorizes_merge": False,
        "authorizes_production_deployment": False,
    }


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def write_receipt(output_directory: Path, receipt: dict[str, object]) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    receipt_path = output_directory / "review-receipt.json"
    checksum_path = output_directory / "SHA256SUMS"
    encoded = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    receipt_path.write_bytes(encoded)
    checksum_path.write_text(
        f"{hashlib.sha256(encoded).hexdigest()}  review-receipt.json\n",
        encoding="ascii",
    )
    return receipt_path, checksum_path


def main() -> None:
    """Read only GitHub-provided runner metadata; never access secrets or hosts."""
    expected = os.environ.get("GITHUB_SHA", "")
    results = {name: os.environ.get("SMARTPLOY_CI_" + name.upper().replace("-", "_"), "")
               for name in REQUIRED_JOBS}
    receipt = create_receipt(
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        event=os.environ.get("GITHUB_EVENT_NAME", ""),
        run_id=os.environ.get("GITHUB_RUN_ID", ""),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        checkout_sha=_git("rev-parse", "HEAD"),
        checkout_tree=_git("rev-parse", "HEAD^{tree}"),
        expected_checkout_sha=expected,
        pull_request_head_sha=os.environ.get("SMARTPLOY_PR_HEAD_SHA", ""),
        job_results=results,
    )
    output_directory = Path(os.environ.get("SMARTPLOY_RECEIPT_DIRECTORY", "review-evidence"))
    receipt_path, checksum_path = write_receipt(output_directory, receipt)
    print(f"review-only receipt: {receipt_path}")
    print(f"checksum: {checksum_path}")
    print(f"tested checkout: {receipt['tested_checkout']['commit_sha']}")
    if receipt["pull_request_head_sha"]:
        print(f"separate PR head: {receipt['pull_request_head_sha']}")
    print("CI: all four gates passed; deployment approval: NOT GRANTED")


if __name__ == "__main__":
    main()

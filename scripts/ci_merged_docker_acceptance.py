#!/usr/bin/env python3
"""Replay the pinned production-stack CI smoke against the actual merged source.

Run only inside an ephemeral GitHub Actions runner, after the nine exact source
PRs were merged by ci_merge_rehearsal.py. This reuses the established SmartPloy
CI fixture, rather than claiming that Docker checks on the CI harness branch
prove the nine-PR integrated API/frontend and migration are healthy.

All four commands are read from the previously verified main CI workflow;
they operate on fixture env/database/containers, not OVH or user accounts.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import yaml

REPOSITORY = "galapoto/smartploy"
BASE_SHA = "d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1"
STEPS = (
    "Prepare fixture production environment",
    "Run no-mutation production preflight",
    "Validate committed production policy",
    "Build and smoke production Compose stack",
)
REQUIRED_DOCKER_ASSERTIONS = (
    "scripts/migrate.py",
    "scripts/assert-healthy-stack.sh",
    "scripts/assert-running-images.sh",
    "scripts/backup.sh",
    "scripts/restore.sh",
    "scripts/release-evidence.sh",
    "external_actions_authorized",
    "POSTGRES_PASSWORD=ci-url-safe-random-password-1234567890",
)


def run_git(directory: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=directory, text=True
    ).strip()


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise RuntimeError("Refusing non-SmartPloy repository context")
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Only a disposable GitHub-hosted Actions runner is supported")

    runner = Path(os.environ["RUNNER_TEMP"]).resolve()
    checkout = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    merged = runner / "smartploy-nine-source-rehearsal"
    evidence = runner / "smartploy-rehearsal-summary.json"

    if not merged.is_dir() or not evidence.is_file():
        raise RuntimeError("Exact nine-source merge and receipt must succeed first")
    if run_git(checkout, "rev-parse", f"{BASE_SHA}^{{commit}}") != BASE_SHA:
        raise RuntimeError("Pinned source main commit is unavailable")
    if run_git(merged, "rev-parse", "--is-inside-work-tree") != "true":
        raise RuntimeError("Missing merged Git worktree")

    import json

    receipt = json.loads(evidence.read_text(encoding="utf-8"))
    actual_head = run_git(merged, "rev-parse", "HEAD")
    actual_tree = run_git(merged, "rev-parse", "HEAD^{tree}")
    if (
        receipt.get("main_baseline") != BASE_SHA
        or receipt.get("final_ephemeral_commit") != actual_head
        or receipt.get("final_tree_sha") != actual_tree
        or receipt.get("never_pushed") is not True
        or receipt.get("production_unmodified") is not True
        or len(receipt.get("merges", [])) != 9
    ):
        raise RuntimeError("Merged-source receipt does not match Git worktree")

    # Read the existing committed main job exactly, not unreviewed workflow
    # snippets on the helper branch or a changed incoming PR.
    workflow = subprocess.check_output(
        ["git", "show", f"{BASE_SHA}:.github/workflows/ci.yml"],
        cwd=merged,
        text=True,
    )
    config = yaml.safe_load(workflow)
    job_steps = config["jobs"]["deploy-stack"]["steps"]
    selected = [
        step for step in job_steps if step.get("name") in STEPS
    ]
    if [step["name"] for step in selected] != list(STEPS):
        raise RuntimeError("Original Docker fixture steps changed or are incomplete")
    for step in selected:
        if not isinstance(step.get("run"), str) or not step["run"].strip():
            raise RuntimeError("Expected shell step missing in pinned main workflow")
    scripts = "\n".join(step["run"] for step in selected)
    if not all(item in scripts for item in REQUIRED_DOCKER_ASSERTIONS):
        raise RuntimeError("Pinned original CI no longer exercises all required gates")

    # The verified existing CI script already installs a trap to remove only
    # the fixture Docker Compose stack (never real /srv/obum containers).
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    for step in selected:
        print("MERGED-STACK FIXTURE START:", step["name"], flush=True)
        subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=merged,
            env=env,
            check=True,
        )
        print("MERGED-STACK FIXTURE PASS:", step["name"], flush=True)

    print("MERGED-STACK DOCKER/MIGRATION/BACKUP/RESTORE PASS", flush=True)
    print("INTEGRATED EPHEMERAL SHA:", actual_head, flush=True)
    print("INTEGRATED CODE TREE SHA:", actual_tree, flush=True)
    print("NO DEPLOYMENT TO OVH OR MAIN", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, KeyError, ValueError) as error:
        print("MERGED-STACK FIXTURE STOPPED:", str(error), file=sys.stderr, flush=True)
        sys.exit(2)

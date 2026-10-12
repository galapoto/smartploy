#!/usr/bin/env python3
"""Attest an EXACT, review-only SmartPloy source commit in independent CI jobs.

This helper never writes to the repository, production or user accounts.
Two independent ephemeral GitHub runners test the *same pinned Git commit and
tree* using actual application tests and the pre-existing main Docker fixture.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPOSITORY = "galapoto/smartploy"
BASE_MAIN = "d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1"
NINE_SOURCE_REVIEW = "60d18bbf9c8fed3cf5ad893b11b9d9122527e592"
CANDIDATE = "c51a784153ec5ddc67ca6bc665209ce5fe04fdda"
CANDIDATE_TREE = "bcd957962ebce471b26400b745bd20c8c9259810"
SOURCE_HEADS = (
    (112, "394ac40aa40a5433149657e85b9a0c7ab781986d"),
    (115, "c8a0905570e680d92590d9fdc74994d08fc9b699"),
    (117, "6ceb9b29e1914ebc5c335737fe1b0f5bf14e8028"),
    (119, "5f1cd20a55cc7c6a04b6c9b65cd0e28f2f559f22"),
    (121, "ba04e214ea1a3931eadc39157a7cafec9a53884a"),
    (123, "7f8d32ec8539b4a0a849d4ca881a8e62e8335ea2"),
    (125, "2f00bbe5d2f73426a58ed1de6c9492dbceb78c48"),
    (122, "6623f7308f3f9b926063b4733678fceefeef5e4c"),
    (118, "17e82ac9c5d4b92e5b2302f6ed704510e37e7a2f"),
    (128, CANDIDATE),
)
EXPECTED_SECURE_DELTA = frozenset({
    "smartploy/oidc.py", "tests/test_session_store_fail_closed.py",
})
DOCKER_STEPS = (
    "Prepare fixture production environment",
    "Run no-mutation production preflight",
    "Validate committed production policy",
    "Build and smoke production Compose stack",
)
DOCKER_REQUIRED = (
    "scripts/migrate.py", "scripts/assert-healthy-stack.sh",
    "scripts/assert-running-images.sh", "scripts/backup.sh",
    "scripts/restore.sh", "scripts/release-evidence.sh",
    "external_actions_authorized",
    "POSTGRES_PASSWORD=ci-url-safe-random-password-1234567890",
)


def fail(message: str) -> None:
    raise ValueError(message)


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=path, text=True,
    ).strip()


def environment_check() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        fail("Only a disposable GitHub-hosted Actions runner is supported")
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        fail("Unexpected GitHub repository")
    # Never run a workflow with write permissions or a live deploy key.
    if os.environ.get("SP10_NO_DEPLOY") != "true":
        fail("CI-only explicit no-deploy environment guard is required")


def ensure_candidate(candidate: Path) -> None:
    environment_check()
    if not (candidate / ".git").exists():
        fail("Expected separate, exact GitHub checkout")
    head = git(candidate, "rev-parse", "HEAD")
    tree = git(candidate, "rev-parse", "HEAD^{tree}")
    if head != CANDIDATE or tree != CANDIDATE_TREE:
        fail(f"Unexpected candidate source commit/tree: {head} / {tree}")
    # Build tools install untracked node_modules (the app has no checked-in
    # npm lockfile) and synthetic browser evidence in this checkout. Those
    # generated paths are expected AFTER tests. The executed, Git-tracked
    # application source must nevertheless stay byte-for-byte unchanged.
    dirty_tracked = git(candidate, "status", "--porcelain", "--untracked-files=no")
    if dirty_tracked:
        fail("Git-tracked candidate source changed during CI: " + dirty_tracked[:500])
    if git(candidate, "rev-parse", f"{BASE_MAIN}^{{commit}}") != BASE_MAIN:
        fail("Original main baseline unavailable")
    remote_main = git(candidate, "ls-remote", "origin", "refs/heads/main").split()
    if len(remote_main) != 2 or remote_main[0] != BASE_MAIN:
        fail("Main moved or its remote SHA is unverifiable")
    for number, sha in SOURCE_HEADS:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, CANDIDATE],
            cwd=candidate, check=True,
        )
        print(f"SOURCE-ANCESTRY PASS: PR #{number} {sha}", flush=True)
    git(candidate, "merge-base", "--is-ancestor", NINE_SOURCE_REVIEW, CANDIDATE)
    delta = frozenset(
        git(candidate, "diff", "--name-only", NINE_SOURCE_REVIEW, CANDIDATE).splitlines()
    )
    if delta != EXPECTED_SECURE_DELTA:
        fail(f"Security fix changed unexpected paths: {sorted(delta)}")
    if git(candidate, "rev-parse", f"{NINE_SOURCE_REVIEW}^{{tree}}") != (
        "7561381b2047ddce5416acfeb2124291a73f7402"
    ):
        fail("Previously independently tested nine-PR tree changed")
    print("CANDIDATE-REVIEW SOURCE PIN VERIFIED:", tree, flush=True)


def receipt(kind: str) -> dict:
    return {
        "format": "smartploy-ten-source-outage-attestation-v1",
        "purpose": kind,
        "repository": REPOSITORY,
        "main_baseline": BASE_MAIN,
        "reviewed_nine_source_parent": NINE_SOURCE_REVIEW,
        "commit_sha": CANDIDATE,
        "tree_sha": CANDIDATE_TREE,
        "sources": [{"pr": n, "sha": sha} for n, sha in SOURCE_HEADS],
        "tests_passed_in_same_job": True,
        "main_was_not_modified": True,
        "production_was_not_modified": True,
        "approved_for_merge": False,
        "approved_for_deployment": False,
    }


def write_receipt(kind: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt(kind), indent=2) + "\n", encoding="utf-8")
    print(f"CI {kind.upper()} COMPLETE FOR TREE:", CANDIDATE_TREE, flush=True)


def replay_pinned_docker_fixture(candidate: Path) -> None:
    ensure_candidate(candidate)
    import yaml

    source = git(candidate, "show", f"{BASE_MAIN}:.github/workflows/ci.yml")
    workflow = yaml.safe_load(source)
    original = workflow["jobs"]["deploy-stack"]["steps"]
    selected = [
        step for step in original if step.get("name") in DOCKER_STEPS
    ]
    if [step["name"] for step in selected] != list(DOCKER_STEPS):
        fail("Pinned original main Docker fixture steps differ unexpectedly")
    shell_commands = "\n".join(x["run"] for x in selected)
    if not all(part in shell_commands for part in DOCKER_REQUIRED):
        fail("Original Docker fixture lost required security/provenance controls")
    for step in selected:
        print("EXACT-CANDIDATE-DOCKER START:", step["name"], flush=True)
        subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=candidate,
            check=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        print("EXACT-CANDIDATE-DOCKER PASS:", step["name"], flush=True)
    print("EXACT-CANDIDATE DOCKER/MIGRATION/BACKUP/RESTORE: PASS", flush=True)


def validate_receipt(path: Path, expected: str) -> dict:
    if not path.is_file() or path.is_symlink():
        fail(f"Expected signed-by-CI artifact missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data != receipt(expected):
        fail(f"CI receipt source pin/claim mismatch: {path}")
    return data


def cross_attest(root: Path) -> None:
    environment_check()
    app = validate_receipt(root / "application" / "receipt.json", "application")
    docker = validate_receipt(root / "docker" / "receipt.json", "docker")
    if app["tree_sha"] != docker["tree_sha"]:
        fail("Two CI jobs tested different source trees")
    output = {
        "format": "smartploy-ten-source-provenance-v1",
        "commit_sha": CANDIDATE,
        "git_tree_sha": CANDIDATE_TREE,
        "source_heads": app["sources"],
        "independent_application_and_docker_tests_passed": True,
        "review_only": True,
        "main_merged": False,
        "production_deployed": False,
        "live_two_account_acceptance": False,
    }
    target = Path("sp10-outage-joined-evidence.json")
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print("CROSS-JOB EXACT SOURCE-TREE PROVENANCE: PASS", flush=True)
    print("EXACT CANDIDATE TREE:", CANDIDATE_TREE, flush=True)
    print("NOT REVIEW APPROVAL / NOT PRODUCTION DEPLOYMENT", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "docker", "receipt", "attest"))
    parser.add_argument("--candidate", default="candidate")
    parser.add_argument("--kind", choices=("application", "docker"))
    parser.add_argument("--output")
    parser.add_argument("--root", default="sp10-proof")
    args = parser.parse_args()
    if args.command == "attest":
        cross_attest(Path(args.root))
        return
    candidate = Path(args.candidate).resolve()
    if args.command == "verify":
        ensure_candidate(candidate)
    elif args.command == "docker":
        replay_pinned_docker_fixture(candidate)
    elif args.command == "receipt":
        if not args.kind or not args.output:
            fail("Receipt requires --kind and --output")
        ensure_candidate(candidate)
        write_receipt(args.kind, Path(args.output))


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError, OSError, subprocess.CalledProcessError, KeyError, TypeError,
        json.JSONDecodeError, AttributeError,
    ) as error:
        print("TEN-SOURCE PROVENANCE BLOCKED:", str(error), file=sys.stderr, flush=True)
        sys.exit(2)

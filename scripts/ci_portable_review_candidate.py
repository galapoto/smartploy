#!/usr/bin/env python3
"""Package the EXACT CI-verified nine-source Git tree for offline review.

The package is an immutable Actions artifact, not a GitHub branch or a
production deployment. Creation is gated by completed application, Docker
and cross-runner source-tree verification. No credentials or real user data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

from ci_merge_rehearsal import MAIN, REPO, SOURCES


def git(worktree: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=worktree, text=True
    ).strip()


def fail(message: str) -> None:
    raise ValueError(message)


def require_provenance(receipt: dict, joined: dict, worktree: Path) -> tuple[str, str]:
    head = git(worktree, "rev-parse", "HEAD")
    tree = git(worktree, "rev-parse", "HEAD^{tree}")
    expected_sources = [{"pr": number, "source_head": sha} for number, sha in SOURCES]

    if receipt.get("format") != "smartploy-nine-source-local-rehearsal-v1":
        fail("Unexpected merge receipt schema")
    if receipt.get("main_baseline") != MAIN or joined.get("main_baseline") != MAIN:
        fail("Pinned main SHA differs from attested main")
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not re.fullmatch(r"[0-9a-f]{40}", tree):
        fail("Invalid Git object SHA")
    if receipt.get("final_ephemeral_commit") != head:
        fail("Merged temporary commit differs from its receipt")
    if receipt.get("final_tree_sha") != tree:
        fail("Merged tree SHA differs from its receipt")
    if joined.get("identical_source_tree_sha") != tree:
        fail("NOT the source tree tested by both independent CI jobs")
    if joined.get("format") != "smartploy-nine-source-joined-evidence-v1":
        fail("Wrong cross-job attestation contract")
    if joined.get("source_pr_count") != len(SOURCES):
        fail("Wrong source PR count")
    if joined.get("application_and_docker_jobs_both_passed") is not True:
        fail("Application and Docker CI approvals are missing")
    if joined.get("deployment_approved") is not False:
        fail("CI receipt unexpectedly suggests deployment authorization")
    if receipt.get("never_pushed") is not True:
        fail("CI receipt unexpectedly claims code push")
    if receipt.get("production_unmodified") is not True:
        fail("CI receipt unexpectedly claims production mutation")
    actual_sources = [
        {"pr": record["pr"], "source_head": record["source_head"]}
        for record in receipt.get("merges", [])
    ]
    if actual_sources != expected_sources:
        fail("Expected exactly nine pinned source PRs in order")
    for _, source_sha in SOURCES:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_sha, head],
            cwd=worktree, check=True,
        )
    if git(worktree, "status", "--porcelain"):
        fail("Temporary merged checkout is not clean")
    if (worktree / "scripts/ci_merge_rehearsal.py").exists():
        fail("The merged release checkout unexpectedly includes CI-only harness")
    return head, tree


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        fail("Package creation requires exact SmartPloy repository")
    if os.environ.get("GITHUB_ACTIONS") != "true":
        fail("Only an isolated GitHub Actions runner is supported")
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    runner = Path(os.environ["RUNNER_TEMP"]).resolve()
    worktree = runner / "smartploy-nine-source-rehearsal"
    receipt_path = runner / "smartploy-rehearsal-summary.json"
    joined_path = workspace / "sp10-joined-evidence.json"

    if not worktree.is_dir() or not receipt_path.is_file() or not joined_path.is_file():
        fail("Missing merged worktree or independent CI attestation")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    joined = json.loads(joined_path.read_text(encoding="utf-8"))
    head, tree = require_provenance(receipt, joined, worktree)

    output = workspace / "sp10-offline-release-candidate"
    output.mkdir(mode=0o700, exist_ok=False)
    bundle_path = output / "smartploy-nine-source-review.bundle"
    source_path = output / "smartploy-nine-source-source.tar.gz"

    # A complete, portable Git history preserving source PR merge ancestry.
    subprocess.run(
        ["git", "bundle", "create", str(bundle_path), "HEAD"],
        cwd=worktree, check=True,
    )
    subprocess.run(
        ["git", "bundle", "verify", str(bundle_path)],
        cwd=worktree, check=True,
        stdout=subprocess.DEVNULL,
    )
    bundle_head = git(worktree, "bundle", "list-heads", str(bundle_path)).splitlines()
    if f"{head} HEAD" not in bundle_head:
        fail("Git bundle does not point to exact verified merge head")

    # Reviewable tree snapshot without .git, run-time env, server DB or tokens.
    script = 'git archive --format=tar HEAD | gzip -n -9 > "$1"'
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script, "bash", str(source_path)],
        cwd=worktree, check=True,
    )

    # Check archive paths and forbid accidentally tracked operator secrets.
    forbidden = {
        ".env", ".env.production", "deploy/personal/env",
        "config/public_ats_sources.json", ".secrets",
    }
    with tarfile.open(source_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            fail("Archived Git source is empty")
        for item in members:
            name = item.name.rstrip("/")
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or name in forbidden
                or name.startswith(".secrets/")
            ):
                fail("Unacceptable source path inside portable snapshot")
            if item.issym() or item.islnk():
                target = PurePosixPath(item.linkname)
                if target.is_absolute() or ".." in target.parts:
                    fail("Unsafe archive link target")

    manifest = {
        "format": "smartploy-nine-source-portable-review-v1",
        "repository": REPO,
        "main_baseline": MAIN,
        "merged_source_tree_sha": tree,
        "review_bundle_head_commit_sha": head,
        "source_prs": [{"number": n, "sha": sha} for n, sha in SOURCES],
        "artifacts": {
            bundle_path.name: {"sha256": digest(bundle_path), "bytes": bundle_path.stat().st_size},
            source_path.name: {"sha256": digest(source_path), "bytes": source_path.stat().st_size},
        },
        "ci_source_tree_verified": True,
        "approved_for_main_merge": False,
        "approved_for_ovh_deploy": False,
        "production_sign_in_acceptance_done": False,
        "offline_review_only": True,
    }
    manifest_path = output / "REVIEW-MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    sha_path = output / "SHA256SUMS"
    sha_path.write_text(
        "".join(
            f"{digest(p)}  {p.name}\n"
            for p in (bundle_path, source_path, manifest_path)
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["sha256sum", "--check", sha_path.name],
        cwd=output, check=True,
    )
    for path in (bundle_path, source_path, manifest_path, sha_path):
        path.chmod(0o600)
    print("CI-ATTESTED PORTABLE REVIEW CANDIDATE: PASS", flush=True)
    print("Nine-PR tested Git tree:", tree, flush=True)
    print("Portable bundle Git HEAD:", head, flush=True)
    print("REVIEW ONLY: cannot merge or deploy without owner authorization", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, json.JSONDecodeError, tarfile.TarError) as exc:
        print("PORTABLE REVIEW CANDIDATE REJECTED:", str(exc), file=sys.stderr, flush=True)
        sys.exit(2)

#!/usr/bin/env python3
"""Compare independent GitHub runner receipts for one exact SmartPloy tree.

The application and Docker CI jobs run in separate ephemeral worktrees.
Their merge commit SHAs may differ due to timestamps; their final *Git
tree* objects must match byte-for-byte for a valid joined release receipt.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from ci_merge_rehearsal import MAIN, REPO, SOURCES

ROOT = Path("sp10-proof")
APP_RECEIPT = ROOT / "application" / "smartploy-rehearsal-summary.json"
DOCKER_RECEIPT = ROOT / "docker" / "smartploy-rehearsal-summary.json"


def valid_receipt(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing trusted CI receipt at {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    sha = data.get("final_tree_sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(f"Missing source-tree object hash from {path}")
    if data.get("main_baseline") != MAIN:
        raise ValueError(f"Unexpected main baseline in {path}")
    if data.get("format") != "smartploy-nine-source-local-rehearsal-v1":
        raise ValueError(f"Unrecognized CI receipt format in {path}")
    if data.get("never_pushed") is not True or data.get("production_unmodified") is not True:
        raise ValueError(f"CI receipt lacks no-push safety flags: {path}")

    merged = data.get("merges")
    actual = (
        [(x.get("pr"), x.get("source_head")) for x in merged]
        if isinstance(merged, list) and all(isinstance(x, dict) for x in merged)
        else None
    )
    if actual != list(SOURCES):
        raise ValueError(f"Nonspecific, missing or modified source PR refs in {path}")

    return data


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise ValueError("This receipt is only for galapoto/smartploy")
    app = valid_receipt(APP_RECEIPT)
    docker = valid_receipt(DOCKER_RECEIPT)
    if app["final_tree_sha"] != docker["final_tree_sha"]:
        raise ValueError(
            "Application and Docker checks ran on DIFFERENT file trees; block release"
        )

    result = {
        "format": "smartploy-nine-source-joined-evidence-v1",
        "main_baseline": MAIN,
        "identical_source_tree_sha": app["final_tree_sha"],
        "source_pr_count": len(SOURCES),
        "application_and_docker_jobs_both_passed": True,
        "deployment_approved": False,
        "owner_signed_in_acceptance_completed": False,
    }
    Path("sp10-joined-evidence.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print("APP-AND-DOCKER TREE ATTESTATION: PASS", flush=True)
    print("Identical nine-source tree:", app["final_tree_sha"], flush=True)
    print("Real production deployment and A1-A7 browser acceptance: NOT PERFORMED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("TREE ATTESTATION FAILED:", str(exc), file=sys.stderr, flush=True)
        sys.exit(2)

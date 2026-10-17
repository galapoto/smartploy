#!/usr/bin/env python3
"""Fail-closed source identity and CI test receipt for isolated Woodpecker.

Not a security review, staging approval, production deploy or model request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

REPOSITORY = "galapoto/smartploy"
SHA = re.compile(r"[0-9a-f]{40}\Z")
FORMAT = "smartploy.obumdelivery.product-test.v1"
OUT = Path(".ci-out/obumdelivery")
STAGES = ("python-postgres", "web-browser")


class AdmissionDenied(ValueError):
    pass


def qualify(repo: str, claimed: str, checkout: str, tree: str) -> dict:
    if repo != REPOSITORY:
        raise AdmissionDenied("WRONG_PRODUCT_REPOSITORY")
    for name, value in (("CLAIM", claimed), ("CHECKOUT", checkout), ("TREE", tree)):
        if not isinstance(value, str) or SHA.fullmatch(value) is None:
            raise AdmissionDenied("INVALID_" + name + "_SHA")
    if claimed != checkout:
        raise AdmissionDenied("CI_CHECKOUT_SHA_MISMATCH")
    return {
        "schema": FORMAT, "repository": repo,
        "source_sha": checkout, "source_tree_sha": tree,
        "source_provenance": "WOODPECKER_METADATA_AND_LOCAL_GIT",
        "synthetic_only": True, "production_changed": False,
        "model_dispatch_executed": False,
        "employer_actions_authorized": False,
        "release_approved": False, "release_gate": "HOLD",
    }


def current() -> dict:
    if os.environ.get("CI_NEGATIVE_PROBE", "") == "1":
        raise AdmissionDenied("EXPECTED_RED_NEGATIVE_PROBE")
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.DEVNULL,
        ).strip()
    return qualify(
        os.environ.get("CI_REPO", ""),
        os.environ.get("CI_COMMIT_SHA", ""),
        git("rev-parse", "HEAD"),
        git("rev-parse", "HEAD^{tree}"),
    )


def directory(root: Path) -> Path:
    result = root / OUT
    if result.parent.is_symlink() or result.is_symlink():
        raise AdmissionDenied("RECEIPT_SYMLINK")
    result.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not result.is_dir() or result.is_symlink():
        raise AdmissionDenied("RECEIPT_DIRECTORY_INVALID")
    return result


def safe_write(path: Path, payload: dict) -> None:
    if path.exists() or path.is_symlink():
        raise AdmissionDenied("RECEIPT_WOULD_OVERWRITE")
    data = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    if len(data) > 16000:
        raise AdmissionDenied("RECEIPT_TOO_LARGE")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as writer:
        writer.write(data)


def safe_read(path: Path) -> dict:
    if path.is_symlink():
        raise AdmissionDenied("RECEIPT_SYMLINK")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 16000:
        raise AdmissionDenied("RECEIPT_TYPE_OR_SIZE")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise AdmissionDenied("RECEIPT_INVALID")
    return result


def mark(root: Path, stage: str, source: dict) -> Path:
    if stage not in STAGES:
        raise AdmissionDenied("UNKNOWN_CI_STAGE")
    path = directory(root) / (stage + ".json")
    safe_write(path, {
        **source, "stage": stage, "stage_passed": True,
        "result_source": "SEQUENTIAL_WOODPECKER_STEP_EXIT_CODE",
        "production_deployment_executed": False,
    })
    return path


def summarize(root: Path, source: dict) -> dict:
    base = root / OUT
    if base.is_symlink():
        raise AdmissionDenied("RECEIPT_SYMLINK")
    evidence = {}
    for stage in STAGES:
        path = base / (stage + ".json")
        expected = {
            **source, "stage": stage, "stage_passed": True,
            "result_source": "SEQUENTIAL_WOODPECKER_STEP_EXIT_CODE",
            "production_deployment_executed": False,
        }
        if safe_read(path) != expected:
            raise AdmissionDenied("STAGE_IDENTITY_OR_POLICY_STOP:" + stage)
        evidence[stage] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        **source, "stage_receipts_sha256": evidence,
        "synthetic_python_postgres_tests_passed": True,
        "synthetic_web_browser_tests_passed": True,
        "production_docker_compose_smoke_executed": False,
        "production_backup_restored": False,
        "live_ovh_deployment_verified": False,
        "independent_security_review": False,
        "staging_or_production_deploy_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "mark-python", "mark-browser", "final"))
    args = parser.parse_args()
    try:
        source = current()
        if args.action == "validate":
            print(json.dumps(source, sort_keys=True))
        elif args.action in ("mark-python", "mark-browser"):
            stage = "python-postgres" if args.action == "mark-python" else "web-browser"
            print("STAGE_RECEIPT=" + str(mark(Path.cwd(), stage, source)))
        else:
            receipt = summarize(Path.cwd(), source)
            path = directory(Path.cwd()) / "product-test-receipt.json"
            safe_write(path, receipt)
            print(json.dumps(receipt, sort_keys=True))
        return 0
    except (AdmissionDenied, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("OBUMDELIVERY_PRODUCT_CI_HOLD: " + str(exc), file=sys.stderr)
        return 41 if str(exc) == "EXPECTED_RED_NEGATIVE_PROBE" else 3


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())

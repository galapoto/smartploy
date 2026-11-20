"""Read-only FEATURE-FIRST-001 OVH commissioning diagnostic.

Prints safe PASS/HOLD/UNVERIFIED facts; never reads or prints credentials,
mutates receipts, writes files, deploys, changes SSH or infers approval.
Run from the trusted host as root for complete permission checks:
  sudo python3 scripts/feature_first_prod_readiness.py --candidate-sha <full-main-sha>
The default exit status is zero for a completed diagnostic even when held;
--require-host-gates returns 42 if any *host-side* required check fails.
This is NOT a release actor, approval receipt or production certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
from typing import Any
from urllib.request import Request, urlopen


SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
REVISION_RE = re.compile(r"[0-9a-f]{12,40}\Z")
DEFAULT_REPO = Path("/srv/obum/stacks/smartploy")
DEFAULT_STATE = Path("/srv/obum/data/smartploy/deploy-state")
SSH_GATE = Path("/usr/local/libexec/smartploy-feature-first-ssh-gate")
DISPATCHER = Path("/usr/local/sbin/smartploy-feature-first-dispatch")
SERVICE_USER = "smartploy-cd"
PUBLIC_HEALTH = "https://smartploy.komplyint.fi/healthz"

# Tests can call inspect() with a temporary tree, but only the canonical
# approved paths are used on the real host. No candidate can write a receipt.
BLOCKING_GATES = (
    "root_context", "production_env", "production_deploy_script",
    "trusted_state_dir", "ssh_gate_root_owned", "dispatcher_root_owned",
    "ssh_gate_source_match", "dispatcher_source_match",
    "service_user_exists", "service_key_restricted",
    "production_checkout_clean", "candidate_on_main",
    "native_ci_exact_sha", "independent_release_approval",
)


def _result(status: str, note: str) -> dict[str, str]:
    return {"status": status, "note": note}


def _owned_file(path: Path) -> bool:
    try:
        info = path.lstat()
        return (
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and info.st_mode & 0o022 == 0
            and info.st_nlink == 1
        )
    except OSError:
        return False


def _owned_directory(path: Path) -> bool:
    try:
        info = path.lstat()
        return (stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and info.st_mode & 0o022 == 0)
    except OSError:
        return False


def _root_receipt_matches(path: Path, expected_sha: str | None) -> bool:
    if not expected_sha or not SHA_RE.fullmatch(expected_sha):
        return False
    if not _owned_file(path):
        return False
    try:
        return path.read_text(encoding="ascii").strip() == expected_sha
    except (OSError, UnicodeError):
        return False


def _same_source(trusted: Path, candidate: Path) -> bool:
    if not _owned_file(trusted) or not candidate.is_file():
        return False
    try:
        return (
            hashlib.sha256(trusted.read_bytes()).digest()
            == hashlib.sha256(candidate.read_bytes()).digest()
        )
    except OSError:
        return False


def _run_git(repo: Path, *args: str) -> tuple[bool, str]:
    """Never fetch, mutate checkout or output git error streams."""
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=6, check=False,
        )
        if completed.returncode == 0:
            return True, completed.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False, ""


def _forced_ssh_key_exists(home: Path) -> bool:
    ssh_dir = home / ".ssh"
    keyfile = ssh_dir / "authorized_keys"
    if not (_owned_directory(home) and _owned_directory(ssh_dir)
            and _owned_file(keyfile)):
        return False
    try:
        # Do not return keys/lines, merely count lines with exactly the
        # reviewed restriction prefix and without other active SSH keys.
        active = [
            line.strip() for line in keyfile.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(active) != 1:
            return False
        line = active[0]
        return (
            line.startswith(
                'restrict,command="/usr/local/libexec/'
                'smartploy-feature-first-ssh-gate" ssh-ed25519 '
            )
            and len(line.split()) >= 3
        )
    except (OSError, UnicodeError):
        return False


def _public_revision() -> str | None:
    try:
        req = Request(PUBLIC_HEALTH, headers={"Accept": "application/json"})
        with urlopen(req, timeout=5) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read(16_384))
        revision = data.get("release_revision")
        if (data.get("ok") is True and isinstance(revision, str)
                and REVISION_RE.fullmatch(revision)):
            return revision
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        pass
    return None


def inspect(
    repo: Path = DEFAULT_REPO,
    state: Path = DEFAULT_STATE,
    candidate: str | None = None,
    online: bool = False,
) -> dict[str, Any]:
    checks: dict[str, dict[str, str]] = {}

    def mark(name: str, okay: bool, yes: str, no: str) -> None:
        checks[name] = _result("PASS" if okay else "HOLD", yes if okay else no)

    candidate_valid = isinstance(candidate, str) and SHA_RE.fullmatch(candidate)
    mark("root_context", os.geteuid() == 0,
         "Root can inspect approved host receipts", "Run through authorized sudo on the production host")
    mark("production_env", (repo / "deploy/personal/env").is_file(),
         "Existing private deployment settings found", "Production env file not accessible")
    mark("production_deploy_script",
         (repo / "deploy/personal/scripts/deploy.sh").is_file(),
         "Existing guarded deploy.sh found", "Guarded deploy.sh not accessible")
    mark("trusted_state_dir", _owned_directory(state),
         "Private root-owned deploy state exists", "Root-owned private deploy-state directory absent/unsafe")

    source_gate = repo / "deploy/personal/scripts/feature-first-ssh-gate.sh"
    source_dispatch = repo / "deploy/personal/scripts/feature-first-remote-promotion.sh"
    mark("ssh_gate_root_owned", _owned_file(SSH_GATE),
         "Forced-command gate installed with safe ownership", "Root-owned forced-command gate missing/unsafe")
    mark("dispatcher_root_owned", _owned_file(DISPATCHER),
         "Dispatcher installed with safe ownership", "Root-owned dispatcher missing/unsafe")
    mark("ssh_gate_source_match", _same_source(SSH_GATE, source_gate),
         "Installed gate matches reviewed checkout", "Gate differs from checked-out source or is missing")
    mark("dispatcher_source_match", _same_source(DISPATCHER, source_dispatch),
         "Installed dispatcher matches reviewed checkout", "Dispatcher differs from checked-out source or is missing")
    try:
        member = pwd.getpwnam(SERVICE_USER)
    except KeyError:
        member = None
    mark("service_user_exists", member is not None,
         "Dedicated deployment SSH account found", "Dedicated deployment account missing")
    mark("service_key_restricted", bool(member and _forced_ssh_key_exists(Path(member.pw_dir))),
         "Only one root-controlled forced-command key entry exists",
         "Deployment SSH authorized key is missing, unsafe or unrestricted")

    clean, changes = _run_git(repo, "status", "--porcelain", "--untracked-files=no")
    mark("production_checkout_clean", clean and not changes,
         "Production tracked checkout clean", "Checkout dirty or git inaccessible")

    on_main = False
    if candidate_valid:
        exists, _ = _run_git(repo, "cat-file", "-e", f"{candidate}^{{commit}}")
        ancestor, _ = _run_git(
            repo, "merge-base", "--is-ancestor", candidate, "refs/remotes/origin/main"
        )
        on_main = exists and ancestor
    mark("candidate_on_main", bool(candidate_valid and on_main),
         "Exact candidate is in host's fetched origin/main history",
         "No exact eligible SHA, or commit not confirmed in host's origin/main history")

    mark("native_ci_exact_sha", bool(candidate_valid and _root_receipt_matches(
        state / "native-ci-qualified-sha", candidate)),
         "Root-owned native CI receipt matches SHA", "Native Woodpecker exact-SHA proof missing/unsafe")
    approval = (
        bool(candidate_valid and _root_receipt_matches(
            state / "feature-first-auto-eligible-sha", candidate))
        or bool(candidate_valid and _root_receipt_matches(
            state / "feature-first-approved-sha", candidate))
    )
    mark("independent_release_approval", approval,
         "Root-owned independent release approval matches SHA",
         "Independent feature risk/approval receipt missing")

    previous: str | None = None
    deployed_file = state / "deployed-sha"
    try:
        if _owned_file(deployed_file):
            value = deployed_file.read_text(encoding="ascii").strip()
            if SHA_RE.fullmatch(value):
                previous = value
    except (OSError, UnicodeError):
        pass

    revision = _public_revision() if online else None
    checks["public_health"] = _result(
        "PASS" if revision else "UNVERIFIED",
        "Public health returned a revision" if revision else
        "Pass --online for read-only public health; does not prove signed-in acceptance",
    )
    holds = [name for name in BLOCKING_GATES if checks[name]["status"] != "PASS"]
    return {
        "schema": "smartploy.feature_first.host_diagnostic.v1",
        "status": "HOST_GATES_PRESENT" if not holds else "HOLD",
        "candidate_sha": candidate if candidate_valid else None,
        "deployed_sha": previous,
        "public_health_revision": revision,
        "checks": checks,
        "host_blockers": holds,
        "external_gates": {
            "github_protected_main_review": "NOT_VERIFIED",
            "github_production_environment": "NOT_VERIFIED",
            "native_runner_signed_execution": "NOT_VERIFIED",
            "actual_signed_in_user_journey": "NOT_VERIFIED",
        },
        "note": "Read-only diagnostic, NOT a deployment or release approval",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SmartPloy host deployment readiness")
    parser.add_argument("--candidate-sha", default=None)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--require-host-gates", action="store_true")
    args = parser.parse_args()
    report = inspect(repo=args.repo, state=args.state_dir,
                     candidate=args.candidate_sha, online=args.online)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 42 if args.require_host_gates and report["status"] != "HOST_GATES_PRESENT" else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""CI-only, read-only GitHub checkout rehearsal for nine pinned SmartPloy PRs.

This script merges exact fetched source heads into a detached temporary worktree.
It never pushes, never touches main or OVH, never substitutes PR #120 for the
source merges, and stops at unexpected conflicts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = "galapoto/smartploy"
MAIN = "d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1"
SOURCES = (
    (112, "394ac40aa40a5433149657e85b9a0c7ab781986d"),
    (115, "c8a0905570e680d92590d9fdc74994d08fc9b699"),
    (117, "6ceb9b29e1914ebc5c335737fe1b0f5bf14e8028"),
    (119, "5f1cd20a55cc7c6a04b6c9b65cd0e28f2f559f22"),
    (121, "ba04e214ea1a3931eadc39157a7cafec9a53884a"),
    (123, "7f8d32ec8539b4a0a849d4ca881a8e62e8335ea2"),
    (125, "2f00bbe5d2f73426a58ed1de6c9492dbceb78c48"),
    (122, "6623f7308f3f9b926063b4733678fceefeef5e4c"),
    (118, "17e82ac9c5d4b92e5b2302f6ed704510e37e7a2f"),
)

# Verified separately: these five substitutions reproduce PR #121's API
# byte-for-byte when applied to its common-ancestor main API.
ACCOUNT_GUARDS = (
    (
        '    app = FastAPI(title="Smartploy API", version="0.5.0")',
        '    resolved_identities = identity_repository or _build_identity_repository()\n'
        '    app = FastAPI(title="Smartploy API", version="0.5.0")',
    ),
    (
        '        sessions=sessions,\n'
        '        access_settings=access_settings,\n'
        '        access_verifier=access_verifier,',
        '        sessions=sessions,\n'
        '        access_settings=access_settings,\n'
        '        identity_repository=resolved_identities,\n'
        '        access_verifier=access_verifier,',
    ),
    (
        '    app.state.identity_repository = identity_repository or _build_identity_repository()',
        '    app.state.identity_repository = resolved_identities',
    ),
    (
        '        binding = app.state.identity_repository.resolve_or_create(principal)\n'
        '        request.state.smartploy_binding = binding\n\n'
        '        cached = app.state.tenant_services.get(binding.profile_id)',
        '''        binding = getattr(request.state, "smartploy_binding", None)
        if not isinstance(binding, UserProfileBinding):
            # Auth-disabled fixtures have no verified principal; otherwise
            # request middleware must have validated and bound this account.
            if authentication.mode != "disabled":
                raise HTTPException(status_code=503, detail="Verified account binding is unavailable")
            binding = app.state.identity_repository.resolve_or_create(principal)
        if binding.status != "active":
            raise HTTPException(status_code=403, detail="SmartPloy account access is disabled")
        request.state.smartploy_binding = binding

        cached = app.state.tenant_services.get(binding.profile_id)''',
    ),
    (
        '        binding = app.state.identity_repository.resolve_or_create(principal)\n'
        '        issued = await asyncio.to_thread(\n'
        '            sessions.create,',
        '''        binding = await asyncio.to_thread(
            app.state.identity_repository.resolve_or_create, principal
        )
        if binding.status != "active":
            raise HTTPException(
                status_code=403, detail="SmartPloy account access is disabled",
                headers={"Cache-Control": "no-store"},
            )
        issued = await asyncio.to_thread(
            sessions.create,''',
    ),
)


class RehearsalError(RuntimeError):
    pass


def git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if result.returncode and check:
        raise RehearsalError(
            f"git {' '.join(args[:4])}: {result.returncode}\n"
            f"{result.stdout[-1800:]}\n{result.stderr[-1800:]}"
        )
    return result


def show_stage(worktree: Path, stage: int, path: str) -> bytes:
    return git("show", f":{stage}:{path}", cwd=worktree).stdout.encode("utf-8")


def resolve_docs(worktree: Path) -> None:
    path = "docs/WEB.md"
    base, ours, theirs = (show_stage(worktree, n, path) for n in (1, 2, 3))
    if not (ours.startswith(base) and theirs.startswith(base)):
        raise RehearsalError("Docs conflict is NOT safe append-only; human review required")
    our_suffix, their_suffix = ours[len(base):], theirs[len(base):]
    def headings(data: bytes) -> set[bytes]:
        return set(re.findall(rb"(?m)^## (.+)$", data))
    if not their_suffix.lstrip().startswith(b"## ") or headings(our_suffix) & headings(their_suffix):
        raise RehearsalError("Unexpected or duplicate documentation headings")
    (worktree / path).write_bytes(ours + their_suffix)
    git("add", path, cwd=worktree)
    print("RESOLVED append-only docs conflict, preserved both suffixes", flush=True)


def replay_account_guards(src: str) -> str:
    for before, after in ACCOUNT_GUARDS:
        if src.count(before) != 1:
            raise RehearsalError("Missing/nonunique account guard anchor: " + before[:68])
        src = src.replace(before, after, 1)
    return src


def resolve_pr121_api(worktree: Path) -> None:
    path = "smartploy/api.py"
    original, ours, theirs = (
        show_stage(worktree, n, path).decode("utf-8") for n in (1, 2, 3)
    )
    if replay_account_guards(original) != theirs:
        raise RehearsalError("PR #121 contains API changes beyond approved five substitutions")
    combined = replay_account_guards(ours)
    for invariant in (
        "resolved_identities",
        "identity_repository=resolved_identities",
        "SmartPloy account access is disabled",
        "Verified account binding is unavailable",
        "app.state.private_saved_jobs",
        "/api/v1/private-jobs",
        "app.state.operator_access",
        "require_shared_ingestion_operator",
    ):
        if invariant not in combined:
            raise RehearsalError("Merged API lost security invariant " + invariant)
    compile(combined, path, "exec")
    (worktree / path).write_text(combined, encoding="utf-8")
    git("add", path, cwd=worktree)
    print("RESOLVED PR121 verified identity guard, preserved private/operator APIs", flush=True)


def main() -> int:
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise RehearsalError("This runner is not the pinned SmartPloy repository")
    home = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    worktree = temp / "smartploy-nine-source-rehearsal"
    if worktree.exists():
        raise RehearsalError("Rehearsal directory already exists; refusing overwrite")

    git("fetch", "--quiet", "--no-tags", "origin", "main", cwd=home)
    remote_main = git("rev-parse", "FETCH_HEAD", cwd=home).stdout.strip()
    if remote_main != MAIN:
        raise RehearsalError(f"Main baseline moved: {remote_main}")

    for number, expected in SOURCES:
        ref = f"refs/remotes/source-rehearsal/pr-{number}"
        git(
            "fetch", "--quiet", "--no-tags", "origin",
            f"+refs/pull/{number}/head:{ref}", cwd=home
        )
        actual = git("rev-parse", ref, cwd=home).stdout.strip()
        if actual != expected:
            raise RehearsalError(f"PR #{number} moved; expected {expected}, got {actual}")
        print(f"PIN VERIFIED PR #{number} {actual}", flush=True)

    git("worktree", "add", "--detach", str(worktree), MAIN, cwd=home)
    git("config", "--local", "user.name", "SmartPloy CI merge rehearsal", cwd=worktree)
    git("config", "--local", "user.email", "ci-merge-rehearsal@users.noreply.github.com", cwd=worktree)
    git("config", "--local", "commit.gpgsign", "false", cwd=worktree)

    done = []
    for number, expected in SOURCES:
        ref = f"refs/remotes/source-rehearsal/pr-{number}"
        result = git("merge", "--no-ff", "--no-edit", ref, cwd=worktree, check=False)
        if result.returncode:
            unresolved = set(
                git("diff", "--name-only", "--diff-filter=U", cwd=worktree)
                .stdout.strip().splitlines()
            )
            print(f"PR #{number} conflicts: {sorted(unresolved)}", flush=True)
            allowed = {"docs/WEB.md"} | ({"smartploy/api.py"} if number == 121 else set())
            if not unresolved or not unresolved <= allowed:
                raise RehearsalError(
                    f"PR #{number} unexpected code conflict: {sorted(unresolved)}"
                )
            if "docs/WEB.md" in unresolved:
                resolve_docs(worktree)
            if "smartploy/api.py" in unresolved:
                resolve_pr121_api(worktree)
            if git("diff", "--name-only", "--diff-filter=U", cwd=worktree).stdout.strip():
                raise RehearsalError("Unresolved conflicts remain")
            git("diff", "--cached", "--check", cwd=worktree)
            git("commit", "--no-edit", cwd=worktree)
        if git("rev-parse", "MERGE_HEAD", cwd=worktree, check=False).returncode == 0:
            raise RehearsalError("Merge remains in progress")
        git("merge-base", "--is-ancestor", expected, "HEAD", cwd=worktree)
        sha = git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        done.append({"pr": number, "source_head": expected, "rehearsal_merge_sha": sha})
        print(f"MERGE PASS PR #{number}: {sha}", flush=True)

    git("diff", "--check", MAIN, "HEAD", cwd=worktree)
    if git("status", "--porcelain", cwd=worktree).stdout.strip():
        raise RehearsalError("Worktree not clean after final merge")
    final = git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
    final_tree = git("rev-parse", "HEAD^{tree}", cwd=worktree).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", final_tree):
        raise RehearsalError("Unexpected source tree object SHA")
    report = {
        "format": "smartploy-nine-source-local-rehearsal-v1",
        "main_baseline": MAIN,
        "final_ephemeral_commit": final,
        "final_tree_sha": final_tree,
        "merges": done,
        "never_pushed": True,
        "production_unmodified": True,
    }
    (temp / "smartploy-rehearsal-summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("ALL NINE SOURCE MERGES PASSED; WORKTREE=" + str(worktree), flush=True)
    print("EPHEMERAL REHEARSAL SHA=" + final, flush=True)
    print("MERGED CODE TREE SHA=" + final_tree, flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RehearsalError, OSError, subprocess.CalledProcessError) as exc:
        print("REHEARSAL STOPPED SAFELY: " + str(exc), file=sys.stderr, flush=True)
        sys.exit(2)

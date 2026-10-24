"""SP30: prove exact-SHA OVH release admission without touching OVH or Docker.

The test exercises the original Git checker with disposable local and bare Git
repositories. It never requires credentials, a production env or a network call.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy/personal/scripts/check-approved-source.sh"
DEPLOY = ROOT / "deploy/personal/scripts/deploy.sh"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.PIPE,
    ).strip()


def source_sandbox(tmp_path: Path) -> tuple[Path, Path, str]:
    repo = tmp_path / "smartploy"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git(repo, "config", "user.email", "synthetic@invalid.example")
    git(repo, "config", "user.name", "Synthetic Test Only")
    git(repo, "remote", "add", "origin", str(remote))
    script_dir = repo / "deploy/personal/scripts"
    script_dir.mkdir(parents=True)
    shutil.copyfile(GATE, script_dir / GATE.name)
    (repo / "README.md").write_text("reviewed source\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "synthetic reviewed source")
    git(repo, "push", "-u", "origin", "main")
    return repo, script_dir / GATE.name, git(repo, "rev-parse", "HEAD")


def run_gate(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["bash", str(script), *args], capture_output=True,
        text=True, check=False, timeout=15, env=env,
    )


def test_exact_reviewed_commit_passes_without_checking_out_or_leaking_env(tmp_path):
    repo, script, sha = source_sandbox(tmp_path)
    (repo / "deploy/personal/env").write_text(
        "PRIVATE_VALUE=synthetic-not-a-real-secret\n", encoding="utf-8",
    )
    before = git(repo, "rev-parse", "HEAD")
    result = run_gate(script, sha)
    assert result.returncode == 0, result.stderr
    assert "release_source_gate=PASS" in result.stdout
    assert "reviewed_release_sha=" + sha in result.stdout
    assert "PRIVATE_VALUE" not in result.stdout + result.stderr
    assert "synthetic-not-a-real-secret" not in result.stdout + result.stderr
    assert git(repo, "rev-parse", "HEAD") == before


def test_reviewed_ancestor_remains_eligible_when_remote_main_advances(tmp_path):
    repo, script, reviewed = source_sandbox(tmp_path)
    (repo / "README.md").write_text("newer unreviewed main change\n", encoding="utf-8")
    git(repo, "commit", "-am", "synthetic later change")
    git(repo, "push", "origin", "main")
    assert git(repo, "rev-parse", "HEAD") != reviewed
    result = run_gate(script, reviewed)
    assert result.returncode == 0, result.stderr
    # Source gate never silently upgrades an explicitly chosen commit to main.
    assert "reviewed_release_sha=" + reviewed in result.stdout


def test_moving_branch_or_missing_revision_never_admitted(tmp_path):
    _, script, sha = source_sandbox(tmp_path)
    for args in ((), ("main",), ("origin/main",), (sha[:12],), ("g" * 40,), (sha, "main")):
        result = run_gate(script, *args)
        assert result.returncode == 2, (args, result.stderr)
        assert "release_source_gate=PASS" not in result.stdout


def test_dirty_tracked_checkout_is_refused_without_changing_content(tmp_path):
    repo, script, sha = source_sandbox(tmp_path)
    original_head = git(repo, "rev-parse", "HEAD")
    contents = "operator local tracked change\n"
    (repo / "README.md").write_text(contents, encoding="utf-8")
    result = run_gate(script, sha)
    assert result.returncode != 0
    assert "tracked files changed" in result.stderr
    assert "release_source_gate=PASS" not in result.stdout
    assert (repo / "README.md").read_text(encoding="utf-8") == contents
    assert git(repo, "rev-parse", "HEAD") == original_head


def test_commit_outside_remote_main_is_refused(tmp_path):
    repo, script, _ = source_sandbox(tmp_path)
    git(repo, "checkout", "-b", "unreviewed")
    (repo / "README.md").write_text("synthetic side branch\n", encoding="utf-8")
    git(repo, "commit", "-am", "synthetic unreviewed side commit")
    unreviewed = git(repo, "rev-parse", "HEAD")
    result = run_gate(script, unreviewed)
    assert result.returncode != 0
    assert "not contained in remote main history" in result.stderr
    assert "release_source_gate=PASS" not in result.stdout
    assert git(repo, "rev-parse", "HEAD") == unreviewed


def test_release_source_gate_precedes_checkout_build_backup_and_migrations():
    deploy = DEPLOY.read_text(encoding="utf-8")
    selector = GATE.read_text(encoding="utf-8")
    guard_at = deploy.index('check-approved-source.sh" "${TARGET_REF}"')
    checkout_at = deploy.index('git checkout --detach "${TARGET_REF}"')
    build_at = deploy.index('"${COMPOSE[@]}" build --pull api web')
    backup_at = deploy.index('bash "${SCRIPT_DIR}/backup.sh"')
    migrate_at = deploy.index('python scripts/migrate.py')
    assert guard_at < checkout_at < build_at < backup_at < migrate_at
    assert "git checkout --detach --force" not in deploy
    assert 'TARGET_REF="${1:-}"' in deploy
    assert '"$TARGET_REF" =~ ^[0-9a-f]{40}$' in deploy
    assert "--untracked-files=no" in selector
    assert "merge-base --is-ancestor" in selector
    assert "fetch --no-tags origin main" in selector
    for path in (DEPLOY, GATE):
        subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)


def test_deploy_rejects_mutable_main_without_loading_private_configuration():
    result = subprocess.run(
        ["bash", str(DEPLOY), "main"], text=True, capture_output=True,
        check=False, timeout=5,
    )
    assert result.returncode == 2
    assert "immutable 40-character Git SHA" in result.stderr
    assert "Missing" not in result.stderr

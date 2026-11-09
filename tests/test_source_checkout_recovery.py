"""Source snapshot recovery: real local Git fixtures, no OVH, Docker or internet."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deploy/personal/scripts/recover-source-checkout.sh"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def stack(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(origin)], check=True, capture_output=True)
    git(origin, "config", "user.email", "fixture@invalid.example")
    git(origin, "config", "user.name", "Fixture")
    (origin / "deploy/personal/scripts").mkdir(parents=True)
    (origin / "deploy/personal/scripts/deploy.sh").write_text("#!/bin/bash\nexit 0\n")
    (origin / ".gitignore").write_text("deploy/personal/env\n")
    git(origin, "add", ".")
    git(origin, "commit", "-m", "approved fixture")
    approved = git(origin, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git(origin, "remote", "add", "origin", str(remote))
    git(origin, "push", "-u", "origin", "main")

    snapshot = tmp_path / "stack" / "smartploy"
    snapshot.mkdir(parents=True)
    config = snapshot / "deploy/personal"
    config.mkdir(parents=True)
    private = config / "env"
    private.write_text("POSTGRES_PASSWORD=synthetic-secret-never-print\n")
    private.chmod(0o600)
    target = tmp_path / "stack" / "smartploy-source"

    text = SOURCE.read_text(encoding="utf-8")
    text = text.replace("SNAPSHOT=/srv/obum/stacks/smartploy", f"SNAPSHOT={snapshot}")
    text = text.replace("RECOVERY=/srv/obum/stacks/smartploy-source", f"RECOVERY={target}")
    text = text.replace("REMOTE=https://github.com/galapoto/smartploy.git", f"REMOTE={remote}")
    command = tmp_path / "recover.sh"
    command.write_text(text, encoding="utf-8")
    return snapshot, target, private, remote, approved, command, origin


def run(stack, sha=None):
    _, _, _, _, approved, command, _ = stack
    return subprocess.run(
        ["bash", str(command), sha if sha is not None else approved],
        capture_output=True, text=True, timeout=15, check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def test_shell_valid():
    subprocess.run(["bash", "-n", str(SOURCE)], check=True)


def test_existing_private_env_is_staged_not_regenerated(stack):
    snapshot, target, env, _, sha, _, _ = stack
    initial = env.read_bytes()
    first = run(stack)
    assert first.returncode == 0, first.stderr
    assert "recovery=new_checkout_ready" in first.stdout
    assert f"source_sha={sha}" in first.stdout
    assert "production_unchanged=true" in first.stdout
    assert "synthetic-secret-never-print" not in first.stdout + first.stderr
    assert not (snapshot / ".git").exists()
    assert env.read_bytes() == initial
    assert git(target, "rev-parse", "HEAD") == sha
    assert (target / "deploy/personal/env").read_bytes() == initial
    assert stat.S_IMODE((target / "deploy/personal/env").stat().st_mode) == 0o600
    assert not list(snapshot.parent.glob(".smartploy-source-recovery.*"))
    second = run(stack)
    assert second.returncode == 0, second.stderr
    assert "recovery=existing_checkout_verified" in second.stdout
    assert git(target, "rev-parse", "HEAD") == sha


def test_invalid_revision_rejected_before_network_or_disk_change(stack):
    _, target, _, _, _, command, _ = stack
    for invalid in ("main", "a" * 12, "-", "z" * 40):
        result = subprocess.run(["bash", str(command), invalid], capture_output=True, text=True)
        assert result.returncode != 0
        assert "immutable 40-character" in result.stderr
        assert not target.exists()


def test_source_with_git_is_not_overwritten(stack):
    snapshot, target, _, _, _, _, _ = stack
    (snapshot / ".git").mkdir()
    git(snapshot, "init")
    result = run(stack)
    assert result.returncode != 0
    assert "already a Git checkout" in result.stderr
    assert not target.exists()


def test_missing_or_insecure_env_blocks_recovery(stack):
    snapshot, target, env, _, _, _, _ = stack
    env.unlink()
    assert "private env absent" in run(stack).stderr
    env.write_text("POSTGRES_PASSWORD=synthetic-secret-never-print\n")
    env.chmod(0o644)
    assert "readable by group" in run(stack).stderr
    env.unlink()
    env.symlink_to(snapshot / "test.env")
    assert "private env absent" in run(stack).stderr
    assert not target.exists()


def test_non_main_sha_rejected_and_no_target_or_secret_leak(stack):
    snapshot, target, _, _, _, _, origin = stack
    git(origin, "checkout", "-b", "not-main")
    (origin / "unreviewed.txt").write_text("different commit")
    git(origin, "add", ".")
    git(origin, "commit", "-m", "unreviewed fixture")
    outsider = git(origin, "rev-parse", "HEAD")
    result = run(stack, outsider)
    assert result.returncode != 0
    assert "absent from first-party main" in result.stderr
    assert not target.exists()
    assert not list(snapshot.parent.glob(".smartploy-source-recovery.*"))
    assert "synthetic-secret-never-print" not in result.stdout + result.stderr


def test_existing_target_never_overwritten(stack):
    _, target, _, _, _, _, _ = stack
    target.mkdir()
    marker = target / "operator-file"
    marker.write_text("KEEP")
    result = run(stack)
    assert result.returncode != 0
    assert "exists but is not a Git checkout" in result.stderr
    assert marker.read_text() == "KEEP"


def test_existing_checkout_with_different_env_requires_manual_reconciliation(stack):
    _, target, _, _, _, _, _ = stack
    assert run(stack).returncode == 0
    (target / "deploy/personal/env").write_text("POSTGRES_PASSWORD=different-private-config\n")
    result = run(stack)
    assert result.returncode != 0
    assert "private env differs" in result.stderr

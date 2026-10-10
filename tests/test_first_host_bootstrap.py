"""First-host bootstrap must be private, idempotent and preserve old data."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/personal/scripts/bootstrap-first-host.sh"
TEMPLATE = ROOT / "deploy/personal/env.example"
COMPOSE = ROOT / "deploy/personal/docker-compose.yml"


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "smartploy"
    scripts = root / "deploy/personal/scripts"
    scripts.mkdir(parents=True)
    (root / ".git").mkdir()
    shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
    shutil.copyfile(TEMPLATE, root / "deploy/personal/env.example")
    shutil.copyfile(COMPOSE, root / "deploy/personal/docker-compose.yml")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = info ]; then exit 0; fi\n"
        "if [ \"$1\" = volume ] && [ \"$2\" = inspect ]; then\n"
        "  if [ \"$MOCK_VOLUME_PRESENT\" = 1 ]; then exit 0; fi\n"
        "  exit 1\n"
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    env["MOCK_VOLUME_PRESENT"] = "0"
    return root, env


def run_bootstrap(root, env):
    return subprocess.run(
        ["bash", str(root / "deploy/personal/scripts" / SCRIPT.name)],
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def test_bootstrap_is_shell_valid():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_new_install_creates_private_env_without_secrets_in_output(sandbox):
    root, env = sandbox
    run = run_bootstrap(root, env)
    assert run.returncode == 0, run.stderr
    target = root / "deploy/personal/env"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    content = target.read_text(encoding="utf-8")
    password = re.search(r"^POSTGRES_PASSWORD=(.+)$", content, flags=re.MULTILINE)
    assert password and re.fullmatch(r"[A-Za-z0-9_-]{48,60}", password.group(1))
    assert password.group(1) not in run.stdout
    assert "OBUMAI_BASE_URL=\n" in content
    assert "SMARTPLOY_ACCESS_AUDIENCE=replace-with-smartploy-access-audience" in content
    assert "private_env=created_mode_600" in run.stdout
    again = run_bootstrap(root, env)
    assert again.returncode == 0
    assert again.stdout.strip() == "private_env=already_exists_untouched"
    assert target.read_text(encoding="utf-8") == content


def test_existing_database_volume_blocks_new_password(sandbox):
    root, env = sandbox
    env["MOCK_VOLUME_PRESENT"] = "1"
    run = run_bootstrap(root, env)
    assert run.returncode != 0
    assert "PostgreSQL volume already exists" in run.stderr
    assert not (root / "deploy/personal/env").exists()


def test_existing_symlink_is_refused(sandbox):
    root, env = sandbox
    target = root / "deploy/personal/env"
    target.symlink_to(root / "deploy/personal/env.example")
    run = run_bootstrap(root, env)
    assert run.returncode != 0
    assert "must never be a symlink" in run.stderr

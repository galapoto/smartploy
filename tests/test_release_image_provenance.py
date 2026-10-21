"""Verify the release image-ID gate independently of a live Docker daemon."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/personal/scripts/assert-running-images.sh"
EXPECTED_SHA = "1" * 40


def _sandbox(tmp_path):
    root = tmp_path / "smartploy"
    scripts = root / "deploy/personal/scripts"
    scripts.mkdir(parents=True)
    # Reuse the real immutable policy selector/validator, not a stub.
    shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
    for name in ("select-runtime-policy.sh", "validate-runtime-policy.sh"):
        shutil.copyfile(SCRIPT.parent / name, scripts / name)
    (root / "deploy/personal/env").write_text("SMARTPLOY_PROFILE_ID=default\n")
    for name in ("runtime.production.env", "runtime.oidc.production.env"):
        shutil.copyfile(ROOT / "deploy/personal" / name, root / "deploy/personal" / name)
    (root / "deploy/personal/docker-compose.yml").write_text(
        "name: smartploy\nservices:\n  api:\n    image: image\n"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(
        """#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
if args[:2] == ['image', 'inspect']:
    image = args[-1]
    if image == 'smartploy-api:' + ('1' * 12):
        print('sha256:' + 'a' * 64)
        sys.exit(0)
    if image == 'smartploy-web:' + ('1' * 12):
        print('sha256:' + 'b' * 64)
        sys.exit(0)
    sys.exit(1)

if args[0] == 'compose' and 'ps' in args:
    service = args[-1]
    ids = {'api': 'c' * 64, 'worker': 'd' * 64, 'web': 'e' * 64}
    if service in ids:
        print(ids[service])
        sys.exit(0)
    sys.exit(1)

if args[:2] == ['inspect', '--format']:
    container = args[-1]
    if container == 'c' * 64:
        print('sha256:' + 'a' * 64)
        sys.exit(0)
    if container == 'd' * 64:
        print('sha256:' + ('f' if os.getenv('MOCK_STALE') == 'worker' else 'a') * 64)
        sys.exit(0)
    if container == 'e' * 64:
        print('sha256:' + 'b' * 64)
        sys.exit(0)

sys.exit(2)
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env.pop("SMARTPLOY_PRODUCTION_IDENTITY_MODE", None)
    return root, env


def _run(root, env, sha=EXPECTED_SHA):
    script = root / "deploy/personal/scripts" / SCRIPT.name
    return subprocess.run(
        ["bash", str(script), sha],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_image_provenance_validates_running_images(tmp_path):
    root, env = _sandbox(tmp_path)
    result = _run(root, env)
    assert result.returncode == 0, result.stderr
    assert "SmartPloy image provenance: PASS" in result.stdout
    for service in ("api", "worker", "web"):
        assert f"service_{service}_image_verified=true" in result.stdout


def test_image_provenance_rejects_stale_but_running_worker(tmp_path):
    root, env = _sandbox(tmp_path)
    env["MOCK_STALE"] = "worker"
    result = _run(root, env)
    assert result.returncode != 0
    assert "worker runs an image other than expected release" in result.stderr
    assert "image provenance: PASS" not in result.stdout


def test_image_provenance_rejects_wrong_revision(tmp_path):
    root, env = _sandbox(tmp_path)
    assert _run(root, env, "invalid").returncode != 0
    result = _run(root, env, "2" * 40)
    assert result.returncode != 0
    assert "missing built image" in result.stderr


def test_provenance_script_passes_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_image_provenance_can_verify_exact_komplyint_oidc_images(tmp_path):
    root, env = _sandbox(tmp_path)
    env["SMARTPLOY_PRODUCTION_IDENTITY_MODE"] = "oidc"
    result = _run(root, env)
    assert result.returncode == 0, result.stderr
    assert "SmartPloy image provenance: PASS" in result.stdout


def test_image_provenance_refuses_mutated_oidc_policy_before_docker(tmp_path):
    root, env = _sandbox(tmp_path)
    env["SMARTPLOY_PRODUCTION_IDENTITY_MODE"] = "oidc"
    policy = root / "deploy/personal/runtime.oidc.production.env"
    policy.write_text(
        policy.read_text(encoding="utf-8").replace(
            "SMARTPLOY_ACCESS_ENABLED=false", "SMARTPLOY_ACCESS_ENABLED=true"
        ), encoding="utf-8"
    )
    result = _run(root, env)
    assert result.returncode != 0
    assert "does not match the approved allowlist" in result.stderr
    assert "image provenance: PASS" not in result.stdout

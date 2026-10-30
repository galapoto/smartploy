"""SP74: frontend build manifest is deterministic, nonsecret and fail-closed."""
import json

import pytest

from web.scripts.package_release_manifest import SCHEMA, manifest, write_manifest


def test_web_manifest_accepts_only_dev_or_exact_lowercase_sha_prefix():
    assert manifest("21d5b7fcdf94") == {
        "schema": SCHEMA, "release_revision": "21d5b7fcdf94"
    }
    assert manifest("dev")["release_revision"] == "dev"


@pytest.mark.parametrize("bad", [
    "", "DEV", "main", "release/latest", "unknown", "21d5b7fcdf9",
    "21d5b7fcdf940", "21D5B7FCDF94", "g" * 12, "0" * 40,
    "abc\nPRIVATE_CV=invalid", "../release.json", "--help",
])
def test_web_manifest_refuses_ambiguous_or_injected_build_version(bad):
    with pytest.raises(ValueError, match="WEB_RELEASE_VERSION"):
        manifest(bad)


def test_web_manifest_is_exact_stable_json_and_contains_no_env_data(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setenv("POSTGRES_PASSWORD", "SECRET_NOT_FOR_WEB")
    monkeypatch.setenv("SMARTPLOY_OIDC_CLIENT_ID", "SECRET_NOT_FOR_WEB")
    target = write_manifest("21d5b7fcdf94", dist)
    assert target == dist / "release.json"
    assert target.read_text(encoding="utf-8") == (
        '{"release_revision":"21d5b7fcdf94","schema":"smartploy-web-release-v1"}\n'
    )
    assert json.loads(target.read_text()) == manifest("21d5b7fcdf94")
    assert "SECRET_NOT_FOR_WEB" not in target.read_text()
    # A rebuild of the exact approved revision yields the same public bytes.
    before = target.read_bytes()
    assert write_manifest("21d5b7fcdf94", dist).read_bytes() == before


def test_web_manifest_refuses_missing_or_symlinked_dist(tmp_path):
    with pytest.raises(ValueError, match="DIRECTORY_INVALID"):
        write_manifest("21d5b7fcdf94", tmp_path / "not-created")
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "dist"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="DIRECTORY_INVALID"):
        write_manifest("21d5b7fcdf94", linked)


def test_web_manifest_does_not_follow_symlinked_target(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    secret = tmp_path / "private.txt"
    secret.write_text("do not modify", encoding="utf-8")
    (dist / "release.json").symlink_to(secret)
    with pytest.raises(ValueError, match="TARGET_INVALID"):
        write_manifest("21d5b7fcdf94", dist)
    assert secret.read_text() == "do not modify"

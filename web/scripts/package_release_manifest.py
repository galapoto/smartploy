#!/usr/bin/env python3
"""Generate a deliberately public, nonsecret frontend release fingerprint.

Only production's approved 12-hex image tag may identify a deployed build.
Local builds may use "dev"; production release gates refuse that sentinel.
Never include environment variables, credentials or applicant information.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

SCHEMA = "smartploy-web-release-v1"
REVISION = re.compile(r"[0-9a-f]{12}\Z")


def manifest(version: str) -> dict[str, str]:
    if version != "dev" and REVISION.fullmatch(version) is None:
        raise ValueError("WEB_RELEASE_VERSION_MUST_BE_EXACT_12_HEX_OR_DEV")
    return {"schema": SCHEMA, "release_revision": version}


def write_manifest(version: str, dist: Path) -> Path:
    if not dist.is_dir() or dist.is_symlink():
        raise ValueError("WEB_RELEASE_DIST_DIRECTORY_INVALID")
    target = dist / "release.json"
    if target.is_symlink() or target.exists() and not target.is_file():
        raise ValueError("WEB_RELEASE_TARGET_INVALID")
    encoded = json.dumps(manifest(version), sort_keys=True, separators=(",", ":")) + "\n"
    target.write_text(encoded, encoding="utf-8")
    return target


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: package_release_manifest.py <12-hex-revision|dev>")
    try:
        result = write_manifest(sys.argv[1], Path(__file__).resolve().parent.parent / "dist")
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
    print("Web release manifest written: " + result.name)

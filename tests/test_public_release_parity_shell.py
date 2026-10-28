"""Execute the real SP57 live release gate without DNS, TLS or OVH access.

A fake curl/getent pair simulates two independent health origins. No
production network, tokens, credentials or applicant records are touched.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "deploy/personal/scripts"


def _fake_live_gate(tmp_path: Path, public_revision: str | None) -> subprocess.CompletedProcess[str]:
    sandbox = tmp_path / "source"
    scripts = sandbox / "deploy/personal/scripts"
    scripts.mkdir(parents=True)
    for name in (
        "live-acceptance.sh", "select-runtime-policy.sh", "validate-runtime-policy.sh",
    ):
        shutil.copyfile(SCRIPTS / name, scripts / name)

    shutil.copyfile(
        ROOT / "deploy/personal/runtime.oidc.production.env",
        sandbox / "deploy/personal/runtime.oidc.production.env",
    )
    (sandbox / "deploy/personal/env").write_text(
        "SMARTPLOY_WEB_HOST_PORT=18091\n"
        "SMARTPLOY_OIDC_ISSUER=https://auth.komplyint.fi\n",
        encoding="utf-8",
    )
    package = sandbox / "smartploy"
    package.mkdir()
    shutil.copyfile(ROOT / "smartploy/__init__.py", package / "__init__.py")
    shutil.copyfile(ROOT / "smartploy/live_acceptance.py", package / "live_acceptance.py")

    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake_getent = binaries / "getent"
    fake_getent.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_getent.chmod(0o755)

    fake_curl = binaries / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
url = args[-1]
if '--write-out' in args:
    if url.endswith('/api/v1/dashboard'):
        print('401\\n\\nCaddy\\n\\n')
    elif url.endswith('/auth/login'):
        print('302\\n\\nCaddy\\nhttps://auth.komplyint.fi/oauth/v2/authorize?state=synthetic\\n')
    elif url.endswith('/'):
        print('200\\n\\nCaddy\\n\\n')
    else:
        sys.exit(9)
else:
    if not url.endswith('/healthz'):
        sys.exit(9)
    data = {
        'ok': True, 'service': 'smartploy',
        'public_origin': 'https://smartploy.komplyint.fi',
        'storage': {'mode': 'postgres', 'ready': True},
        'access': {'environment': 'production', 'enabled': False, 'owner_restricted': True},
        'external_actions_authorized': False,
        'release_revision': 'ab12cd34ef56',
    }
    if url.startswith('https://'):
        revision = os.environ.get('MOCK_PUBLIC_VERSION', '')
        if revision == 'MISSING':
            del data['release_revision']
        else:
            data['release_revision'] = revision
    sys.stdout.write(json.dumps(data))
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
    env["SMARTPLOY_PRODUCTION_IDENTITY_MODE"] = "oidc"
    env["MOCK_PUBLIC_VERSION"] = public_revision if public_revision is not None else "MISSING"
    return subprocess.run(
        ["bash", str(scripts / "live-acceptance.sh")],
        cwd=sandbox, env=env, capture_output=True, text=True, timeout=8, check=False,
    )


def test_sp57_independent_public_and_local_health_release_gates_pass(tmp_path):
    result = _fake_live_gate(tmp_path, "ab12cd34ef56")
    assert result.returncode == 0, result.stderr
    assert "public_revision_matches_origin=true" in result.stdout
    assert "public_release_revision=ab12cd34ef56" in result.stdout
    assert "access_api=protected_by_app_session" in result.stdout
    assert "oidc_login=redirect_to_trusted_oidc" in result.stdout
    assert "live_acceptance=pass" in result.stdout


@pytest.mark.parametrize("version", ["ab12cd34ef57", None, "dev", "A" * 12])
def test_sp57_real_release_shell_refuses_stale_or_missing_public_build(tmp_path, version):
    result = _fake_live_gate(tmp_path, version)
    assert result.returncode != 0
    assert "public OIDC release revision does not match the local origin" in result.stderr
    assert "live_acceptance=pass" not in result.stdout
    assert "public_revision_matches_origin=true" not in result.stdout
    assert "PRIVATE" not in result.stdout + result.stderr

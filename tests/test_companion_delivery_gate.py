"""SP45: native release gate must compare running Caddy bytes with source.

All requests are to local synthetic ThreadingHTTPServer. No employer traffic,
cookies, applicant data, public origin, production mutation or credentials.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
from threading import Thread

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/personal/scripts/assert-companion-release.sh"
HOST = "smartploy.komplyint.fi"
ZIP_NAME = "smartploy-apply-companion.zip"


def built_source_zip(tmp_path: Path) -> bytes:
    path = tmp_path / ZIP_NAME
    subprocess.run([
        sys.executable, str(ROOT / "web/scripts/package_companion.py"),
        "--output", str(path),
    ], check=True, capture_output=True, text=True, timeout=20)
    return path.read_bytes()


@contextmanager
def synthetic_caddy(
    data: bytes, sidecar: bytes, *, caching: bool = True,
    redirect: bool = False, missing: bool = False,
):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") != f"{HOST}:{self.server.server_port}":
                # The real curl explicitly overrides Host to HOST, so check
                # either standard or portless form below.
                if self.headers.get("Host") != HOST:
                    self.send_error(404)
                    return
            if self.path == "/" + ZIP_NAME and redirect:
                self.send_response(302)
                self.send_header("Location", "https://evil.invalid/malicious.zip")
                self.end_headers()
                return
            if self.path == "/" + ZIP_NAME and not missing:
                body, is_zip = data, True
            elif self.path == "/" + ZIP_NAME + ".sha256":
                body, is_zip = sidecar, False
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Type", "application/zip" if is_zip else "text/plain"
            )
            if is_zip and caching:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv.server_port
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def invoke(port: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), HOST, str(port)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


def test_sp45_read_only_live_bundle_gate_matches_exact_checkout(tmp_path):
    data = built_source_zip(tmp_path)
    digest = sha256(data).hexdigest()
    sidecar = f"{digest}  {ZIP_NAME}\n".encode("ascii")
    with synthetic_caddy(data, sidecar) as port:
        result = invoke(port)
    assert result.returncode == 0, result.stderr
    assert "companion_release_verified=true" in result.stdout
    assert f"companion_zip_sha256={digest}" in result.stdout
    assert "applicant" not in result.stdout
    assert "employer" not in result.stdout


@pytest.mark.parametrize("failure", [
    "tampered_matching_checksum", "stale_checksum", "no_cache",
    "missing_zip", "offsite_redirect", "html_spa", "dangerous_checksum",
])
def test_sp45_release_gate_rejects_missing_stale_or_untrusted_served_assets(
    tmp_path, failure,
):
    data = built_source_zip(tmp_path)
    sidecar = f"{sha256(data).hexdigest()}  {ZIP_NAME}\n".encode()
    opts = {}
    if failure == "tampered_matching_checksum":
        data += b"\nextra-unreviewed-extension-source"
        sidecar = f"{sha256(data).hexdigest()}  {ZIP_NAME}\n".encode()
    elif failure == "stale_checksum":
        sidecar = f"{'a' * 64}  {ZIP_NAME}\n".encode()
    elif failure == "no_cache":
        opts["caching"] = False
    elif failure == "missing_zip":
        opts["missing"] = True
    elif failure == "offsite_redirect":
        opts["redirect"] = True
    elif failure == "html_spa":
        data = b"<!doctype html><html>SmartPloy index.html</html>"
        sidecar = f"{sha256(data).hexdigest()}  {ZIP_NAME}\n".encode()
    elif failure == "dangerous_checksum":
        sidecar = f"{sha256(data).hexdigest()}  ../../evil.zip\n".encode()
    with synthetic_caddy(data, sidecar, **opts) as port:
        result = invoke(port)
    assert result.returncode != 0, failure
    assert "companion_release_verified=true" not in result.stdout


def test_sp45_release_rejects_invalid_host_and_port_without_web_calls():
    for host, port in [
        ("http://evil.invalid", "8091"), ("smartploy.komplyint.fi\rX", "8091"),
        ("smartploy.komplyint.fi", "80"), ("smartploy.komplyint.fi", "99999"),
        ("smartploy.komplyint.fi", "abc"),
    ]:
        result = subprocess.run(
            ["bash", str(SCRIPT), host, port],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 2
        assert "companion_release_verified=true" not in result.stdout


def test_sp45_release_proof_must_run_before_marking_deploy_sha():
    deploy = (ROOT / "deploy/personal/scripts/deploy.sh").read_text()
    gate = 'bash "${SCRIPT_DIR}/assert-companion-release.sh" "${PRODUCTION_HOST}" "${WEB_PORT}"'
    assert gate in deploy
    assert deploy.index(gate) < deploy.index('> "${STATE_DIR}/deployed-sha"')
    evidence = (ROOT / "deploy/personal/scripts/release-evidence.sh").read_text()
    assert "COMPANION_FIELDS" in evidence
    assert "companion_release_verified=true" in evidence
    assert "${COMPANION_FIELDS}" in evidence
    woodpecker = (ROOT / ".woodpecker/smartploy.yaml").read_text()
    assert "python3 --version" in woodpecker
    assert "npm run build" in woodpecker

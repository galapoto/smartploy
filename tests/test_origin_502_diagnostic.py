"""Static safety checks for the read-only SmartPloy 502 diagnostic."""
from pathlib import Path
import subprocess


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "personal"
    / "scripts"
    / "diagnose-origin-502.sh"
)


def test_origin_diagnostic_is_shell_valid_and_read_only():
    assert SCRIPT.is_file()
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "read_only=true" in source
    assert "loopback_health_http" in source
    assert 'select-runtime-policy.sh' in source
    assert 'validate-runtime-policy.sh' in source
    assert 'PRODUCTION_HOST="${PRODUCTION_ORIGIN#https://}"' in source
    assert 'probe --connect-to "${PRODUCTION_HOST}:443:127.0.0.1:443"' in source
    assert "smartploy.obumai.com:443" not in source
    for forbidden in (
        "docker compose up",
        "docker compose down",
        "docker compose restart",
        "--insecure",
        "curl -k",
        "printenv",
        "cat \"$ENV_FILE\"",
        "docker compose logs",
    ):
        assert forbidden not in source

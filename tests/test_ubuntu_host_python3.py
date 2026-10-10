"""Host-side scripts run on Ubuntu where 'python3' exists but 'python' may not."""
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "deploy/personal/scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_host_scripts_use_python3_not_unversioned_python():
    preflight = _read("preflight.sh")
    assert "awk python3;" in preflight
    assert "| python3 -c" in preflight
    assert '\npython3 - "${COMPOSE_JSON}"' in preflight

    deploy = _read("deploy.sh")
    restore = _read("restore.sh")
    assert 'if python3 - "${HEALTH_FILE}"' in deploy
    assert 'if python3 - "${HEALTH_FILE}"' in restore

    live = _read("live-acceptance.sh")
    assert "curl getent python3 mktemp" in live
    assert 'PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance' in live

    evidence = _read("release-evidence.sh")
    assert "mktemp mv python3 realpath" in evidence
    assert 'PYTHONPATH="${REPO_ROOT}" python3 -m smartploy.live_acceptance' in evidence
    assert 'HEALTH_FIELDS="$(python3 - "${HEALTH_FILE}"' in evidence

    boundaries = _read("smoke-env-boundaries.sh")
    assert '\npython3 - "${TMP_DIR}"' in boundaries


def test_container_python_commands_remain_in_container_only():
    # Docker image has 'python', so container commands must NOT be modified.
    assert 'api python scripts/migrate.py' in _read("deploy.sh")
    assert 'api python scripts/migrate.py' in _read("restore.sh")
    assert "  python -c 'import os;" in _read("smoke-env-boundaries.sh")

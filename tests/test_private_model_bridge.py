"""Private cross-stack Ollama bridge has explicit consent and narrow membership."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/personal/scripts/bridge-local-ollama.sh"


FAKE_DOCKER = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

path = Path(os.environ["FAKE_DOCKER_STATE"])
data = json.loads(path.read_text(encoding="utf-8"))
args = sys.argv[1:]
data["calls"].append(args)

def write():
    # Docker introspection is read-only. In the real shell, network-inspect
    # and container-inspect run concurrently in a pipeline, so mocks must
    # not race over one shared state file for those harmless observations.
    if args[0] in {"ps", "inspect"} or args[:2] == ["network", "inspect"]:
        return
    path.write_text(json.dumps(data), encoding="utf-8")

if args[0] == "ps":
    labels = " ".join(args)
    if "com.docker.compose.project=obumai-personal" in labels:
        print("core123")
    elif "com.docker.compose.project=smartploy" in labels:
        print("api456")
    write()
    sys.exit(0)

if args[0] == "inspect":
    fmt = args[args.index("--format") + 1]
    subject = args[-1]
    if "Health.Status" in fmt:
        print("healthy")
    elif ".Config.Image" in fmt:
        print("ollama/ollama:0.34.0" if subject == "core123" else "smartploy-api:cf495220682c")
    elif ".Name" in fmt:
        print("/obumai-personal-ollama-1" if subject == "core123" else "/smartploy-api-1")
    else:
        sys.exit(3)
    write()
    sys.exit(0)

if args[:2] == ["network", "inspect"]:
    if not data["network"]:
        write()
        sys.exit(1)
    if "--format" in args:
        fmt = args[args.index("--format") + 1]
        if ".Driver" in fmt:
            print("bridge")
        elif ".Internal" in fmt:
            print("true" if data["internal"] else "false")
        elif ".Labels" in fmt:
            print("private")
        elif ".Containers" in fmt:
            if "core123" in data["members"]:
                print("obumai-personal-ollama-1")
            if "api456" in data["members"]:
                print("smartploy-api-1")
    write()
    sys.exit(0)

if args[:2] == ["network", "create"]:
    if "--internal" not in args or "--driver" not in args:
        sys.exit(5)
    data["network"] = True
    data["internal"] = True
    write()
    print("fixture-private-network")
    sys.exit(0)

if args[:2] == ["network", "connect"]:
    data["members"].append(args[-1])
    write()
    sys.exit(0)

if args[0] == "exec":
    print("model_endpoint_reachable=true")
    print("installed_model_count=1")
    print("required_model_present=true")
    write()
    sys.exit(0)

write()
sys.exit(2)
'''


@pytest.fixture()
def fake_docker(tmp_path: Path):
    fake = tmp_path / "docker"
    fake.write_text(FAKE_DOCKER, encoding="utf-8")
    fake.chmod(0o755)
    state = tmp_path / "docker.json"
    state.write_text(
        json.dumps({"network": False, "internal": False, "members": [], "calls": []}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    env["FAKE_DOCKER_STATE"] = str(state)
    return env, state


def run(env: dict, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20, check=False, env=env,
    )


def state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_script_parses_and_has_no_public_port_or_vault_modification():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    source = SCRIPT.read_text(encoding="utf-8")
    assert "docker network create --driver bridge --internal" in source
    assert 'service_id obumai-personal ollama' in source
    assert 'service_id smartploy api' in source
    assert 'label=com.docker.compose.project=$project' in source
    assert 'label=com.docker.compose.service=$service' in source
    assert "docker network connect --alias ollama" in source
    assert "docker exec -i" in source
    for disallowed in ("docker run", "docker compose down", "docker network create --attachable",
                       "docker exec --privileged", "0.0.0.0:11434", "-p 11434", "postgres"):
        assert disallowed not in source


def test_default_status_never_creates_or_connects_network(fake_docker):
    env, path = fake_docker
    output = run(env)
    assert output.returncode == 0, output.stderr
    assert "diagnosis=private_bridge_not_yet_commissioned" in output.stdout
    calls = state(path)["calls"]
    assert all(row[:2] not in (["network", "connect"], ["network", "create"]) for row in calls)


def test_explicit_connect_uses_only_private_bridge_and_is_idempotent(fake_docker):
    env, path = fake_docker
    first = run(env, "--connect")
    assert first.returncode == 0, first.stderr + first.stdout
    assert "model_endpoint_reachable=true" in first.stdout
    final = state(path)
    assert final["internal"] is True
    assert final["network"] is True
    assert set(final["members"]) == {"core123", "api456"}
    created = [a for a in final["calls"] if a[:2] == ["network", "create"]]
    assert len(created) == 1
    assert "--internal" in created[0]
    connected = [a for a in final["calls"] if a[:2] == ["network", "connect"]]
    assert len(connected) == 2
    assert ["network", "connect", "--alias", "ollama", "smartploy-ollama-private", "core123"] in connected
    assert ["network", "connect", "smartploy-ollama-private", "api456"] in connected

    second = run(env, "--connect")
    assert second.returncode == 0, second.stderr + second.stdout
    calls = state(path)["calls"]
    assert len([a for a in calls if a[:2] == ["network", "connect"]]) == 2
    assert len([a for a in calls if a[:2] == ["network", "create"]]) == 1


def test_existing_untrusted_bridge_is_rejected_without_connect(fake_docker):
    env, path = fake_docker
    data = state(path)
    data.update({"network": True, "internal": False})
    path.write_text(json.dumps(data), encoding="utf-8")
    result = run(env, "--connect")
    assert result.returncode != 0
    assert "existing network is not the approved internal" in result.stderr
    assert not any(c[:2] == ["network", "connect"] for c in state(path)["calls"])


def test_bridge_command_is_never_implicit_in_default_disabled_deploy():
    source = (ROOT / "deploy/personal/scripts/deploy.sh").read_text(encoding="utf-8")
    assert 'if [[ "$LOCAL_AI_ENABLED" == "true" ]]' in source
    assert 'LOCAL_AI_URL" != "http://ollama:11434"' in source
    assert 'bridge-local-ollama.sh" --connect' in source
    assert source.index('up -d --wait --wait-timeout 120 --no-deps --force-recreate api') < source.index('bridge-local-ollama.sh" --connect')

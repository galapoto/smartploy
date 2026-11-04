"""SP130 host readiness diagnostics are read-only, redacted and fail closed."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import feature_first_prod_readiness as diag


SHA = "a" * 40
OTHER = "b" * 40


def test_absent_or_inaccessible_server_is_hold_not_a_fake_live_release(tmp_path, monkeypatch):
    monkeypatch.setattr(diag.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(diag.pwd, "getpwnam", lambda _user: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(diag, "_run_git", lambda *_args: (False, ""))
    missing = tmp_path / "missing"
    report = diag.inspect(repo=missing, state=missing / "state", candidate=SHA)
    assert report["status"] == "HOLD"
    assert "root_context" in report["host_blockers"]
    assert "native_ci_exact_sha" in report["host_blockers"]
    assert "candidate_on_main" in report["host_blockers"]
    assert report["deployed_sha"] is None
    assert report["public_health_revision"] is None
    assert report["external_gates"]["actual_signed_in_user_journey"] == "NOT_VERIFIED"
    assert not missing.exists()  # no provisioning or runtime changes


def _fixture(tmp_path: Path, monkeypatch):
    repo, state, installed, home = (
        tmp_path / "smartploy", tmp_path / "state",
        tmp_path / "installed", tmp_path / "home"
    )
    for path in (repo / "deploy/personal/scripts", state, installed, home / ".ssh"):
        path.mkdir(parents=True, exist_ok=True)
    (repo / "deploy/personal/env").write_text("PRIVATE_PASSWORD=DO_NOT_DISPLAY\n")
    (repo / "deploy/personal/scripts/deploy.sh").write_text("# real guarded deploy placeholder\n")
    (repo / "deploy/personal/scripts/feature-first-ssh-gate.sh").write_text(
        "mock original gate\n"
    )
    (repo / "deploy/personal/scripts/feature-first-remote-promotion.sh").write_text(
        "mock original dispatcher\n"
    )
    gate = installed / "ssh-gate"
    dispatcher = installed / "dispatch"
    gate.write_text("mock original gate\n")
    dispatcher.write_text("mock original dispatcher\n")
    (home / ".ssh/authorized_keys").write_text(
        'restrict,command="/usr/local/libexec/smartploy-feature-first-ssh-gate" '
        'ssh-ed25519 AAAATEST fixture\n'
    )
    for name in ("native-ci-qualified-sha", "feature-first-auto-eligible-sha",
                 "deployed-sha"):
        (state / name).write_text(SHA + "\n")

    monkeypatch.setattr(diag, "SSH_GATE", gate)
    monkeypatch.setattr(diag, "DISPATCHER", dispatcher)
    monkeypatch.setattr(diag, "_owned_file",
                        lambda p: p.is_file() and not p.is_symlink())
    monkeypatch.setattr(diag, "_owned_directory",
                        lambda p: p.is_dir() and not p.is_symlink())
    monkeypatch.setattr(diag.os, "geteuid", lambda: 0)
    monkeypatch.setattr(diag.pwd, "getpwnam", lambda _user:
                        SimpleNamespace(pw_dir=str(home)))
    monkeypatch.setattr(diag, "_run_git", lambda *_args: (True, ""))
    return repo, state, installed, home


def test_host_only_gates_can_pass_but_signed_in_and_environment_remain_unverified(
    tmp_path, monkeypatch,
):
    repo, state, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(diag, "_public_revision", lambda: "804747bd9f01")
    report = diag.inspect(repo=repo, state=state, candidate=SHA, online=True)
    assert report["status"] == "HOST_GATES_PRESENT"
    assert report["host_blockers"] == []
    assert report["candidate_sha"] == SHA
    assert report["deployed_sha"] == SHA
    assert report["public_health_revision"] == "804747bd9f01"
    assert all(check["status"] == "PASS" for key, check in report["checks"].items()
               if key != "public_health")
    assert all(state == "NOT_VERIFIED"
               for state in report["external_gates"].values())
    assert "SHIP" not in json.dumps(report)
    assert "DO_NOT_DISPLAY" not in json.dumps(report)


def test_diagnostic_rejects_wrong_sha_unapproved_candidate_and_second_ssh_key(
    tmp_path, monkeypatch,
):
    repo, state, _, home = _fixture(tmp_path, monkeypatch)
    report = diag.inspect(repo=repo, state=state, candidate=OTHER)
    assert report["status"] == "HOLD"
    assert "native_ci_exact_sha" in report["host_blockers"]
    assert "independent_release_approval" in report["host_blockers"]
    assert report["candidate_sha"] == OTHER

    (home / ".ssh/authorized_keys").write_text(
        (home / ".ssh/authorized_keys").read_text()
        + "ssh-ed25519 ANOTHERKEY unrestricted\n"
    )
    report = diag.inspect(repo=repo, state=state, candidate=SHA)
    assert report["status"] == "HOLD"
    assert "service_key_restricted" in report["host_blockers"]


def test_diagnostic_rejects_installed_script_drift_and_missing_native_receipt(
    tmp_path, monkeypatch,
):
    repo, state, installed, _ = _fixture(tmp_path, monkeypatch)
    (installed / "ssh-gate").write_text("unreviewed gate\n")
    (state / "native-ci-qualified-sha").unlink()
    result = diag.inspect(repo=repo, state=state, candidate=SHA)
    assert result["status"] == "HOLD"
    assert {"ssh_gate_source_match", "native_ci_exact_sha"} <= set(
        result["host_blockers"]
    )


def test_real_root_receipt_validation_refuses_symlink_and_nonroot_ownership(tmp_path):
    receipt = tmp_path / "native-ci-qualified-sha"
    receipt.write_text(SHA)
    receipt.chmod(0o666)
    assert not diag._root_receipt_matches(receipt, SHA)
    receipt.chmod(0o600)
    if receipt.stat().st_uid == 0:
        assert diag._root_receipt_matches(receipt, SHA)
    else:
        assert not diag._root_receipt_matches(receipt, SHA)
    alias = tmp_path / "alias"
    alias.symlink_to(receipt)
    assert not diag._root_receipt_matches(alias, SHA)
    assert not diag._root_receipt_matches(receipt, OTHER)


def test_cli_prints_safe_json_and_optional_strict_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(diag.sys, "argv", [
        "feature_first_prod_readiness.py", "--repo", str(tmp_path / "missing"),
        "--state-dir", str(tmp_path / "missing-state"),
        "--candidate-sha", SHA, "--require-host-gates",
    ])
    assert diag.main() == 42
    printed = capsys.readouterr().out
    parsed = json.loads(printed)
    assert parsed["status"] == "HOLD"
    assert parsed["note"].startswith("Read-only")
    assert "PRIVATE_PASSWORD" not in printed


def test_script_never_executes_deployment_or_writes_approvals():
    source = Path(diag.__file__).read_text(encoding="utf-8")
    assert "subprocess.run(" in source
    assert '"git", "-c", f"safe.directory={repo}"' in source
    assert 'git fetch' not in source and 'ssh-keygen' not in source
    assert 'write_text(' not in source and 'unlink(' not in source
    # Source mentions approved paths in comments, but cannot create approvals.
    assert '"native-ci-qualified-sha"' in source
    assert '"feature-first-approved-sha"' in source
    assert "urlopen(req, timeout=5)" in source

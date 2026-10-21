"""Offline source and release-HOLD tests; no runner/production access."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.obumdelivery_ci_gate import (
    AdmissionDenied, FORMAT, REPOSITORY, STAGES, mark, qualify, summarize,
)

SHA = "a" * 40
TREE = "b" * 40


def source():
    return qualify(REPOSITORY, SHA, SHA, TREE)


@pytest.mark.parametrize("args", [
    ("obumai/obumellm", SHA, SHA, TREE),
    (REPOSITORY, SHA, "c" * 40, TREE),
    (REPOSITORY, "main", SHA, TREE),
    (REPOSITORY, SHA, SHA, "bad"),
])
def test_untrusted_source_claim_fails(args):
    with pytest.raises(AdmissionDenied):
        qualify(*args)


def test_source_receipt_never_grants_deployment():
    value = source()
    assert value["schema"] == FORMAT
    assert value["source_sha"] == SHA
    assert value["release_gate"] == "HOLD"
    assert not value["production_changed"]
    assert not value["employer_actions_authorized"]


def test_missing_stage_or_wrong_sha_fails_closed(tmp_path: Path):
    with pytest.raises((AdmissionDenied, FileNotFoundError)):
        summarize(tmp_path, source())
    mark(tmp_path, STAGES[0], source())
    with pytest.raises((AdmissionDenied, FileNotFoundError)):
        summarize(tmp_path, source())
    mark(tmp_path, STAGES[1], source())
    other = qualify(REPOSITORY, "c" * 40, "c" * 40, TREE)
    with pytest.raises(AdmissionDenied, match="IDENTITY"):
        summarize(tmp_path, other)


def test_both_stages_produce_one_nonrelease_result(tmp_path: Path):
    for stage in STAGES:
        marker = mark(tmp_path, stage, source())
        with pytest.raises(AdmissionDenied, match="OVERWRITE"):
            mark(tmp_path, stage, source())
        assert marker.stat().st_size < 16000
    output = summarize(tmp_path, source())
    assert output["synthetic_python_postgres_tests_passed"]
    assert output["synthetic_web_browser_tests_passed"]
    assert output["live_ovh_deployment_verified"] is False
    assert output["staging_or_production_deploy_authorized"] is False
    assert json.dumps(output).count("HOLD") == 1


def test_unknown_stage_and_symlink_rejected(tmp_path: Path):
    with pytest.raises(AdmissionDenied, match="STAGE"):
        mark(tmp_path, "ovh-production", source())
    other = tmp_path / "dir"
    other.mkdir()
    (tmp_path / ".ci-out").symlink_to(other, target_is_directory=True)
    with pytest.raises(AdmissionDenied, match="SYMLINK"):
        mark(tmp_path, STAGES[0], source())


def _simulate_woodpecker_checkout(monkeypatch, event, expected=None, claimed=SHA):
    """Synthetic Git checkout; never calls a controller or production host."""
    import scripts.obumdelivery_ci_gate as gate

    monkeypatch.setenv("CI_REPO", REPOSITORY)
    monkeypatch.setenv("CI_COMMIT_SHA", claimed)
    monkeypatch.setenv("CI_PIPELINE_EVENT", event)
    monkeypatch.delenv("CI_NEGATIVE_PROBE", raising=False)
    monkeypatch.delenv("OBUMDELIVERY_EXPECTED_SHA", raising=False)
    if expected is not None:
        monkeypatch.setenv("OBUMDELIVERY_EXPECTED_SHA", expected)
    monkeypatch.setattr(
        gate.subprocess, "check_output",
        lambda args, **kwargs: TREE if args[-1] == "HEAD^{tree}" else SHA,
    )
    return gate.current()


def test_manual_review_exact_sha_success_still_holds_release(monkeypatch):
    result = _simulate_woodpecker_checkout(monkeypatch, "manual", SHA)
    assert result["source_sha"] == SHA
    assert result["expected_review_sha"] == SHA
    assert result["release_gate"] == "HOLD"
    assert not result["production_changed"]
    assert not result["employer_actions_authorized"]


@pytest.mark.parametrize("expected,reason", [
    (None, "MANUAL_EXPECTED_SHA_REQUIRED"),
    ("main", "MANUAL_EXPECTED_SHA_REQUIRED"),
    ("c" * 40, "MANUAL_SOURCE_SHA_MISMATCH"),
])
def test_manual_review_rejects_missing_invalid_or_moved_sha(monkeypatch, expected, reason):
    with pytest.raises(AdmissionDenied, match=reason):
        _simulate_woodpecker_checkout(monkeypatch, "manual", expected)


def test_main_push_preserves_existing_ci_without_manual_pin(monkeypatch):
    result = _simulate_woodpecker_checkout(monkeypatch, "push")
    assert result["source_sha"] == SHA
    assert "expected_review_sha" not in result
    assert result["release_gate"] == "HOLD"


def test_manual_does_not_trust_forged_woodpecker_checkout_claim(monkeypatch):
    with pytest.raises(AdmissionDenied, match="CI_CHECKOUT_SHA_MISMATCH"):
        _simulate_woodpecker_checkout(monkeypatch, "manual", SHA, claimed="c" * 40)


def test_unsupported_woodpecker_event_is_not_qualified(monkeypatch):
    with pytest.raises(AdmissionDenied, match="UNSUPPORTED_CI_EVENT"):
        _simulate_woodpecker_checkout(monkeypatch, "pull_request", SHA)


def test_deliberate_negative_probe_still_fails_before_manual_pin(monkeypatch):
    import scripts.obumdelivery_ci_gate as gate

    _simulate_woodpecker_checkout(monkeypatch, "manual", SHA)
    monkeypatch.setenv("CI_NEGATIVE_PROBE", "1")
    with pytest.raises(AdmissionDenied, match="EXPECTED_RED_NEGATIVE_PROBE"):
        gate.current()


def test_native_woodpecker_pipeline_executes_exact_negative_control_before_tests():
    """The real isolated CI job MUST demonstrate denied source admission."""
    pipeline = (Path(__file__).resolve().parents[1] / ".woodpecker/smartploy.yaml").read_text(
        encoding="utf-8"
    )
    assert "CI_NEGATIVE_PROBE=1 python3 -B scripts/obumdelivery_ci_gate.py validate" in pipeline
    assert 'test "$negative_status" -eq 41' in pipeline
    assert "EXPECTED_RED_NEGATIVE_PROBE" in pipeline
    assert "OBUMDELIVERY_EXPECTED_RED_NEGATIVE_CONTROL_VERIFIED" in pipeline
    assert pipeline.index("OBUMDELIVERY_EXPECTED_RED_NEGATIVE_CONTROL_VERIFIED") < pipeline.index(
        'python3 -m pip install --no-cache-dir -e ".[dev]"'
    )
    assert "PRODUCTION_RELEASE_GATE_HOLD" in pipeline
    assert "docker compose up" not in pipeline

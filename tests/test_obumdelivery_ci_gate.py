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

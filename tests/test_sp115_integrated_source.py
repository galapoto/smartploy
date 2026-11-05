"""SP115 synthetic-only negative tests for the immutable release review gate."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.verify_sp115_integrated_source import (
    CandidateGateError, EXPECTED_HEAD, EXPECTED_SCHEMA, MANIFEST,
    git_blob_sha1, verify_inventory, verify_source_blob,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest():
    return json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))


def test_sp115_exact_integrated_source_inventory_passes_without_network(manifest):
    assert manifest["schema"] == EXPECTED_SCHEMA
    assert manifest["source_head_sha"] == EXPECTED_HEAD
    assert verify_inventory(ROOT, manifest) == 79


def test_sp115_single_byte_source_mutation_is_rejected(manifest):
    entry = next(item for item in manifest["source_artifacts"]
                 if item["path"] == "web/src/App.tsx")
    original = (ROOT / entry["path"]).read_bytes()
    assert git_blob_sha1(original) == entry["git_blob_sha1"]
    with pytest.raises(CandidateGateError, match="source blob changed"):
        verify_source_blob(entry["git_blob_sha1"], original + b"\n")


@pytest.mark.parametrize("unsafe_path", [
    "../private-data", "/etc/passwd", "web\\src\\App.tsx",
    "web//src/App.tsx", "web/../src/App.tsx",
])
def test_sp115_inventory_cannot_read_unapproved_or_traversal_paths(
    manifest, unsafe_path,
):
    altered = deepcopy(manifest)
    altered["source_artifacts"][0]["path"] = unsafe_path
    with pytest.raises(CandidateGateError):
        verify_inventory(ROOT, altered)


@pytest.mark.parametrize("key,value", [
    ("production_verified", True),
    ("automatic_unattended_employer_submission_authorized", True),
    ("local_browser_employer_submit_automatic", True),
    ("browser_observation_counts_as_provider_acknowledgement", True),
])
def test_sp115_cannot_claim_unverified_employer_or_production_actions(
    manifest, key, value,
):
    altered = deepcopy(manifest)
    altered["scope"][key] = value
    with pytest.raises(CandidateGateError, match="Unsafe or falsely"):
        verify_inventory(ROOT, altered)


@pytest.mark.parametrize("key,value", [
    ("approval_required", False),
    ("independent_code_privacy_review_required", False),
    ("native_delivery_ci_required", False),
    ("production_deployment_approved", True),
    ("real_employer_acceptance_verified", True),
])
def test_sp115_independent_release_approval_cannot_be_short_circuited(
    manifest, key, value,
):
    altered = deepcopy(manifest)
    altered["release"][key] = value
    with pytest.raises(CandidateGateError, match="Unsafe or falsely"):
        verify_inventory(ROOT, altered)


def test_sp115_removed_file_or_outdated_review_head_fails_closed(manifest):
    altered = deepcopy(manifest)
    altered["source_artifacts"].pop()
    with pytest.raises(CandidateGateError, match="missing critical"):
        verify_inventory(ROOT, altered)
    altered = deepcopy(manifest)
    altered["source_dependency_prs"][-1]["head"] = "0" * 40
    with pytest.raises(CandidateGateError, match="dependency"):
        verify_inventory(ROOT, altered)


def test_sp115_rea_status_cannot_claim_a_nonexistent_trace(manifest):
    altered = deepcopy(manifest)
    altered["rea"]["status"] = "REA_APPLIED"
    with pytest.raises(CandidateGateError, match="REA evidence"):
        verify_inventory(ROOT, altered)

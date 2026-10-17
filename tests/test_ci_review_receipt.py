"""Offline, synthetic receipts: no GitHub network, credentials or deployments."""

import hashlib
import json

import pytest

from scripts.ci_review_receipt import REQUIRED_JOBS, create_receipt, write_receipt


BASE = {
    "repository": "galapoto/smartploy",
    "event": "pull_request",
    "run_id": "123456789",
    "run_attempt": "1",
    "checkout_sha": "a" * 40,
    "checkout_tree": "b" * 40,
    "expected_checkout_sha": "a" * 40,
    "pull_request_head_sha": "c" * 40,
    "job_results": {name: "success" for name in REQUIRED_JOBS},
}


def test_pr_receipt_distinguishes_tested_checkout_from_pr_head():
    receipt = create_receipt(**BASE)
    assert receipt["automated_ci_passed"] is True
    assert receipt["tested_checkout"]["commit_sha"] == "a" * 40
    assert receipt["tested_checkout"]["tree_sha"] == "b" * 40
    assert receipt["pull_request_head_sha"] == "c" * 40
    assert receipt["tested_checkout"]["is_pull_request_merge_ref_possible"] is True
    assert receipt["authorizes_merge"] is False
    assert receipt["authorizes_production_deployment"] is False
    assert all(receipt["not_verified_by_ci"].values())


@pytest.mark.parametrize("job", REQUIRED_JOBS)
def test_failed_or_missing_job_cannot_earn_review_receipt(job):
    payload = {**BASE, "job_results": {**BASE["job_results"], job: "failure"}}
    with pytest.raises(ValueError, match="did not succeed"):
        create_receipt(**payload)
    payload["job_results"].pop(job)
    with pytest.raises(ValueError, match="exactly"):
        create_receipt(**payload)


def test_checkout_sha_mismatch_fails_closed():
    with pytest.raises(ValueError, match="differs"):
        create_receipt(**{**BASE, "expected_checkout_sha": "d" * 40})


@pytest.mark.parametrize("field,value", [
    ("run_id", "not-an-int"),
    ("run_attempt", "0"),
    ("repository", "../invalid"),
    ("event", "scheduled"),
    ("checkout_tree", "bad-tree"),
    ("pull_request_head_sha", ""),
])
def test_invalid_metadata_fails_closed(field, value):
    with pytest.raises(ValueError):
        create_receipt(**{**BASE, field: value})


def test_push_receipt_has_no_claim_about_pr_head():
    receipt = create_receipt(**{**BASE, "event": "push", "pull_request_head_sha": ""})
    assert receipt["pull_request_head_sha"] is None
    assert receipt["tested_checkout"]["is_pull_request_merge_ref_possible"] is False
    with pytest.raises(ValueError, match="must not claim"):
        create_receipt(**{**BASE, "event": "push"})


def test_checksum_and_receipt_are_reproducible(tmp_path):
    payload = create_receipt(**BASE)
    path, checksum_path = write_receipt(tmp_path, payload)
    raw = path.read_bytes()
    assert json.loads(raw)["format"] == "smartploy-ci-review-receipt-v1"
    assert checksum_path.read_text(encoding="ascii") == (
        f"{hashlib.sha256(raw).hexdigest()}  review-receipt.json\n"
    )
    old = path.read_bytes()
    write_receipt(tmp_path, payload)
    assert path.read_bytes() == old

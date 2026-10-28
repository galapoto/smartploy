"""SP59: independently attest the original owner-opted-in AutoDraft worker.

Synthetic worker rows only. This never reads an applicant, contacts an ATS or
starts a scheduled task, and cannot prove any particular CV kit was created.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from smartploy.auto_draft_runtime_acceptance import (
    AutoDraftAcceptanceError, evaluate, main,
)
from smartploy.worker_schedule import WorkerTask


NOW = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
POLICY = {
    "private_opt_in_required": True,
    "processing": "local_only",
    "external_actions_authorized": False,
}


def task(
    *, enabled: bool = True, kind: str = "application_draft",
    task_id: str = "application:auto-draft-shortlist",
    status: str = "healthy", completed: datetime | None = NOW,
    failures: int = 0, metadata: dict | None = None, cadence: int = 120,
) -> WorkerTask:
    return WorkerTask(
        task_id=task_id, task_kind=kind, enabled=enabled,
        cadence_seconds=cadence, next_run_at=NOW,
        last_status=status, last_completed_at=completed,
        consecutive_failures=failures, metadata=POLICY if metadata is None else metadata,
    )


def test_no_operator_flag_means_no_actual_worker_authorization():
    disabled = evaluate("false", None, now=NOW)
    assert disabled == {
        "schema": "smartploy.auto_draft.runtime.v1",
        "status": "disabled_by_operator",
        "task_registered": False,
        "task_enabled": False,
        "completed_run_verified": False,
        "candidate_drafts_created_verified": False,
        "employer_contacts_authorized": False,
        "external_actions_authorized": False,
    }
    assert evaluate("false", task(enabled=False), now=NOW)["status"] == "disabled_by_operator"
    with pytest.raises(AutoDraftAcceptanceError, match="STILL_ENABLED"):
        evaluate("false", task(), now=NOW)
    with pytest.raises(AutoDraftAcceptanceError, match="OPT_IN_REQUIRED"):
        evaluate("false", task(enabled=False), now=NOW, require_run=True)


@pytest.mark.parametrize("flag", ["", "1", "yes", "on", "TRUE", "true ", " False"])
def test_explicit_host_optin_must_be_an_exact_boolean(flag):
    with pytest.raises(AutoDraftAcceptanceError, match="FLAG_INVALID"):
        evaluate(flag, task(), now=NOW)


@pytest.mark.parametrize(("overrides", "reason"), [
    ({"enabled": False}, "NOT_ENABLED"),
    ({"kind": "application_agent"}, "NOT_ENABLED"),
    ({"task_id": "source:unexpected"}, "NOT_ENABLED"),
    ({"cadence": 0}, "CADENCE_INVALID"),
    ({"cadence": 86401}, "CADENCE_INVALID"),
])
def test_invalid_registered_worker_cannot_be_called_healthy(overrides, reason):
    with pytest.raises(AutoDraftAcceptanceError, match=reason):
        evaluate("true", task(**overrides), now=NOW, require_run=True)


def test_missing_worker_task_is_not_generic_worker_health():
    with pytest.raises(AutoDraftAcceptanceError, match="NOT_REGISTERED"):
        evaluate("true", None, now=NOW)


@pytest.mark.parametrize(("key", "value"), [
    ("private_opt_in_required", False),
    ("private_opt_in_required", "true"),
    ("private_opt_in_required", None),
    ("processing", "remote_ai"),
    ("processing", "local_and_remote"),
    ("external_actions_authorized", True),
    ("external_actions_authorized", None),
])
def test_worker_policy_must_prove_optin_local_only_no_employer_actions(key, value):
    with pytest.raises(AutoDraftAcceptanceError, match="PRIVATE_POLICY_MISMATCH"):
        evaluate("true", task(metadata={**POLICY, key: value}), now=NOW, require_run=True)


def test_fresh_current_worker_run_qualifies_not_an_applicant_or_employer_receipt():
    recent = task(completed=NOW - timedelta(seconds=12))
    result = evaluate(
        "true", recent, now=NOW,
        not_before=NOW - timedelta(seconds=15), require_run=True,
    )
    assert result["status"] == "healthy_scheduled_run"
    assert result["completed_run_verified"] is True
    assert result["task_enabled"] is True
    assert result["candidate_drafts_created_verified"] is False
    assert result["employer_contacts_authorized"] is False
    assert result["external_actions_authorized"] is False


def test_scheduled_task_row_cannot_borrow_pre_restart_old_cycle():
    recent = task(completed=NOW - timedelta(seconds=12))
    with pytest.raises(AutoDraftAcceptanceError, match="FRESH_RUN_MISSING"):
        evaluate(
            "true", recent, now=NOW,
            not_before=NOW - timedelta(seconds=4), require_run=True,
        )


def test_stale_task_row_remains_unverified_even_when_status_still_healthy():
    old = task(completed=NOW - timedelta(minutes=20), cadence=120)
    assert evaluate("true", old, now=NOW)["status"] == "registered_waiting_for_run"
    with pytest.raises(AutoDraftAcceptanceError, match="FRESH_RUN_MISSING"):
        evaluate("true", old, now=NOW, require_run=True)


@pytest.mark.parametrize(("status", "failures", "completed"), [
    ("degraded", 0, NOW),
    ("failed", 0, NOW),
    ("never", 0, None),
    ("healthy", 1, NOW),
    ("healthy", 0, None),
])
def test_failed_worker_or_uncompleted_cycle_never_claims_healthy(
    status, failures, completed
):
    with pytest.raises(AutoDraftAcceptanceError, match="RUN_NOT_HEALTHY"):
        evaluate("true", task(status=status, failures=failures, completed=completed),
                 now=NOW, require_run=True)


def test_future_and_naive_timestamps_fail_closed():
    with pytest.raises(AutoDraftAcceptanceError, match="RUN_CLOCK_INVALID"):
        evaluate("true", task(completed=NOW + timedelta(minutes=5)), now=NOW)
    with pytest.raises(AutoDraftAcceptanceError, match="TIMESTAMP_INVALID"):
        evaluate("true", task(), now=NOW.replace(tzinfo=None))
    with pytest.raises(AutoDraftAcceptanceError, match="TIMESTAMP_INVALID"):
        evaluate("true", task(completed=NOW.replace(tzinfo=None)), now=NOW)


def test_untrusted_worker_metadata_never_enters_attestation():
    private = {**POLICY, "debug_cv": "PRIVATE-CV-DO-NOT-PRINT",
               "user_id": "USER-TOKEN-DO-NOT-PRINT", "source_url": "https://private.invalid"}
    rendered = json.dumps(evaluate("true", task(metadata=private), now=NOW, require_run=True))
    assert "PRIVATE-CV" not in rendered
    assert "USER-TOKEN" not in rendered
    assert "private.invalid" not in rendered


def test_cli_refuses_unsafe_poll_and_invalid_clock_without_echoing_dsn(monkeypatch, capsys):
    dsn = "postgresql://fake:PRIVATE-PASSWORD@127.0.0.1:9999/smartploy"
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", dsn)
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED", "true")
    assert main(["--wait-seconds", "121"]) == 3
    assert main(["--require-run", "--not-before", "invalid-clock"]) == 3
    out = capsys.readouterr()
    assert dsn not in out.out + out.err
    assert "HOLD" in out.err
    assert "INVALID_WAIT_LIMIT" in out.err
    assert "INVALID_NOT_BEFORE_TIME" in out.err
    assert "healthy_scheduled_run" not in out.out


def test_source_runtime_uses_worker_schedule_original_task_not_new_scheduler():
    from smartploy.worker_runtime import build_worker_task_specs
    import os
    # Task metadata/cadence match the ORIGINAL worker registry.
    # The function requires a DB URI but only declares specs, no connections.
    saved = os.environ.get("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED")
    try:
        os.environ["SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED"] = "true"
        specs = build_worker_task_specs("postgresql://synthetic:synthetic@localhost/smartploy")
        candidate = next(row for row in specs if row.task_id == task().task_id)
        assert candidate.task_kind == "application_draft"
        assert candidate.metadata == POLICY
    finally:
        if saved is None:
            os.environ.pop("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED", None)
        else:
            os.environ["SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED"] = saved

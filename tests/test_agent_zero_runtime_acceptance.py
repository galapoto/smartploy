"""SP36 acceptance: real task receipt, strict default OFF, no external actions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

import pytest

from smartploy.agent_zero_runtime_acceptance import (
    AgentZeroAcceptanceError, evaluate, main,
)
from smartploy.worker_schedule import WorkerTask


NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
POLICY = {
    "channel": "in_app_only",
    "external_actions_authorized": False,
    "employer_submission_authorized": False,
}


def task(
    *, enabled: bool = True, status: str = "healthy",
    completed: datetime | None = None, failures: int = 0,
    metadata: dict | None = None, cadence: int = 60,
) -> WorkerTask:
    return WorkerTask(
        task_id="application:agent-zero-reminders",
        task_kind="application_agent",
        enabled=enabled, cadence_seconds=cadence, next_run_at=NOW,
        last_status=status,
        last_completed_at=completed if completed is not None else NOW,
        consecutive_failures=failures,
        metadata=POLICY if metadata is None else metadata,
    )


def test_default_off_allows_absent_or_disabled_case_only():
    missing = evaluate("false", None, now=NOW)
    assert missing == {
        "schema": "smartploy.agent_zero.runtime.v1",
        "status": "disabled_by_operator",
        "task_registered": False, "task_enabled": False,
        "completed_run_verified": False,
        "candidate_reminder_delivered_verified": False,
        "employer_contacts_authorized": False,
        "external_actions_authorized": False,
    }
    assert evaluate("false", task(enabled=False), now=NOW)["status"] == "disabled_by_operator"
    with pytest.raises(AgentZeroAcceptanceError, match="STILL_ENABLED"):
        evaluate("false", task(), now=NOW)
    with pytest.raises(AgentZeroAcceptanceError, match="OPT_IN_REQUIRED"):
        evaluate("false", None, now=NOW, require_run=True)


@pytest.mark.parametrize("flag", ["yes", "1", " enabled", "", "false true"])
def test_invalid_worker_enable_flag_fails_closed(flag):
    with pytest.raises(AgentZeroAcceptanceError, match="FLAG_INVALID"):
        evaluate(flag, None, now=NOW)


def test_flag_true_requires_exact_registered_enabled_task():
    with pytest.raises(AgentZeroAcceptanceError, match="NOT_REGISTERED"):
        evaluate("true", None, now=NOW)
    with pytest.raises(AgentZeroAcceptanceError, match="NOT_ENABLED"):
        evaluate("true", task(enabled=False), now=NOW)


@pytest.mark.parametrize("field,value", [
    ("channel", "email"),
    ("external_actions_authorized", True),
    ("employer_submission_authorized", True),
    ("employer_submission_authorized", None),
])
def test_external_authority_mismatch_refuses_healthy_attestation(field, value):
    policy = dict(POLICY, **{field: value})
    with pytest.raises(AgentZeroAcceptanceError, match="POLICY_MISMATCH"):
        evaluate("true", task(metadata=policy), now=NOW, require_run=True)


def test_actual_fresh_run_after_container_start_is_required():
    recent = task(completed=NOW - timedelta(seconds=12))
    before = NOW - timedelta(seconds=15)
    result = evaluate(
        "true", recent, now=NOW, not_before=before, require_run=True,
    )
    assert result["status"] == "healthy_scheduled_run"
    assert result["completed_run_verified"] is True
    assert result["candidate_reminder_delivered_verified"] is False
    assert result["external_actions_authorized"] is False

    with pytest.raises(AgentZeroAcceptanceError, match="FRESH_RUN_MISSING"):
        evaluate(
            "true", recent, now=NOW,
            not_before=NOW - timedelta(seconds=4), require_run=True,
        )


def test_unrun_stale_or_failed_tasks_cannot_pass_released_worker_gate():
    waiting = task(status="never")
    assert evaluate("true", waiting, now=NOW)["status"] == "registered_waiting_for_run"
    with pytest.raises(AgentZeroAcceptanceError, match="RUN_NOT_HEALTHY"):
        evaluate("true", waiting, now=NOW, require_run=True)
    with pytest.raises(AgentZeroAcceptanceError, match="RUN_NOT_HEALTHY"):
        evaluate("true", task(failures=1), now=NOW, require_run=True)
    stale = task(completed=NOW - timedelta(minutes=20))
    assert evaluate("true", stale, now=NOW)["completed_run_verified"] is False
    with pytest.raises(AgentZeroAcceptanceError, match="FRESH_RUN_MISSING"):
        evaluate("true", stale, now=NOW, require_run=True)


def test_untrusted_clock_and_cadence_fail_before_release():
    with pytest.raises(AgentZeroAcceptanceError, match="CLOCK_INVALID"):
        evaluate("true", task(completed=NOW + timedelta(minutes=3)), now=NOW)
    with pytest.raises(AgentZeroAcceptanceError, match="CADENCE_INVALID"):
        evaluate("true", task(cadence=0), now=NOW)
    with pytest.raises(AgentZeroAcceptanceError, match="ACCEPTANCE_TIME"):
        evaluate("true", task(), now=NOW.replace(tzinfo=None))


def test_cli_never_leaks_a_database_url_or_false_success(monkeypatch, capsys):
    secret = "postgresql://fake:synthetic-private-password@localhost:9999/smartploy"
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", secret)
    monkeypatch.setenv("SMARTPLOY_WORKER_AGENT_ZERO_ENABLED", "true")
    code = main(["--require-run", "--not-before", "invalid-timestamp"])
    assert code == 3
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "HOLD" in captured.err
    assert "INVALID_NOT_BEFORE_TIME" in captured.err
    assert "healthy_scheduled_run" not in captured.out


def test_cli_rejects_unsafe_poll_time_before_database_access(monkeypatch, capsys):
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    assert main(["--wait-seconds", "121"]) == 3
    assert "INVALID_WAIT_LIMIT" in capsys.readouterr().err

"""Read-only application acceptance diagnostics must not overstate success."""
from __future__ import annotations

import json
import os
import sys

import pytest

from scripts import check_application_runtime as runtime
from smartploy.storage import PostgresJobRepository


def ready_tables():
    return {name: True for name in runtime.REQUIRED_TABLES}


def test_report_has_conservative_server_and_browser_boundaries():
    report = runtime.summarize(
        ready_tables(), active_jobs=75,
        local_ai={"configured": False, "ready": False, "model": ""},
        auth_mode="cloudflare",
    )
    assert report["ready_for_authenticated_browser_acceptance"] is True
    assert report["document_editor_backend_ready"] is True
    assert report["browser_packet_and_receipt_backend_ready"] is True
    assert report["local_ai"]["ready"] is False
    assert report["browser_form_test_completed"] is False
    assert report["real_employer_receipt_verified"] is False
    assert report["server_automatic_employer_submit_authorized"] is False
    assert report["private_cv_content_included"] is False
    assert report["database_credentials_included"] is False


def test_no_jobs_or_missing_receipt_table_prevents_browser_readiness():
    for tables, count in [
        (ready_tables(), 0),
        ({**ready_tables(), "smartploy_browser_receipts": False}, 5),
        ({**ready_tables(), "smartploy_application_workspaces": False}, 5),
    ]:
        report = runtime.summarize(
            tables, active_jobs=count,
            local_ai={"configured": True, "ready": True, "model": "qwen3:4b"},
            auth_mode="hybrid",
        )
        assert report["ready_for_authenticated_browser_acceptance"] is False
        assert report["browser_form_test_completed"] is False


def test_cli_status_checks_never_claim_live_browser_success(monkeypatch, capsys):
    report = runtime.summarize(
        ready_tables(), active_jobs=3,
        local_ai={"configured": True, "ready": False, "model": "qwen3:4b"},
        auth_mode="cloudflare",
    )
    monkeypatch.setattr(runtime, "check", lambda: report)
    monkeypatch.setattr(sys, "argv", ["check_application_runtime.py", "--require-browser-backend"])
    assert runtime.main() == 0
    assert json.loads(capsys.readouterr().out)["browser_extension_installed"] == "cannot_be_verified_from_server"

    monkeypatch.setattr(sys, "argv", ["check_application_runtime.py", "--require-local-ai"])
    assert runtime.main() == 4
    capsys.readouterr()

    def fail():
        raise RuntimeError("POSTGRES_PASSWORD=myverysecret from DSN")
    monkeypatch.setattr(runtime, "check", fail)
    monkeypatch.setattr(sys, "argv", ["check_application_runtime.py"])
    assert runtime.main() == 2
    captured = capsys.readouterr()
    assert "myverysecret" not in captured.err + captured.out
    assert "RuntimeError" in captured.err


@pytest.mark.skipif(not os.getenv("SMARTPLOY_TEST_DATABASE_URL"), reason="requires PostgreSQL")
def test_postgres_tables_are_present_after_real_migrations(monkeypatch):
    dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    PostgresJobRepository(dsn).migrate()
    monkeypatch.setenv("SMARTPLOY_DATABASE_URL", dsn)
    monkeypatch.setenv("SMARTPLOY_LOCAL_AI_ENABLED", "false")
    result = runtime.check()
    assert result["database_tables_ready"] is True
    assert result["document_editor_backend_ready"] is True
    assert result["browser_packet_and_receipt_backend_ready"] is True
    assert result["server_automatic_employer_submit_authorized"] is False

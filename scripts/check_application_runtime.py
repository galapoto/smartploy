#!/usr/bin/env python3
"""Private, read-only SmartPloy application release readiness.

Run *inside* the API container. Nothing is modified, no private profile
records are selected, no tokens or DSNs are printed, and no employer sites
are contacted. This report is not a substitute for a user-approved live
browser acceptance test.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from psycopg import connect

from smartploy.local_drafting import LocalDraftClient, LocalDraftSettings


REQUIRED_TABLES = (
    "smartploy_jobs",
    "smartploy_cv_files",
    "smartploy_profile_facts",
    "smartploy_application_workspaces",
    "smartploy_browser_receipts",
)
SCHEMA = "smartploy.application-readiness.v1"


def summarize(
    tables: dict[str, bool],
    *,
    active_jobs: int,
    local_ai: dict[str, Any],
    auth_mode: str,
) -> dict[str, Any]:
    all_tables = all(tables.get(name) is True for name in REQUIRED_TABLES)
    document_ready = all(tables.get(name) is True for name in (
        "smartploy_cv_files", "smartploy_profile_facts", "smartploy_application_workspaces",
    ))
    packet_ready = document_ready and tables.get("smartploy_browser_receipts") is True
    browser_review = packet_ready and active_jobs > 0
    return {
        "report": SCHEMA,
        "database_tables_ready": all_tables,
        "table_presence": tables,
        "active_job_count": active_jobs,
        "document_editor_backend_ready": document_ready,
        "browser_packet_and_receipt_backend_ready": packet_ready,
        "ready_for_authenticated_browser_acceptance": browser_review,
        "configured_identity_mode": auth_mode if auth_mode in {"cloudflare", "oidc", "hybrid"} else "other",
        "local_ai": {
            "configured": bool(local_ai.get("configured")),
            "ready": bool(local_ai.get("ready")),
            "model": str(local_ai.get("model", ""))[:95],
            "endpoint_reachable": bool(local_ai.get("endpoint_reachable")),
            "failure_category": str(local_ai.get("failure_category", "disabled"))[:40],
            "external_ai_forwarding": False,
        },
        "browser_extension_installed": "cannot_be_verified_from_server",
        "browser_form_test_completed": False,
        "real_employer_receipt_verified": False,
        "independently_verified_submissions": "not_measured",
        "server_automatic_employer_submit_authorized": False,
        "private_cv_content_included": False,
        "database_credentials_included": False,
        "employer_network_actions_performed": False,
    }


def check() -> dict[str, Any]:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("No private SmartPloy database connection is configured")
    tables: dict[str, bool] = {}
    active_jobs = 0
    with connect(dsn, connect_timeout=4, options="-c default_transaction_read_only=on") as connection:
        with connection.cursor() as cursor:
            for name in REQUIRED_TABLES:
                cursor.execute("SELECT to_regclass(%s)", ("public." + name,))
                tables[name] = cursor.fetchone()[0] is not None
            if tables.get("smartploy_jobs"):
                cursor.execute("SELECT COUNT(*) FROM smartploy_jobs WHERE source_current = true")
                active_jobs = int(cursor.fetchone()[0])

    model_client = LocalDraftClient(LocalDraftSettings.from_env())
    try:
        model = model_client.status()
    finally:
        model_client.close()
    return summarize(
        tables, active_jobs=active_jobs, local_ai=model,
        auth_mode=os.getenv("SMARTPLOY_AUTH_MODE", ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only production application readiness report")
    parser.add_argument("--require-browser-backend", action="store_true",
                        help="Nonzero when application editor or browser receipt storage is missing")
    parser.add_argument("--require-local-ai", action="store_true",
                        help="Nonzero when local-only Ollama drafting has not been enabled and reached")
    args = parser.parse_args()
    try:
        report = check()
    except Exception as exc:
        # Exception strings may include DSNs and other private values; never echo.
        print(json.dumps({"report": SCHEMA, "error": "read_only_readiness_check_failed",
                          "exception_type": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if args.require_browser_backend and not report["ready_for_authenticated_browser_acceptance"]:
        return 3
    if args.require_local_ai and not report["local_ai"]["ready"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

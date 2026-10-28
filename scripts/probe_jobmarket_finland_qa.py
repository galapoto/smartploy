#!/usr/bin/env python3
"""SP60: credential-gated, database-free KEHA P67 QA connectivity check.

By default this is an offline configuration check. --execute performs two
explicit, bounded, read-only POST searches against the exact KEHA QA P67
endpoint only. It never starts the worker, writes postings, invokes ObumAI,
submits applications, or prints credentials, record bodies or raw exceptions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
from typing import Any

import httpx

from smartploy.sources.jobmarket_finland import (
    TEST_ENDPOINT,
    JobMarketFinlandAPIError,
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
)


SCHEMA = "smartploy.keha-p67.qa-smoke.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 250


class QASmokeRejected(ValueError):
    """A fixed non-secret code, never an upstream error body."""


def _validate_window(minutes: int) -> None:
    if type(minutes) is not int or not 5 <= minutes <= 120:
        raise QASmokeRejected("INVALID_LOOKBACK_MINUTES")


def validate_qa_environment(environment: dict[str, str]) -> None:
    """No QA credential may enable a production worker or select a P67 prod URL."""
    mode = str(environment.get("JOBMARKET_FINLAND_ENVIRONMENT", "test")).strip().casefold()
    if mode != "test":
        raise QASmokeRejected("QA_ENVIRONMENT_ONLY")
    endpoint = str(environment.get("JOBMARKET_FINLAND_ENDPOINT", "")).strip()
    if endpoint and endpoint != TEST_ENDPOINT:
        raise QASmokeRejected("QA_ENDPOINT_ONLY")
    enabled = str(environment.get("JOBMARKET_FINLAND_API_ENABLED", "false")).strip().casefold()
    if enabled not in {"false", "0", "no", "off", ""}:
        raise QASmokeRejected("QA_WORKER_MUST_REMAIN_DISABLED")


def qa_settings(environment: dict[str, str]) -> JobMarketFinlandSettings:
    validate_qa_environment(environment)
    # The subscribed key is read only in memory, never passed to argparse,
    # a URL, a job observation or stdout. QA keys are not production keys.
    key = str(environment.get("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "")).strip()
    if not key:
        raise QASmokeRejected("QA_KEY_MISSING")
    return JobMarketFinlandSettings(
        environment="test",
        endpoint=TEST_ENDPOINT,
        subscription_key=key,
        posting_languages=("fi", "en", "sv"),
        timeout_seconds=15,
        max_bytes=MAX_BYTES,
        max_items=MAX_ITEMS,
    )


def run_qa_probe(
    settings: JobMarketFinlandSettings,
    *,
    minutes: int = 30,
    now: datetime | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Execute the existing P67 adapter twice; disclose counts only.

    This does not use SmartployService, PostgreSQL, source observations,
    persistent scheduler tasks or candidate files. Zero QA postings in the
    selected modified window still proves a valid successful API response.
    """
    _validate_window(minutes)
    if settings.environment != "test" or settings.endpoint != TEST_ENDPOINT:
        raise QASmokeRejected("QA_ENDPOINT_ONLY")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise QASmokeRejected("QA_CLOCK_MUST_BE_TIMEZONE_AWARE")
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    begin = current - timedelta(minutes=minutes)

    def iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    adapter = JobMarketFinlandAdapter(settings, http_client=http_client)
    try:
        published = adapter.fetch_window(
            status="PUBLISHED", modified_from=iso(begin), modified_to=iso(current),
        )
        archived = adapter.fetch_window(
            status="ARCHIVED", modified_from=iso(begin), modified_to=iso(current),
        )
        return {
            "schema": SCHEMA,
            "status": "qa_reachable",
            "environment": "test",
            "qa_endpoint_verified": True,
            "published_query_passed": True,
            "archived_query_passed": True,
            "modified_window_minutes": minutes,
            "published_posting_count": len(published.observations),
            "archived_posting_count": len(archived.archived),
            "production_credentials_used": False,
            "production_database_writes": 0,
            "qa_job_records_saved": 0,
            "applicant_records_accessed": 0,
            "external_ai_forwarding": False,
            "employer_applications_sent": 0,
        }
    finally:
        adapter.close()


def _error_class(exc: Exception) -> str:
    # Fixed allowlist only. Never print the exception, response body or headers,
    # which could contain the KEHA key, infrastructure details or job content.
    if isinstance(exc, QASmokeRejected):
        return str(exc)
    if isinstance(exc, JobMarketFinlandAPIError):
        description = str(exc)
        if "HTTP 401" in description or "HTTP 403" in description:
            return "QA_AUTHORIZATION_OR_IP_ACCESS_DENIED"
        if "HTTP 429" in description:
            return "QA_RATE_LIMITED"
        if "HTTP 5" in description:
            return "QA_UPSTREAM_UNAVAILABLE"
        if "response exceeds" in description:
            return "QA_RESPONSE_LIMIT"
        if "request failed" in description:
            return "QA_NETWORK_OR_TLS"
        return "QA_RESPONSE_CONTRACT_FAILED"
    return "QA_SMOKE_UNEXPECTED_FAILURE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Make exactly two QA-only POST searches with an already loaded private key")
    parser.add_argument("--minutes", type=int, default=30,
                        help="Bound the modified window to 5-120 minutes (default 30)")
    args = parser.parse_args(argv)
    try:
        _validate_window(args.minutes)
        validate_qa_environment(os.environ)
        if not args.execute:
            print(json.dumps({
                "schema": SCHEMA, "status": "offline_configuration_only",
                "qa_endpoint": TEST_ENDPOINT,
                "credential_present": bool(os.getenv("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "").strip()),
                "network_requests": 0, "production_database_writes": 0,
                "employer_applications_sent": 0, "live_qa_verified": False,
            }, sort_keys=True))
            return 0
        result = run_qa_probe(qa_settings(os.environ), minutes=args.minutes)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "hold", "reason": _error_class(exc),
            "production_database_writes": 0, "employer_applications_sent": 0,
            "live_qa_verified": False,
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

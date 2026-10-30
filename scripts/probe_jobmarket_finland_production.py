#!/usr/bin/env python3
"""SP76: read-only, credential-gated KEHA P67 production acceptance probe.

Offline by default. --execute makes precisely two bounded production POST
SEARCH requests (PUBLISHED, then ARCHIVED). It never opens PostgreSQL, runs
SmartPloy workers, saves jobs, forwards postings, touches CVs, or submits
employer applications. It intentionally never prints credentials, URLs with
secrets, response bodies, headers, exceptions or individual job records.
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
    PRODUCTION_ENDPOINT,
    JobMarketFinlandAPIError,
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
)

SCHEMA = "smartploy.keha-p67.production-smoke.v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 5000


class ProductionSmokeRejected(ValueError):
    """Fixed failure codes only, never the upstream response body."""


def validate_production_probe_environment(environment: dict[str, str]) -> None:
    if str(environment.get("JOBMARKET_FINLAND_ENVIRONMENT", "")).strip().casefold() != "production":
        raise ProductionSmokeRejected("PRODUCTION_ENVIRONMENT_REQUIRED")
    if str(environment.get("SMARTPLOY_ENVIRONMENT", "production")).strip().casefold() != "production":
        raise ProductionSmokeRejected("SMARTPLOY_PRODUCTION_CONTEXT_REQUIRED")
    endpoint = str(environment.get("JOBMARKET_FINLAND_ENDPOINT", "")).strip()
    if endpoint and endpoint != PRODUCTION_ENDPOINT:
        raise ProductionSmokeRejected("OFFICIAL_PRODUCTION_ENDPOINT_REQUIRED")
    # The probe must never double as a worker activation command.
    enabled = str(environment.get("JOBMARKET_FINLAND_API_ENABLED", "false")).strip().casefold()
    if enabled not in {"false", "0", "no", "off", ""}:
        raise ProductionSmokeRejected("PRODUCTION_WORKER_MUST_REMAIN_DISABLED")


def production_settings(environment: dict[str, str]) -> JobMarketFinlandSettings:
    validate_production_probe_environment(environment)
    key = str(environment.get("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "")).strip()
    if not key:
        raise ProductionSmokeRejected("PRODUCTION_KEY_MISSING")
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ProductionSmokeRejected("PRODUCTION_KEY_FORMAT_INVALID")
    # Reuse the exact original adapter and canonical HTTPS endpoint. The key
    # never becomes an argument, URL, log line, persisted record or frontend.
    return JobMarketFinlandSettings(
        environment="production",
        endpoint=PRODUCTION_ENDPOINT,
        subscription_key=key,
        posting_languages=("fi", "en", "sv"),
        timeout_seconds=18,
        max_bytes=MAX_BYTES,
        max_items=MAX_ITEMS,
    )


def _window(minutes: int, now: datetime | None) -> tuple[str, str]:
    if type(minutes) is not int or not 5 <= minutes <= 120:
        raise ProductionSmokeRejected("INVALID_PRODUCTION_LOOKBACK")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ProductionSmokeRejected("PRODUCTION_CLOCK_MUST_BE_UTC_AWARE")
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    begin = current - timedelta(minutes=minutes)
    def iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")
    return iso(begin), iso(current)


def run_production_probe(
    settings: JobMarketFinlandSettings,
    *,
    minutes: int = 30,
    now: datetime | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    start, end = _window(minutes, now)
    if settings.environment != "production" or settings.endpoint != PRODUCTION_ENDPOINT:
        raise ProductionSmokeRejected("OFFICIAL_PRODUCTION_ENDPOINT_REQUIRED")
    adapter = (
        JobMarketFinlandAdapter(settings, http_client=http_client)
        if http_client is not None else JobMarketFinlandAdapter(settings)
    )
    try:
        published = adapter.fetch_window(
            status="PUBLISHED", modified_from=start, modified_to=end,
        )
        archived = adapter.fetch_window(
            status="ARCHIVED", modified_from=start, modified_to=end,
        )
        # No records, URLs, external IDs or employer names in this receipt.
        return {
            "schema": SCHEMA,
            "status": "production_search_reachable",
            "environment": "production",
            "production_endpoint_verified": True,
            "published_query_passed": True,
            "archived_query_passed": True,
            "lookback_minutes": minutes,
            "published_count": len(published.observations),
            "archived_count": len(archived.archived),
            "nonempty_published_payload_verified": bool(published.observations),
            "nonempty_archived_payload_verified": bool(archived.archived),
            "database_writes": 0,
            "applicant_records_accessed": 0,
            "external_ai_forwarding": False,
            "employer_applications_sent": 0,
            "worker_activation": False,
            "production_ingestion_verified": False,
        }
    finally:
        adapter.close()


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, ProductionSmokeRejected):
        return str(exc)
    if isinstance(exc, JobMarketFinlandAPIError):
        # Adapter errors have fixed phrasing, but only these *allowlisted*
        # markers may escape. Never disclose upstream bodies or a raw error.
        message = str(exc)
        if "HTTP 401" in message or "HTTP 403" in message:
            return "PRODUCTION_AUTHORIZATION_OR_IP_ACCESS_DENIED"
        if "HTTP 429" in message:
            return "PRODUCTION_RATE_LIMITED"
        if "HTTP 5" in message:
            return "PRODUCTION_UPSTREAM_UNAVAILABLE"
        if "response exceeds" in message:
            return "PRODUCTION_RESPONSE_LIMIT"
        if "request failed" in message:
            return "PRODUCTION_NETWORK_OR_TLS"
        return "PRODUCTION_RESPONSE_CONTRACT_INVALID"
    return "PRODUCTION_SMOKE_UNEXPECTED_FAILURE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Run two read-only KEHA P67 production POST searches; no database writes",
    )
    parser.add_argument(
        "--minutes", type=int, default=30,
        help="Modified window 5-120 minutes, default 30",
    )
    args = parser.parse_args(argv)
    try:
        _window(args.minutes, None)
        validate_production_probe_environment(os.environ)
        if not args.execute:
            print(json.dumps({
                "schema": SCHEMA,
                "status": "offline_configuration_only",
                "environment": "production",
                "production_endpoint": PRODUCTION_ENDPOINT,
                "credential_present": bool(os.getenv(
                    "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "").strip()),
                "network_requests": 0,
                "database_writes": 0,
                "employer_applications_sent": 0,
                "live_production_verified": False,
                "worker_activation": False,
            }, sort_keys=True))
            return 0
        result = run_production_probe(production_settings(os.environ), minutes=args.minutes)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "schema": SCHEMA,
            "status": "hold",
            "reason": _safe_error_code(exc),
            "database_writes": 0,
            "employer_applications_sent": 0,
            "live_production_verified": False,
            "worker_activation": False,
        }, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

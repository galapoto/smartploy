#!/usr/bin/env python3
"""Emit deterministic, synthetic-only SmartPloy search/evidence quality evidence.

Never reads production databases, private candidate profiles or ATS providers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from smartploy.matching_quality import (
    DEFAULT_FIXTURE, evaluate_fixture, load_fixture,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Finnish/English SmartPloy quality checks")
    parser.add_argument(
        "--fixture", type=Path, default=DEFAULT_FIXTURE,
        help="Versioned, synthetic benchmark JSON path (no real CVs or posting data)",
    )
    args = parser.parse_args()
    try:
        report = evaluate_fixture(load_fixture(args.fixture))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "schema": "smartploy.matching-quality-report.v1",
            "synthetic_only": True,
            "error": "invalid_or_unreadable_benchmark_fixture",
            "exception_type": type(exc).__name__,
        }), file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["failed_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

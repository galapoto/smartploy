#!/usr/bin/env python3
"""Import an operator-reviewed Smartploy profile JSON file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from smartploy.profile import facts_from_json
from smartploy.profile_storage import PostgresProfileRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--profile-id", default=os.getenv("SMARTPLOY_PROFILE_ID", "default"))
    args = parser.parse_args()

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("SMARTPLOY_DATABASE_URL is required")

    value = json.loads(args.path.read_text(encoding="utf-8"))
    facts = facts_from_json(value)
    repository = PostgresProfileRepository(dsn, profile_id=args.profile_id)
    repository.migrate()
    for fact in facts:
        repository.upsert_fact(fact)
    profile = repository.profile()
    print(profile.summary())
    print(f"approved_fact_count={profile.approved_evidence()['approved_fact_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

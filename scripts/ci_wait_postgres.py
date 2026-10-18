"""Readiness check for SmartPloy's ephemeral ObumDelivery PostgreSQL fixture.

Cannot connect to a production database: the only accepted DSN is the
hard-coded, synthetic internal Woodpecker service. No connection error or
credential is written into logs. This is not a deployment or release check.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Callable, Any

from scripts.obumdelivery_ci_gate import current

SYNTHETIC_DSN = (
    "postgresql://smartploy:synthetic-local-ci-only"
    "@postgres:5432/smartploy_test"
)


class FixtureAdmissionError(ValueError):
    """The configured connection is outside the ephemeral CI fixture."""


def validate_fixture_dsn(dsn: str) -> None:
    # Reject every other PostgreSQL host, port, user, database, password,
    # credential and URL option, before any network operation.
    if not isinstance(dsn, str) or dsn != SYNTHETIC_DSN:
        raise FixtureAdmissionError("NON_SYNTHETIC_DATABASE_TARGET_STOP")


def await_fixture(
    dsn: str,
    opener: Callable[..., Any],
    *,
    timeout_seconds: float = 60.0,
    clock: Callable[[], float] = time.monotonic,
    nap: Callable[[float], None] = time.sleep,
) -> int:
    """Attempt only SELECT 1 until a bounded deadline; fail closed.

    Openers are only called after validating the exact synthetic DSN.
    Connection errors or DSN values never appear in public exceptions.
    """
    validate_fixture_dsn(dsn)
    if not 0 < timeout_seconds <= 180:
        raise FixtureAdmissionError("UNBOUNDED_FIXTURE_WAIT_STOP")
    deadline = clock() + timeout_seconds
    attempts = 0
    while True:
        attempts += 1
        try:
            with opener(dsn, connect_timeout=2) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    if cursor.fetchone() != (1,):
                        raise FixtureAdmissionError("NOT_READY")
            return attempts
        except Exception:
            remaining = deadline - clock()
            if remaining <= 0:
                raise FixtureAdmissionError("SYNTHETIC_POSTGRES_NOT_READY_STOP") from None
            nap(min(1.0, remaining))


def main() -> int:
    try:
        # Independently reject checkout or Woodpecker metadata mismatch.
        current()
        dsn = os.environ.get("SMARTPLOY_TEST_DATABASE_URL", "")
        validate_fixture_dsn(dsn)
        # Installed by the earlier source-pinned pip stage.
        import psycopg

        attempts = await_fixture(dsn, psycopg.connect)
        print(f"SYNTHETIC_POSTGRES_READY attempts={attempts}; release_gate=HOLD")
        return 0
    except Exception:
        print("OBUMDELIVERY_SYNTHETIC_POSTGRES_HOLD", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

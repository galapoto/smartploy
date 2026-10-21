"""Pure, no-network SmartPloy Woodpecker fixture readiness contract tests."""
from pathlib import Path

import pytest

from scripts.ci_wait_postgres import (
    FixtureAdmissionError, SYNTHETIC_DSN, await_fixture, validate_fixture_dsn,
)


class FakeConnection:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self

    def execute(self, sql):
        self.executed.append(sql)

    def fetchone(self):
        return (1,)


@pytest.mark.parametrize("bad", [
    "", None, "postgres://smartploy:synthetic-local-ci-only@postgres:5432/smartploy_test",
    SYNTHETIC_DSN + "?sslmode=disable",
    SYNTHETIC_DSN.replace("@postgres:", "@prod-db:"),
    SYNTHETIC_DSN.replace("smartploy_test", "smartploy"),
    SYNTHETIC_DSN.replace("synthetic-local-ci-only", "actual-credential"),
    SYNTHETIC_DSN.replace(":5432/", ":5433/"),
])
def test_only_internal_synthetic_postgres_is_accepted(bad):
    with pytest.raises(FixtureAdmissionError, match="NON_SYNTHETIC"):
        validate_fixture_dsn(bad)


def test_successful_read_only_probe():
    conn = FakeConnection()
    attempted = []

    def connect(dsn, *, connect_timeout):
        attempted.append((dsn, connect_timeout))
        return conn

    assert await_fixture(SYNTHETIC_DSN, connect) == 1
    assert attempted == [(SYNTHETIC_DSN, 2)]
    assert conn.executed == ["SELECT 1"]


def test_retries_are_bounded_and_errors_do_not_leak_secrets():
    seen = []
    ticks = iter(range(10))

    def fail(_dsn, *, connect_timeout):
        seen.append(connect_timeout)
        raise OSError("sensitive-password-not-for-logs")

    with pytest.raises(FixtureAdmissionError) as exc:
        await_fixture(SYNTHETIC_DSN, fail, timeout_seconds=3,
                      clock=lambda: next(ticks), nap=lambda _delay: None)
    assert "sensitive-password" not in str(exc.value)
    assert len(seen) == 3


def test_a_production_target_is_rejected_before_any_network_call():
    invoked = []

    def must_not_connect(_dsn, **kwargs):
        invoked.append(kwargs)
        raise AssertionError("unexpected network access")

    with pytest.raises(FixtureAdmissionError):
        await_fixture(SYNTHETIC_DSN.replace("@postgres", "@db-prod"),
                      must_not_connect)
    assert invoked == []


@pytest.mark.parametrize("bad", [-1, 0, 181, 9999])
def test_no_unbounded_or_negative_deadline(bad):
    with pytest.raises(FixtureAdmissionError, match="UNBOUNDED"):
        await_fixture(SYNTHETIC_DSN, lambda *_a, **_k: None,
                      timeout_seconds=bad)


def test_woodpecker_browser_receipt_runs_only_after_browser_success():
    yaml_path = Path(__file__).resolve().parents[1] / ".woodpecker" / "smartploy.yaml"
    source = yaml_path.read_text(encoding="utf-8")
    python_section = source.split("  - name: python-postgres\n", 1)[1].split("  - name: web-browser\n", 1)[0]
    browser_section = source.split("  - name: web-browser\n", 1)[1].split("  - name: exact-source-hold-receipt\n", 1)[0]
    final_section = source.split("  - name: exact-source-hold-receipt\n", 1)[1]
    assert "- python3 -B -m scripts.ci_wait_postgres" in python_section
    assert "- python3 -B scripts/obumdelivery_ci_gate.py mark-browser" not in browser_section
    assert "depends_on: [web-browser]" in final_section
    assert final_section.index("mark-browser") < final_section.index(" final")
    assert "python-postgres" in browser_section

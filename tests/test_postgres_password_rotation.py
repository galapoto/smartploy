"""Guard the existing-SHA SmartPloy database credential rotation procedure.

No test changes the production server. The optional Postgres integration
creates and drops a synthetic CI role in the isolated test database only.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/personal/scripts/rotate-postgres-password.py"
spec = importlib.util.spec_from_file_location("smartploy_password_rotation", SCRIPT)
assert spec is not None and spec.loader is not None
rotation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotation)


def test_rotation_script_compiles_and_requires_explicit_host_authorization(monkeypatch):
    source = SCRIPT.read_text(encoding="utf-8")
    compile(source, str(SCRIPT), "exec")
    assert "production-operation.lock" in source
    assert "--expected-sha" in source
    assert "--apply" in source
    assert "obum-core-01" in source
    assert "SMARTPLOY_IMAGE_TAG" in source
    assert "fc94e78" not in source  # no automatic approval of stale revisions
    monkeypatch.setattr(rotation.os, "geteuid", lambda: 1000)
    with pytest.raises(rotation.RotationError, match="run_as_root"):
        rotation.main(["--apply", "--expected-sha", "1" * 40])


def test_unique_private_env_replacement_preserves_other_secrets_and_policy():
    text = (
        "# private config\n"
        "POSTGRES_DB=smartploy\n"
        "POSTGRES_USER=smartploy\n"
        "POSTGRES_PASSWORD=old-local-synthetic-password-long-enough\n"
        "SMARTPLOY_OIDC_CLIENT_ID=public-synthetic-id\n"
        "SMARTPLOY_OIDC_ISSUER=https://auth.komplyint.fi\n"
        "SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED=true\n"
    )
    values = rotation.settings(text)
    assert len(values) == 6
    new = rotation.replace_password(text, "different-new-synthetic-secret-longer-than-24")
    assert "old-local-synthetic-password-long-enough" not in new
    assert new.count("POSTGRES_PASSWORD=") == 1
    assert "SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED=true" in new
    assert "SMARTPLOY_OIDC_ISSUER=https://auth.komplyint.fi" in new
    assert "SMARTPLOY_OIDC_CLIENT_ID=public-synthetic-id" in new
    assert rotation.settings(new)["POSTGRES_PASSWORD"] == "different-new-synthetic-secret-longer-than-24"


@pytest.mark.parametrize("bad", [
    "POSTGRES_PASSWORD=first\nPOSTGRES_PASSWORD=second\n",
    "POSTGRES_PASSWORD=\nPOSTGRES_PASSWORD=second\n",
    " POSTGRES_PASSWORD=not-a-real-key\n",
    "POSTGRES_PASSWORD=broken\nUNPARSEABLE\n",
])
def test_rotation_refuses_ambiguous_or_malformed_configuration(bad):
    with pytest.raises(rotation.RotationError):
        rotation.settings(bad) if "UNPARSEABLE" in bad or " POSTGRES_PASSWORD" in bad else rotation.replace_password(
            bad, "completely-new-synthetic-secret-password"
        )


def test_scram_sql_never_includes_plaintext_and_uses_fresh_random_salt():
    secret = "private-new-synthetic-password-never-log-this-123456"
    sql1, sql2 = rotation.sql_change("smartploy", secret), rotation.sql_change("smartploy", secret)
    assert secret not in sql1
    assert secret not in sql2
    assert sql1 != sql2
    assert sql1.startswith('ALTER ROLE "smartploy" WITH LOGIN PASSWORD ')
    assert sql1.count("SCRAM-SHA-256$4096:") == 1
    assert re.fullmatch(
        r'ALTER ROLE "smartploy" WITH LOGIN PASSWORD '
        r"'SCRAM-SHA-256\$4096:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+';\n",
        sql1,
    )
    for bad in ('smartploy";DROP ROLE smartploy;--', "postgres\n", "other role"):
        with pytest.raises(rotation.RotationError):
            rotation.sql_change(bad, secret)


def test_private_atomic_write_and_snapshot_are_permission_restricted(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    file = private / "env"
    file.write_text("POSTGRES_PASSWORD=synthetic-old-long-password\n", encoding="utf-8")
    saved = rotation.make_snapshot(file, tmp_path / "secret_backups")
    assert saved.read_bytes() == file.read_bytes()
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert stat.S_IMODE(saved.parent.stat().st_mode) == 0o700
    rotation.atomic_private_write(file, "POSTGRES_PASSWORD=synthetic-new-long-password\n")
    assert file.read_text(encoding="utf-8") == "POSTGRES_PASSWORD=synthetic-new-long-password\n"
    assert saved.read_text(encoding="utf-8") == "POSTGRES_PASSWORD=synthetic-old-long-password\n"
    assert stat.S_IMODE(file.stat().st_mode) == 0o600


def test_subprocess_failures_do_not_echo_secret_output():
    synthetic = "DONT-PRINT-THIS-DATABASE-SECRET"
    with pytest.raises(rotation.RotationError) as caught:
        rotation.call([sys.executable, "-c",
                       f"import sys; print({synthetic!r}); sys.exit(2)"])
    assert synthetic not in str(caught.value)


def test_rotation_is_explicitly_old_release_only_no_oidc_change_or_build():
    source = SCRIPT.read_text(encoding="utf-8")
    for mandatory in (
        "deployed-sha", "production-operation.lock", "backup.sh",
        "SMARTPLOY_BACKUP_SKIP_RETENTION", "private-config",
        "docker", "compose", "postgres", "api", "worker",
        "expected_image", "old_password_revoked=true",
        "private_config_updated=true", "identity_mode=unchanged_cloudflare",
    ):
        assert mandatory in source
    assert 'dc("up", "-d", "--wait"' in source
    assert "--force-recreate" in source
    assert "docker build" in source and "do NOT run docker build" in source
    assert "SMARTPLOY_PRODUCTION_IDENTITY_MODE" not in source
    assert "SMARTPLOY_OIDC_CLIENT_ID=" not in source


@pytest.mark.skipif(
    not os.getenv("SMARTPLOY_TEST_DATABASE_URL", ""),
    reason="isolated PostgreSQL fixture not configured",
)
def test_postgres_17_accepts_scram_verifier_and_rejects_old_password():
    """Actual PostgreSQL authentication acceptance, not a regex-only test."""
    from psycopg import OperationalError, connect, sql
    from psycopg.conninfo import conninfo_to_dict

    admin_dsn = os.environ["SMARTPLOY_TEST_DATABASE_URL"]
    role = "rotation_ci_" + uuid4().hex[:16]
    old = "synthetic-pre-rotation-secret-password-0000"
    new = "synthetic-post-rotation-secret-password-1111"
    config = conninfo_to_dict(admin_dsn)
    with connect(admin_dsn, autocommit=True) as admin:
        with admin.cursor() as cur:
            # PostgreSQL DDL does not accept a server-side $1 placeholder
            # for CREATE ROLE PASSWORD. Create the isolated test role first,
            # then reuse the exact pre-encoded SCRAM verifier writer.
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            cur.execute(rotation.sql_change(role, old))
        try:
            before = dict(config, user=role, password=old, connect_timeout=5)
            after = dict(config, user=role, password=new, connect_timeout=5)
            with connect(**before) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    assert cur.fetchone() == (1,)
            with admin.cursor() as cur:
                cur.execute(rotation.sql_change(role, new))
                cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s", (role,))
                verifier = cur.fetchone()[0]
            assert verifier.startswith("SCRAM-SHA-256$4096:")
            assert old not in verifier and new not in verifier
            with pytest.raises(OperationalError):
                connect(**before)
            with connect(**after) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    assert cur.fetchone() == (1,)
        finally:
            with admin.cursor() as cur:
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

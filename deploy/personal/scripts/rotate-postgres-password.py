#!/usr/bin/env python3
"""One-shot SmartPloy PostgreSQL credential rotation for the EXISTING live release.

Run locally as root on obum-core-01 with --apply --expected-sha <full SHA>.
Reuses the live Compose manifest, private env, backup.sh and production lock.
Neither the previous nor generated password is placed in argv, output or Git.
This does NOT enable OIDC, merge code or submit employer applications.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = Path("/srv/obum/stacks/smartploy")
ROLE = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,62}\Z")
PASSWORD = re.compile(r"[A-Za-z0-9._~-]{24,}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
PORT = re.compile(r"[0-9]{4,5}\Z")


class RotationError(RuntimeError):
    pass


def settings(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key):
            raise RotationError("invalid_private_env_line")
        if key in result:
            raise RotationError("duplicate_private_env_key")
        result[key] = value
    return result


def replace_password(text: str, value: str) -> str:
    if not PASSWORD.fullmatch(value):
        raise RotationError("invalid_generated_password")
    matches = re.findall(r"^POSTGRES_PASSWORD=.*$", text, re.MULTILINE)
    if len(matches) != 1:
        raise RotationError("password_setting_missing_or_duplicated")
    return re.sub(r"^POSTGRES_PASSWORD=.*$", "POSTGRES_PASSWORD=" + value, text, count=1, flags=re.MULTILINE)


def sql_change(role: str, password: str) -> str:
    if not ROLE.fullmatch(role) or not PASSWORD.fullmatch(password):
        raise RotationError("invalid_database_role_or_password")
    # Reuse the PostgreSQL 17 SCRAM-SHA-256 verifier protocol rather than
    # sending the plaintext credential in an ALTER ROLE statement.
    # PostgreSQL accepts this pre-encoded verifier as-is. Even if a database
    # administrator enabled log_statement=ddl, the SQL never reveals the
    # newly generated plain password. 4096 PBKDF2 iterations match the
    # standard SCRAM server implementation, with a fresh 128-bit salt.
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 4096)
    stored_key = hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest()
    server_key = hmac.digest(salted, b"Server Key", "sha256")
    b64 = lambda data: base64.b64encode(data).decode("ascii")
    verifier = f"SCRAM-SHA-256$4096:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"
    # Only this SCRAM verifier goes into psql stdin; never any cleartext.
    return f'ALTER ROLE "{role}" WITH LOGIN PASSWORD \'{verifier}\';\n'


def atomic_private_write(path: Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=".env-credential-rotation-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def call(args: list[str], *, data: str | None = None, timeout: int = 90,
         env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args, input=data, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, env=env, check=False,
    )
    if check and result.returncode:
        # Deliberately never print subprocess output: Docker Compose may
        # otherwise echo private configuration or a failed SQL statement.
        raise RotationError("private_operation_failed")
    return result


def verify_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RotationError("private_env_missing_or_symlink")
    info = path.stat()
    if info.st_uid != 0 or (stat.S_IMODE(info.st_mode) & 0o077):
        raise RotationError("private_env_permissions_or_owner")
    return path.read_text(encoding="utf-8")


def make_snapshot(path: Path, backup_dir: Path) -> Path:
    if backup_dir.is_symlink():
        raise RotationError("private_backup_directory_symlink")
    backup_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    target = backup_dir / ("env-before-password-rotation-" +
                           time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) +
                           "-" + secrets.token_hex(4))
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(path.read_bytes())
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Safely rotate ONLY SmartPloy's existing PostgreSQL role")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    if not args.apply:
        raise RotationError("explicit_apply_required")
    if os.geteuid() != 0 or socket.gethostname().split(".")[0] != "obum-core-01":
        raise RotationError("run_as_root_on_obum_core_01_only")
    if SHA.fullmatch(args.expected_sha) is None:
        raise RotationError("invalid_expected_live_sha")
    env_file = REPO / "deploy/personal/env"
    original = verify_file(env_file)
    values = settings(original)
    username, dbname, old = (values.get(name, "") for name in (
        "POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"))
    if not ROLE.fullmatch(username) or not ROLE.fullmatch(dbname) or not PASSWORD.fullmatch(old):
        raise RotationError("invalid_existing_database_configuration")
    state_dir = Path(values.get("SMARTPLOY_DEPLOY_STATE_DIR") or
                     "/srv/obum/data/smartploy/deploy-state")
    if not state_dir.is_absolute() or state_dir.is_symlink():
        raise RotationError("invalid_state_directory")
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_dir.chmod(0o700)
    lock_path = state_dir / "production-operation.lock"
    if lock_path.is_symlink():
        raise RotationError("production_lock_symlink")
    lockfd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RotationError("another_production_operation_is_running") from exc
        recorded = (state_dir / "deployed-sha").read_text(encoding="ascii").strip()
        checked_out = call(["git", "-C", str(REPO), "rev-parse", "HEAD"]).stdout.strip()
        if recorded != args.expected_sha or checked_out != recorded:
            raise RotationError("running_release_git_sha_mismatch")
        profile = state_dir / "deployed-auth-profile"
        if profile.exists() and profile.read_text(encoding="ascii").strip() != "cloudflare":
            raise RotationError("unexpected_deployed_identity_profile")
        docker_env = dict(os.environ)
        # Never allow ambient overrides to replace the exact private env.
        for key in list(docker_env):
            if key.startswith(("POSTGRES_", "SMARTPLOY_", "OBUMAI_", "JOBMARKET_", "KUNTAREKRY_")):
                docker_env.pop(key, None)
        docker_env["SMARTPLOY_IMAGE_TAG"] = recorded[:12]
        docker_env["CI"] = "false"
        compose = ["docker", "compose", "--env-file", str(env_file),
                   "--env-file", str(REPO / "deploy/personal/runtime.production.env"),
                   "-f", str(REPO / "deploy/personal/docker-compose.yml")]

        def docker(*params: str, data: str | None = None, check: bool = True,
                   timeout: int = 150) -> subprocess.CompletedProcess[str]:
            return call([*params], data=data, timeout=timeout, env=docker_env, check=check)

        def dc(*params: str, data: str | None = None, check: bool = True,
               timeout: int = 150) -> subprocess.CompletedProcess[str]:
            return docker(*compose, *params, data=data, check=check, timeout=timeout)

        def container_id(service: str) -> str:
            value = dc("ps", "-q", service).stdout.strip()
            if re.fullmatch(r"[0-9a-f]{12,64}", value) is None:
                raise RotationError("missing_or_ambiguous_container_" + service)
            return value

        # The database role, API and worker must belong ONLY to the
        # previously deployed release. Never silently substitute :dev.
        dc("config", "--quiet")
        postgres_id = container_id("postgres")
        api_id = container_id("api")
        worker_id = container_id("worker")
        container_env = json.loads(docker("docker", "inspect", "--format",
                                          "{{json .Config.Env}}", postgres_id).stdout)
        postgres_config = dict(item.split("=", 1) for item in container_env if "=" in item)
        if postgres_config.get("POSTGRES_PASSWORD") != old:
            raise RotationError("postgres_container_env_not_synced_with_private_file")
        expected_image = docker("docker", "image", "inspect", "--format", "{{.Id}}",
                                f"smartploy-api:{recorded[:12]}").stdout.strip()
        for cid in (api_id, worker_id):
            running_image = docker("docker", "inspect", "--format", "{{.Image}}", cid).stdout.strip()
            if not expected_image.startswith("sha256:") or running_image != expected_image:
                raise RotationError("unapproved_running_image_identity")

        # Require actual TCP password authentication plus local admin access
        # BEFORE touching data or application credentials.
        local_query = 'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"'
        if dc("exec", "-T", "postgres", "sh", "-ec", local_query).stdout.strip() != "1":
            raise RotationError("postgres_local_admin_auth_unavailable")

        def password_valid(pw: str) -> bool:
            cmd = ('IFS= read -r PGPASSWORD; export PGPASSWORD; '
                   'exec psql -h 127.0.0.1 -X -qAt -v ON_ERROR_STOP=1 '
                   '-U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"')
            result = dc("exec", "-T", "postgres", "sh", "-ec", cmd,
                        data=pw + "\n", check=False)
            return result.returncode == 0 and result.stdout.strip() == "1"

        if not password_valid(old):
            raise RotationError("existing_password_failed_tcp_auth")
        # Reject misconfigured PostgreSQL host trust: a password change
        # would not actually revoke the publicly exposed credential.
        if password_valid("deliberately-invalid-password-" + secrets.token_hex(16)):
            raise RotationError("postgres_tcp_auth_accepts_wrong_password")

        # Reuse the existing production backup + checksum + lock-aware
        # retention bypass. Do not overwrite any other services' volumes.
        backup_env = dict(docker_env)
        backup_env["SMARTPLOY_OPERATION_LOCK_HELD"] = "1"
        backup_env["SMARTPLOY_BACKUP_SKIP_RETENTION"] = "1"
        receipt = call(["bash", str(REPO / "deploy/personal/scripts/backup.sh")],
                       env=backup_env, timeout=240).stdout
        backups = [x.removeprefix("Backup created: ").strip() for x in receipt.splitlines()
                   if x.startswith("Backup created: ")]
        if len(backups) != 1 or not Path(backups[0]).is_file() or \
                not Path(backups[0] + ".sha256").is_file():
            raise RotationError("database_backup_receipt_missing")
        priv_dir = Path("/srv/obum/backups/smartploy/private-config")
        snapshot = make_snapshot(env_file, priv_dir)

        new = secrets.token_urlsafe(48)
        if new == old or not PASSWORD.fullmatch(new):
            raise RotationError("new_password_generation_failed")
        staged = replace_password(original, new)
        changed = False
        try:
            # Pre-encoded SCRAM verifier through stdin, never the plain
            # password in argv, shell history, a SQL log or stdout.
            sql = sql_change(username, new)
            changed = True   # Also attempt rollback if ALTER might have committed.
            dc("exec", "-T", "postgres", "sh", "-ec",
               'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -',
               data=sql)
            if not password_valid(new) or password_valid(old):
                raise RotationError("new_password_or_old_password_revocation_failed")
            atomic_private_write(env_file, staged)
            # Recreate the EXISTING postgres container to scrub its old
            # POSTGRES_PASSWORD env without reinitializing its PGDATA volume.
            # Keep the exact pinned API/worker image; do NOT run docker build.
            dc("up", "-d", "--wait", "--wait-timeout", "120",
               "--no-deps", "--force-recreate", "postgres", timeout=180)
            dc("up", "-d", "--wait", "--wait-timeout", "120",
               "--no-deps", "--force-recreate", "api", timeout=180)
            dc("up", "-d", "--wait", "--wait-timeout", "120",
               "--no-deps", "--force-recreate", "worker", timeout=180)
            # Verify the new role password *and* new container environment.
            new_id = container_id("postgres")
            new_config = json.loads(docker("docker", "inspect", "--format",
                                           "{{json .Config.Env}}", new_id).stdout)
            new_values = dict(i.split("=", 1) for i in new_config if "=" in i)
            if new_values.get("POSTGRES_PASSWORD") != new or not password_valid(new):
                raise RotationError("new_postgres_container_env_or_auth_failed")
            if password_valid(old):
                raise RotationError("exposed_password_still_valid")
            for service in ("api", "worker"):
                cid = container_id(service)
                if docker("docker", "inspect", "--format", "{{.Image}}", cid).stdout.strip() != expected_image:
                    raise RotationError("image_identity_changed_after_rotation")
                health = docker("docker", "inspect", "--format",
                                "{{.State.Health.Status}}", cid).stdout.strip()
                if health != "healthy":
                    raise RotationError("unhealthy_app_service_after_rotation")
            # Existing web must still serve the old-origin public gateway.
            # Keep live Cloudflare auth unchanged until a separately
            # approved OIDC release; a 502 from stale Caddy upstream
            # must make the rotation fail instead of claiming success.
            webport = values.get("SMARTPLOY_WEB_HOST_PORT") or "8091"
            if not PORT.fullmatch(webport) or int(webport) > 65535:
                raise RotationError("invalid_private_gateway_port")
            verified_web = False
            for _ in range(12):
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{webport}/healthz",
                        headers={"Host": "smartploy.obumai.com"},
                    )
                    with urllib.request.urlopen(request, timeout=4) as response:
                        health = json.loads(response.read(4096))
                        verified_web = (response.status == 200 and health.get("ok") is True
                                        and health.get("storage", {}).get("ready") is True)
                except (OSError, ValueError, KeyError, TypeError):
                    verified_web = False
                if verified_web:
                    break
                time.sleep(2)
            if not verified_web:
                raise RotationError("live_gateway_health_unavailable_after_rotation")
            print("rotation=PASS")
            print("database_backup=verified")
            print("old_password_revoked=true")
            print("private_config_updated=true")
            print("postgres_api_worker_recreated=true")
            print("live_gateway_health=verified")
            print("exact_running_release_sha=" + recorded)
            print("identity_mode=unchanged_cloudflare")
            print("autoapply_upgrade=not_yet_deployed")
            return 0
        except BaseException:
            # Recover from failures AFTER any possible ALTER ROLE; never
            # leave a new DB password paired with an old private env.
            if changed:
                try:
                    atomic_private_write(env_file, original)
                    dc("exec", "-T", "postgres", "sh", "-ec",
                       'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -',
                       data=sql_change(username, old))
                    dc("up", "-d", "--wait", "--wait-timeout", "120",
                       "--no-deps", "--force-recreate", "postgres", timeout=180)
                    dc("up", "-d", "--wait", "--wait-timeout", "120",
                       "--no-deps", "--force-recreate", "api", timeout=180)
                    dc("up", "-d", "--wait", "--wait-timeout", "120",
                       "--no-deps", "--force-recreate", "worker", timeout=180)
                    print("rotation=ROLLED_BACK")
                    print("prior_password_restored=true")
                    print("private_backup_present=true")
                except BaseException:
                    print("rotation=RECOVERY_REQUIRED")
                    print("private_backup_present=true")
                    print("do_not_run_deploy_or_change_database_manually=true")
            raise RotationError("rotation_not_verified; see status above") from None
    finally:
        os.close(lockfd)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (RotationError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        # No provider or Docker output, credential, role string, SQL or
        # subprocess command is ever printed on failure.
        if isinstance(exc, RotationError):
            print(f"rotation_error={exc}", file=sys.stderr)
        else:
            print("rotation_error=private_operation_failed", file=sys.stderr)
        raise SystemExit(2) from None

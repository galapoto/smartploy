"""Validation helpers for SmartPloy's post-deploy production acceptance gate."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import urlsplit
import sys


PRODUCTION_ORIGIN = "https://smartploy.obumai.com"
PRODUCTION_HOST = "smartploy.obumai.com"
ACCEPTED_DENIAL_STATUSES = frozenset({401, 403})
ACCEPTED_REDIRECT_STATUSES = frozenset({302, 303, 307, 308})


class LiveAcceptanceError(ValueError):
    pass


@dataclass(frozen=True)
class PublicProbe:
    status_code: int
    cf_ray: str = ""
    server: str = ""
    location: str = ""

    @property
    def cloudflare_edge(self) -> bool:
        return bool(self.cf_ray.strip()) or self.server.strip().casefold() == "cloudflare"


def validate_origin_health(payload: dict[str, object]) -> None:
    if payload.get("ok") is not True:
        raise LiveAcceptanceError("origin health is not ready")
    if payload.get("service") != "smartploy":
        raise LiveAcceptanceError("origin service identity is invalid")
    if payload.get("public_origin") != PRODUCTION_ORIGIN:
        raise LiveAcceptanceError("origin public URL does not match production")

    storage = payload.get("storage")
    if not isinstance(storage, dict) or storage.get("ready") is not True:
        raise LiveAcceptanceError("origin storage is not ready")

    access = payload.get("access")
    if not isinstance(access, dict):
        raise LiveAcceptanceError("origin Access health is missing")
    if access.get("enabled") is not True:
        raise LiveAcceptanceError("origin Access is not enabled")
    if access.get("environment") != "production":
        raise LiveAcceptanceError("origin Access environment is not production")
    if access.get("owner_restricted") is not True:
        raise LiveAcceptanceError("origin Access is not owner restricted")

    if payload.get("external_actions_authorized") is not False:
        raise LiveAcceptanceError("origin external-action authority is unsafe")


def is_cloudflare_access_redirect(location: str) -> bool:
    value = str(location or "").strip()
    if not value:
        return False
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.casefold()
    if not host.endswith(".cloudflareaccess.com"):
        return False
    return parsed.path.startswith("/cdn-cgi/access/")


def validate_public_probe(probe: PublicProbe) -> str:
    if not probe.cloudflare_edge:
        raise LiveAcceptanceError("public response lacks Cloudflare edge evidence")

    status = int(probe.status_code)
    if status >= 500:
        raise LiveAcceptanceError("public response returned a server error")
    if status == 200:
        raise LiveAcceptanceError("protected production surface is publicly accessible")
    if status in ACCEPTED_DENIAL_STATUSES:
        return "protected"
    if status in ACCEPTED_REDIRECT_STATUSES:
        if not is_cloudflare_access_redirect(probe.location):
            raise LiveAcceptanceError("public redirect does not target Cloudflare Access")
        return "protected"
    raise LiveAcceptanceError(f"unexpected protected-surface HTTP status: {status}")


def parse_probe_lines(text: str) -> PublicProbe:
    lines = text.splitlines()
    if len(lines) < 4:
        raise LiveAcceptanceError("public probe output is incomplete")
    try:
        status = int(lines[0].strip())
    except ValueError as exc:
        raise LiveAcceptanceError("public probe status is invalid") from exc
    return PublicProbe(
        status_code=status,
        cf_ray=lines[1].strip(),
        server=lines[2].strip(),
        location=lines[3].strip(),
    )


def _main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"origin-health", "public-probe"}:
        raise SystemExit(
            "usage: python -m smartploy.live_acceptance "
            "(origin-health <json-file> | public-probe <probe-file>)"
        )

    command, path = argv
    raw = Path(path).read_text(encoding="utf-8")
    if command == "origin-health":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit("origin health payload is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SystemExit("origin health payload must be an object")
        try:
            validate_origin_health(payload)
        except LiveAcceptanceError as exc:
            raise SystemExit(str(exc)) from exc
        print("pass")
        return 0

    try:
        result = validate_public_probe(parse_probe_lines(raw))
    except LiveAcceptanceError as exc:
        raise SystemExit(str(exc)) from exc
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

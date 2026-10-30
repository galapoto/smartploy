"""Validation helpers for SmartPloy's post-deploy production acceptance gate."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import sys


# Legacy Cloudflare-Access origin remains safe for rollback.
PRODUCTION_ORIGIN = "https://smartploy.obumai.com"
PRODUCTION_HOST = "smartploy.obumai.com"
# The new first-party OIDC policy has its own exact canonical origin.
OIDC_PRODUCTION_ORIGIN = "https://smartploy.komplyint.fi"
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


def validate_origin_health(payload: dict[str, object], identity_profile: str = "cloudflare") -> None:
    if payload.get("ok") is not True:
        raise LiveAcceptanceError("origin health is not ready")
    if payload.get("service") != "smartploy":
        raise LiveAcceptanceError("origin service identity is invalid")
    expected = OIDC_PRODUCTION_ORIGIN if identity_profile == "oidc" else PRODUCTION_ORIGIN
    if payload.get("public_origin") != expected:
        raise LiveAcceptanceError("origin public URL does not match production")

    storage = payload.get("storage")
    if not isinstance(storage, dict) or storage.get("ready") is not True:
        raise LiveAcceptanceError("origin storage is not ready")

    access = payload.get("access")
    if not isinstance(access, dict):
        raise LiveAcceptanceError("origin Access health is missing")
    if access.get("environment") != "production":
        raise LiveAcceptanceError("origin environment is not production")
    # Reuse the private operator-selected immutable policy, NOT a public
    # disclosure of OIDC issuer/mode/session internals via /healthz.
    if identity_profile == "oidc":
        if access.get("enabled") is not False:
            raise LiveAcceptanceError("first-party OIDC must disable Access assertions")
    elif identity_profile == "cloudflare":
        if access.get("enabled") is not True:
            raise LiveAcceptanceError("origin Access is not enabled")
        if access.get("owner_restricted") is not True:
            raise LiveAcceptanceError("origin Access is not owner restricted")
    else:
        raise LiveAcceptanceError("unsupported production identity mode")

    if payload.get("external_actions_authorized") is not False:
        raise LiveAcceptanceError("origin external-action authority is unsafe")


def validate_public_release_parity(
    origin: dict[str, object], public: dict[str, object], identity_profile: str = "oidc"
) -> str:
    """Prove that the public Komplyint HTTPS gateway serves the local release.

    Source-only comparison: a matched pair is not by itself approval of an
    exact Git commit. deploy.sh and release-evidence.sh independently check
    the local image, checkout and approved full SHA before certifying it.
    """
    if identity_profile != "oidc":
        raise LiveAcceptanceError("public revision parity is limited to the public OIDC host")
    validate_origin_health(origin, identity_profile)
    validate_origin_health(public, identity_profile)
    local_revision = origin.get("release_revision")
    public_revision = public.get("release_revision")
    for value in (local_revision, public_revision):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{12}", value) is None:
            raise LiveAcceptanceError("release fingerprint missing or invalid")
    if local_revision != public_revision:
        raise LiveAcceptanceError("public HTTPS entry point runs a different release revision")
    return local_revision



WEB_MANIFEST_SCHEMA = "smartploy-web-release-v1"


def validate_web_release_parity(
    origin_health: dict[str, object],
    origin_web: dict[str, object],
    expected_revision: str,
    identity_profile: str,
    public_web: dict[str, object] | None = None,
) -> str:
    """Require an exact reviewed SHA on API + served static web artifact.

    This is an additional *content* gate. It never approves a release by
    itself: the caller must independently attest checkout, image IDs, source
    security, publisher, TLS hostname and applicant acceptance.
    """
    validate_origin_health(origin_health, identity_profile)
    if not isinstance(expected_revision, str) or re.fullmatch(
        r"[0-9a-f]{12}", expected_revision
    ) is None:
        raise LiveAcceptanceError("invalid approved web release revision")
    if origin_health.get("release_revision") != expected_revision:
        raise LiveAcceptanceError("local API release fingerprint differs from the reviewed SHA")

    def validate_manifest(document: dict[str, object]) -> None:
        if not isinstance(document, dict) or set(document) != {
            "schema", "release_revision"
        }:
            raise LiveAcceptanceError("web manifest is missing or has an unknown schema")
        if document["schema"] != WEB_MANIFEST_SCHEMA:
            raise LiveAcceptanceError("web manifest format is invalid")
        if document["release_revision"] != expected_revision:
            raise LiveAcceptanceError("web static artifact differs from the API/reviewed SHA")

    validate_manifest(origin_web)
    if public_web is not None:
        if identity_profile != "oidc":
            raise LiveAcceptanceError("public web SHA parity requires first-party OIDC")
        validate_manifest(public_web)
    return expected_revision


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


def validate_oidc_public_probe(
    probe: PublicProbe, surface: str, oidc_issuer: str
) -> str:
    """Public SPA is allowed; exact private API must still be locked.

    The exact HTTPS public origin and TLS certificate are verified by the
    calling production shell. The registered Komplyint hostname reaches the
    OVH Caddy ingress directly, so Cloudflare edge headers are OPTIONAL for
    OIDC (but still mandatory for the legacy Access profile).

    Reject Cloudflare Access challenges through the exact root/401/login
    contracts; never accept arbitrary redirects or a public private API.
    """
    if surface == "root":
        if probe.status_code != 200:
            raise LiveAcceptanceError("OIDC public login shell is not reachable")
        return "public_login_shell"
    if surface == "api":
        if probe.status_code != 401:
            raise LiveAcceptanceError("OIDC private API is not returning signed-out 401")
        return "protected_by_app_session"
    if surface == "login":
        origin = urlsplit(oidc_issuer)
        destination = urlsplit(probe.location)
        if (
            probe.status_code not in ACCEPTED_REDIRECT_STATUSES
            or origin.scheme != "https"
            or not origin.netloc or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in {"", "/"}
            or destination.scheme != "https"
            or destination.netloc != origin.netloc or destination.hostname != origin.hostname
            or destination.username or destination.password
            or not destination.path.startswith("/")
        ):
            raise LiveAcceptanceError("OIDC login does not redirect to configured trusted issuer")
        return "redirect_to_trusted_oidc"
    raise LiveAcceptanceError("unknown OIDC public probe surface")


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


def read_release_json(path: str) -> dict[str, object]:
    file = Path(path)
    if not 0 < file.stat().st_size <= 4096 or file.is_symlink():
        raise LiveAcceptanceError("release verification payload must be small and regular")
    decoded = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise LiveAcceptanceError("release verification payload is not an object")
    return decoded


def _main(argv: list[str]) -> int:
    if len(argv) in {5, 6} and argv[0] == "web-release-parity":
        # python -m smartploy.live_acceptance web-release-parity
        #   <origin-health.json> <origin-web.json> <expected-12hex>
        #   <cloudflare|oidc> [public-web.json]
        try:
            local_health = read_release_json(argv[1])
            local_web = read_release_json(argv[2])
            public_web = read_release_json(argv[5]) if len(argv) == 6 else None
            result = validate_web_release_parity(
                local_health, local_web, argv[3], argv[4], public_web
            )
        except (OSError, UnicodeError, json.JSONDecodeError, LiveAcceptanceError) as exc:
            # Never echo an unexpected HTTPS response, applicant data or secret.
            raise SystemExit("web release parity: verification failed") from exc
        print(result)
        return 0

    if len(argv) == 4 and argv[0] == "public-release-parity":
        _, local_file, public_file, profile = argv
        try:
            payloads = []
            for path in (local_file, public_file):
                file = Path(path)
                if not 0 < file.stat().st_size <= 16384:
                    raise LiveAcceptanceError("health response size is invalid")
                decoded = json.loads(file.read_text(encoding="utf-8"))
                if not isinstance(decoded, dict):
                    raise LiveAcceptanceError("health response is not an object")
                payloads.append(decoded)
            revision = validate_public_release_parity(payloads[0], payloads[1], profile)
        except (OSError, UnicodeError, json.JSONDecodeError, LiveAcceptanceError) as exc:
            # Never print malformed provider/health JSON or private fields.
            raise SystemExit("public release parity: verification failed") from exc
        print(revision)
        return 0

    oidc_commands = {"oidc-root": "root", "oidc-api": "api", "oidc-login": "login"}
    if len(argv) == 3 and argv[0] in oidc_commands:
        command, path, issuer = argv
        try:
            status = validate_oidc_public_probe(
                parse_probe_lines(Path(path).read_text(encoding="utf-8")),
                oidc_commands[command], issuer,
            )
        except LiveAcceptanceError as exc:
            raise SystemExit(str(exc)) from exc
        print(status)
        return 0

    if not (
        (len(argv) in {2, 3} and argv[0] == "origin-health")
        or (len(argv) == 2 and argv[0] == "public-probe")
    ):
        raise SystemExit(
            "usage: python -m smartploy.live_acceptance "
            "(origin-health <json-file> | public-probe <probe-file> | "
            "oidc-root/oidc-api/oidc-login <probe-file> <issuer-origin> | "
            "public-release-parity <local-health-json> <public-health-json> oidc | "
            "web-release-parity <origin-health-json> <origin-web-json> "
            "<12-hex-revision> <cloudflare|oidc> [public-web-json])"
        )

    command, path = argv[:2]
    identity_profile = argv[2] if len(argv) == 3 else "cloudflare"
    raw = Path(path).read_text(encoding="utf-8")
    if command == "origin-health":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit("origin health payload is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SystemExit("origin health payload must be an object")
        try:
            validate_origin_health(payload, identity_profile)
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

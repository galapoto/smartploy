#!/usr/bin/env python3
"""Validate exact read-only ZITADEL OIDC discovery for a public PKCE client.

Invoked by the original OVH pre-deploy online preflight. Never consumes or
prints credentials. JSON enters via stdin, expected issuer via one argv.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit


def validate_metadata(payload: object, expected_issuer: str) -> None:
    origin = urlsplit(expected_issuer)
    if (
        origin.scheme != "https" or not origin.hostname or origin.path
        or origin.username or origin.password or origin.query or origin.fragment
    ):
        raise ValueError("invalid_expected_issuer")
    if not isinstance(payload, dict) or payload.get("issuer") != expected_issuer:
        raise ValueError("oidc_issuer_mismatch")
    required = {
        "grant_types_supported": "authorization_code",
        "response_types_supported": "code",
        "code_challenge_methods_supported": "S256",
        "token_endpoint_auth_methods_supported": "none",
    }
    for key, option in required.items():
        choices = payload.get(key)
        if not isinstance(choices, list) or option not in choices:
            raise ValueError("oidc_public_pkce_unsupported")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.startswith(expected_issuer + "/"):
            raise ValueError("oidc_endpoint_origin_mismatch")
        endpoint = urlsplit(value)
        if (
            endpoint.scheme != "https" or endpoint.netloc != origin.netloc
            or not endpoint.path or endpoint.username or endpoint.password
            or endpoint.query or endpoint.fragment
        ):
            raise ValueError("oidc_endpoint_origin_mismatch")


def main() -> int:
    if len(sys.argv) != 2:
        print("OIDC_METADATA_INVALID: expected issuer argument", file=sys.stderr)
        return 2
    raw = sys.stdin.buffer.read(65537)
    if not raw or len(raw) > 65536:
        print("OIDC_METADATA_INVALID: discovery size", file=sys.stderr)
        return 2
    try:
        validate_metadata(json.loads(raw), sys.argv[1])
    except (ValueError, TypeError, UnicodeDecodeError):
        print("OIDC_METADATA_INVALID: issuer, endpoints or PKCE support", file=sys.stderr)
        return 2
    print("OIDC_METADATA_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

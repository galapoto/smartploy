#!/usr/bin/env python3
"""Administrative SmartPloy identity migration/linking utility.

Identity claims are read from environment variables so provider subjects are not
placed on the process command line. The script never prints the raw subject,
email, database DSN, or credentials.
"""

from __future__ import annotations

import argparse
import json
import os

from smartploy.identity import AuthenticatedPrincipal, PostgresIdentityRepository


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=_required("SMARTPLOY_IDENTITY_ISSUER"),
        subject=_required("SMARTPLOY_IDENTITY_SUBJECT"),
        email=os.getenv("SMARTPLOY_IDENTITY_EMAIL", "").strip(),
        auth_source=os.getenv("SMARTPLOY_IDENTITY_AUTH_SOURCE", "oidc").strip(),
    ).normalized()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    link = sub.add_parser("link", help="link a trusted identity alias to an existing SmartPloy user")
    link.add_argument("--user-id", required=True)

    claim = sub.add_parser(
        "claim-legacy",
        help="claim a legacy profile for the current trusted identity",
    )
    claim.add_argument("--profile-id", default="default")

    args = parser.parse_args()
    repository = PostgresIdentityRepository(_required("SMARTPLOY_DATABASE_URL"))
    repository.migrate()
    principal = _principal()

    if args.command == "link":
        binding = repository.link_identity(args.user_id, principal)
        action = "identity_linked"
    else:
        binding = repository.claim_legacy_profile(
            principal,
            legacy_profile_id=args.profile_id,
        )
        action = "legacy_profile_claimed"

    print(
        json.dumps(
            {
                "status": "ok",
                "action": action,
                "user_id": binding.user_id,
                "profile_id": binding.profile_id,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

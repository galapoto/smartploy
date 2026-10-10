"""Provider-neutral authenticated identity and SmartPloy profile binding."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Protocol
import re

from psycopg import connect
from psycopg.types.json import Jsonb

from .storage import apply_migrations


IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,2047}$", re.IGNORECASE)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    issuer: str
    subject: str
    email: str = ""
    auth_source: str = ""
    claims: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "AuthenticatedPrincipal":
        issuer = str(self.issuer or "").strip().rstrip("/")
        subject = str(self.subject or "").strip()
        email = str(self.email or "").strip().casefold()
        auth_source = str(self.auth_source or "").strip().casefold()

        if not issuer.startswith("https://") or len(issuer) > 2048:
            raise ValueError("identity issuer must be a bounded HTTPS issuer")
        if not subject or len(subject) > 2048 or any(ord(ch) < 32 for ch in subject):
            raise ValueError("identity subject is invalid")
        if email and ("@" not in email or len(email) > 320):
            raise ValueError("identity email is invalid")
        if len(auth_source) > 64:
            raise ValueError("identity auth_source is invalid")

        return AuthenticatedPrincipal(
            issuer=issuer,
            subject=subject,
            email=email,
            auth_source=auth_source,
            claims=dict(self.claims or {}),
        )


def stable_user_id(issuer: str, subject: str) -> str:
    principal = AuthenticatedPrincipal(issuer=issuer, subject=subject).normalized()
    digest = sha256(
        (principal.issuer + "\x00" + principal.subject).encode("utf-8")
    ).hexdigest()[:32]
    return f"usr-{digest}"


def stable_profile_id(user_id: str) -> str:
    value = str(user_id or "").strip()
    if not value.startswith("usr-"):
        raise ValueError("user_id is invalid")
    digest = sha256(("smartploy-profile\x00" + value).encode("utf-8")).hexdigest()[:32]
    return f"profile-{digest}"


@dataclass(frozen=True)
class UserProfileBinding:
    user_id: str
    profile_id: str
    issuer: str
    subject: str
    email: str
    status: str = "active"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "profile_id": self.profile_id,
            "email": self.email,
            "status": self.status,
        }


class IdentityRepository(Protocol):
    def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UserProfileBinding: ...
    def get(self, user_id: str) -> UserProfileBinding | None: ...
    def claim_legacy_profile(
        self,
        principal: AuthenticatedPrincipal,
        *,
        legacy_profile_id: str = "default",
    ) -> UserProfileBinding: ...


class MemoryIdentityRepository:
    def __init__(self) -> None:
        self._by_user: dict[str, UserProfileBinding] = {}
        self._legacy_claims: dict[str, str] = {}

    def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UserProfileBinding:
        item = principal.normalized()
        user_id = stable_user_id(item.issuer, item.subject)
        existing = self._by_user.get(user_id)
        if existing is not None:
            updated = UserProfileBinding(
                user_id=existing.user_id,
                profile_id=existing.profile_id,
                issuer=existing.issuer,
                subject=existing.subject,
                email=item.email or existing.email,
                status=existing.status,
            )
            self._by_user[user_id] = updated
            return updated

        binding = UserProfileBinding(
            user_id=user_id,
            profile_id=stable_profile_id(user_id),
            issuer=item.issuer,
            subject=item.subject,
            email=item.email,
        )
        self._by_user[user_id] = binding
        return binding

    def get(self, user_id: str) -> UserProfileBinding | None:
        return self._by_user.get(str(user_id or "").strip())

    def claim_legacy_profile(
        self,
        principal: AuthenticatedPrincipal,
        *,
        legacy_profile_id: str = "default",
    ) -> UserProfileBinding:
        item = principal.normalized()
        legacy = str(legacy_profile_id or "").strip()
        if not legacy:
            raise ValueError("legacy_profile_id is required")
        user_id = stable_user_id(item.issuer, item.subject)
        owner = self._legacy_claims.get(legacy)
        if owner and owner != user_id:
            raise ValueError("legacy profile is already claimed by another user")
        binding = UserProfileBinding(
            user_id=user_id,
            profile_id=legacy,
            issuer=item.issuer,
            subject=item.subject,
            email=item.email,
        )
        self._legacy_claims[legacy] = user_id
        self._by_user[user_id] = binding
        return binding


class PostgresIdentityRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    def migrate(self) -> None:
        apply_migrations(self.dsn)

    @staticmethod
    def _binding(row: tuple[Any, ...]) -> UserProfileBinding:
        return UserProfileBinding(
            user_id=str(row[0]),
            profile_id=str(row[1]),
            issuer=str(row[2]),
            subject=str(row[3]),
            email=str(row[4] or ""),
            status=str(row[5]),
        )

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT u.user_id, p.profile_id, u.issuer, u.subject, u.email, u.status
            FROM smartploy_users AS u
            JOIN smartploy_user_profiles AS p ON p.user_id = u.user_id
        """

    def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UserProfileBinding:
        item = principal.normalized()
        user_id = stable_user_id(item.issuer, item.subject)
        profile_id = stable_profile_id(user_id)

        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_users (
                        user_id, issuer, subject, email, status,
                        created_at, updated_at, last_seen_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, 'active', now(), now(), now(), %s)
                    ON CONFLICT (issuer, subject) DO UPDATE SET
                        email = CASE
                            WHEN EXCLUDED.email <> '' THEN EXCLUDED.email
                            ELSE smartploy_users.email
                        END,
                        updated_at = now(),
                        last_seen_at = now()
                    RETURNING user_id
                    """,
                    (
                        user_id,
                        item.issuer,
                        item.subject,
                        item.email,
                        Jsonb({"auth_source": item.auth_source}),
                    ),
                )
                actual_user_id = str(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO smartploy_user_profiles (user_id, profile_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (actual_user_id, stable_profile_id(actual_user_id)),
                )
                cur.execute(
                    self._select_sql() + " WHERE u.user_id = %s",
                    (actual_user_id,),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("identity/profile reconciliation failed")
        return self._binding(row)

    def get(self, user_id: str) -> UserProfileBinding | None:
        value = str(user_id or "").strip()
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(self._select_sql() + " WHERE u.user_id = %s", (value,))
                row = cur.fetchone()
        return self._binding(row) if row else None

    def claim_legacy_profile(
        self,
        principal: AuthenticatedPrincipal,
        *,
        legacy_profile_id: str = "default",
    ) -> UserProfileBinding:
        item = principal.normalized()
        legacy = str(legacy_profile_id or "").strip()
        if not legacy:
            raise ValueError("legacy_profile_id is required")

        user_id = stable_user_id(item.issuer, item.subject)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_users (
                        user_id, issuer, subject, email, status,
                        created_at, updated_at, last_seen_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, 'active', now(), now(), now(), %s)
                    ON CONFLICT (issuer, subject) DO UPDATE SET
                        email = CASE
                            WHEN EXCLUDED.email <> '' THEN EXCLUDED.email
                            ELSE smartploy_users.email
                        END,
                        updated_at = now(),
                        last_seen_at = now()
                    RETURNING user_id
                    """,
                    (
                        user_id,
                        item.issuer,
                        item.subject,
                        item.email,
                        Jsonb({"auth_source": item.auth_source, "legacy_claim": True}),
                    ),
                )
                actual_user_id = str(cur.fetchone()[0])

                cur.execute(
                    "SELECT user_id FROM smartploy_user_profiles WHERE profile_id = %s FOR UPDATE",
                    (legacy,),
                )
                owner = cur.fetchone()
                if owner is not None and str(owner[0]) != actual_user_id:
                    raise ValueError("legacy profile is already claimed by another user")

                cur.execute(
                    "SELECT profile_id FROM smartploy_user_profiles WHERE user_id = %s FOR UPDATE",
                    (actual_user_id,),
                )
                current = cur.fetchone()
                if current is not None and str(current[0]) != legacy:
                    cur.execute(
                        """
                        DELETE FROM smartploy_user_profiles
                        WHERE user_id = %s
                          AND profile_id = %s
                        """,
                        (actual_user_id, str(current[0])),
                    )

                cur.execute(
                    """
                    INSERT INTO smartploy_user_profiles (user_id, profile_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        profile_id = EXCLUDED.profile_id,
                        updated_at = now()
                    """,
                    (actual_user_id, legacy),
                )
                cur.execute(
                    self._select_sql() + " WHERE u.user_id = %s",
                    (actual_user_id,),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("legacy profile claim reconciliation failed")
        return self._binding(row)


__all__ = [
    "AuthenticatedPrincipal",
    "IdentityRepository",
    "MemoryIdentityRepository",
    "PostgresIdentityRepository",
    "UserProfileBinding",
    "stable_profile_id",
    "stable_user_id",
]

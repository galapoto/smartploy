"""Provider-neutral authenticated identity and SmartPloy profile binding."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .storage import apply_migrations


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    issuer: str
    subject: str
    email: str = ""
    auth_source: str = ""
    claims: dict[str, Any] = field(default_factory=dict)

    @property
    def subject_fingerprint(self) -> str:
        return sha256(self.subject.encode("utf-8")).hexdigest()[:16]

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
    def link_identity(
        self,
        user_id: str,
        principal: AuthenticatedPrincipal,
    ) -> UserProfileBinding: ...
    def claim_legacy_profile(
        self,
        principal: AuthenticatedPrincipal,
        *,
        legacy_profile_id: str = "default",
    ) -> UserProfileBinding: ...


class MemoryIdentityRepository:
    def __init__(self) -> None:
        self._bindings: dict[str, UserProfileBinding] = {}
        self._identity_to_user: dict[tuple[str, str], str] = {}
        self._legacy_claims: dict[str, str] = {}

    def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UserProfileBinding:
        item = principal.normalized()
        key = (item.issuer, item.subject)
        user_id = self._identity_to_user.get(key)
        if user_id is None:
            user_id = stable_user_id(item.issuer, item.subject)
            self._identity_to_user[key] = user_id

        existing = self._bindings.get(user_id)
        if existing is None:
            existing = UserProfileBinding(
                user_id=user_id,
                profile_id=stable_profile_id(user_id),
                email=item.email,
            )
        elif item.email:
            existing = UserProfileBinding(
                user_id=existing.user_id,
                profile_id=existing.profile_id,
                email=item.email,
                status=existing.status,
            )
        self._bindings[user_id] = existing
        return existing

    def get(self, user_id: str) -> UserProfileBinding | None:
        return self._bindings.get(str(user_id or "").strip())

    def link_identity(
        self,
        user_id: str,
        principal: AuthenticatedPrincipal,
    ) -> UserProfileBinding:
        value = str(user_id or "").strip()
        existing = self._bindings.get(value)
        if existing is None:
            raise KeyError(value)

        item = principal.normalized()
        key = (item.issuer, item.subject)
        mapped = self._identity_to_user.get(key)
        if mapped is not None and mapped != value:
            raise ValueError("identity is already linked to another SmartPloy user")
        self._identity_to_user[key] = value

        if item.email:
            existing = UserProfileBinding(
                user_id=existing.user_id,
                profile_id=existing.profile_id,
                email=item.email,
                status=existing.status,
            )
            self._bindings[value] = existing
        return existing

    def claim_legacy_profile(
        self,
        principal: AuthenticatedPrincipal,
        *,
        legacy_profile_id: str = "default",
    ) -> UserProfileBinding:
        legacy = str(legacy_profile_id or "").strip()
        if not legacy:
            raise ValueError("legacy_profile_id is required")

        binding = self.resolve_or_create(principal)
        owner = self._legacy_claims.get(legacy)
        if owner and owner != binding.user_id:
            raise ValueError("legacy profile is already claimed by another user")

        claimed = UserProfileBinding(
            user_id=binding.user_id,
            profile_id=legacy,
            email=binding.email,
            status=binding.status,
        )
        self._legacy_claims[legacy] = binding.user_id
        self._bindings[binding.user_id] = claimed
        return claimed


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
            email=str(row[2] or ""),
            status=str(row[3]),
        )

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT u.user_id, p.profile_id, u.email, u.status
            FROM smartploy_users AS u
            JOIN smartploy_user_profiles AS p ON p.user_id = u.user_id
        """

    def _binding_for_user(self, cur, user_id: str) -> UserProfileBinding:
        cur.execute(self._select_sql() + " WHERE u.user_id = %s", (user_id,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("identity/profile reconciliation failed")
        return self._binding(row)

    def resolve_or_create(self, principal: AuthenticatedPrincipal) -> UserProfileBinding:
        item = principal.normalized()
        proposed_user_id = stable_user_id(item.issuer, item.subject)

        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_users (
                        user_id, email, status, created_at, updated_at, last_seen_at, metadata
                    )
                    VALUES (%s, %s, 'active', now(), now(), now(), %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (
                        proposed_user_id,
                        item.email,
                        Jsonb({"created_from_auth_source": item.auth_source}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO smartploy_user_identities (
                        issuer, subject, user_id, auth_source, created_at, last_seen_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, now(), now(), %s)
                    ON CONFLICT (issuer, subject) DO UPDATE SET
                        last_seen_at = now(),
                        auth_source = CASE
                            WHEN EXCLUDED.auth_source <> '' THEN EXCLUDED.auth_source
                            ELSE smartploy_user_identities.auth_source
                        END
                    RETURNING user_id
                    """,
                    (
                        item.issuer,
                        item.subject,
                        proposed_user_id,
                        item.auth_source,
                        Jsonb({}),
                    ),
                )
                actual_user_id = str(cur.fetchone()[0])

                cur.execute(
                    """
                    UPDATE smartploy_users
                    SET email = CASE WHEN %s <> '' THEN %s ELSE email END,
                        updated_at = now(),
                        last_seen_at = now()
                    WHERE user_id = %s
                    """,
                    (item.email, item.email, actual_user_id),
                )
                cur.execute(
                    """
                    INSERT INTO smartploy_user_profiles (user_id, profile_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (actual_user_id, stable_profile_id(actual_user_id)),
                )
                binding = self._binding_for_user(cur, actual_user_id)
            conn.commit()
        return binding

    def get(self, user_id: str) -> UserProfileBinding | None:
        value = str(user_id or "").strip()
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(self._select_sql() + " WHERE u.user_id = %s", (value,))
                row = cur.fetchone()
        return self._binding(row) if row else None

    def link_identity(
        self,
        user_id: str,
        principal: AuthenticatedPrincipal,
    ) -> UserProfileBinding:
        value = str(user_id or "").strip()
        item = principal.normalized()
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM smartploy_users WHERE user_id = %s FOR UPDATE",
                    (value,),
                )
                if cur.fetchone() is None:
                    raise KeyError(value)

                cur.execute(
                    """
                    INSERT INTO smartploy_user_identities (
                        issuer, subject, user_id, auth_source, created_at, last_seen_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, now(), now(), %s)
                    ON CONFLICT (issuer, subject) DO NOTHING
                    """,
                    (
                        item.issuer,
                        item.subject,
                        value,
                        item.auth_source,
                        Jsonb({"explicit_link": True}),
                    ),
                )
                cur.execute(
                    """
                    SELECT user_id
                    FROM smartploy_user_identities
                    WHERE issuer = %s AND subject = %s
                    FOR UPDATE
                    """,
                    (item.issuer, item.subject),
                )
                mapped = str(cur.fetchone()[0])
                if mapped != value:
                    raise ValueError("identity is already linked to another SmartPloy user")

                cur.execute(
                    """
                    UPDATE smartploy_user_identities
                    SET last_seen_at = now(),
                        auth_source = CASE WHEN %s <> '' THEN %s ELSE auth_source END
                    WHERE issuer = %s AND subject = %s
                    """,
                    (item.auth_source, item.auth_source, item.issuer, item.subject),
                )
                if item.email:
                    cur.execute(
                        """
                        UPDATE smartploy_users
                        SET email = %s, updated_at = now(), last_seen_at = now()
                        WHERE user_id = %s
                        """,
                        (item.email, value),
                    )
                binding = self._binding_for_user(cur, value)
            conn.commit()
        return binding

    def claim_legacy_profile(
        self,
        principal: AuthenticatedPrincipal,
        *,
        legacy_profile_id: str = "default",
    ) -> UserProfileBinding:
        legacy = str(legacy_profile_id or "").strip()
        if not legacy:
            raise ValueError("legacy_profile_id is required")

        binding = self.resolve_or_create(principal)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id
                    FROM smartploy_user_profiles
                    WHERE profile_id = %s
                    FOR UPDATE
                    """,
                    (legacy,),
                )
                owner = cur.fetchone()
                if owner is not None and str(owner[0]) != binding.user_id:
                    raise ValueError("legacy profile is already claimed by another user")

                if binding.profile_id != legacy:
                    cur.execute(
                        "SELECT count(*) FROM smartploy_profile_facts WHERE profile_id = %s",
                        (binding.profile_id,),
                    )
                    fact_count = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        SELECT count(*)
                        FROM smartploy_application_preparations
                        WHERE profile_id = %s
                        """,
                        (binding.profile_id,),
                    )
                    preparation_count = int(cur.fetchone()[0])
                    cur.execute(
                        "SELECT count(*) FROM smartploy_applications WHERE profile_id = %s",
                        (binding.profile_id,),
                    )
                    application_count = int(cur.fetchone()[0])
                    if fact_count or preparation_count or application_count:
                        raise ValueError(
                            "current profile already contains data and cannot be replaced by legacy claim"
                        )

                cur.execute(
                    """
                    INSERT INTO smartploy_user_profiles (user_id, profile_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        profile_id = EXCLUDED.profile_id,
                        updated_at = now()
                    """,
                    (binding.user_id, legacy),
                )
                claimed = self._binding_for_user(cur, binding.user_id)
            conn.commit()
        return claimed


__all__ = [
    "AuthenticatedPrincipal",
    "IdentityRepository",
    "MemoryIdentityRepository",
    "PostgresIdentityRepository",
    "UserProfileBinding",
    "stable_profile_id",
    "stable_user_id",
]

"""Obum Identity OIDC login and opaque SmartPloy application sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import secrets
from typing import Any
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from psycopg import connect
from psycopg.types.json import Jsonb
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .access import (
    ACCESS_ASSERTION_HEADER,
    AccessPrincipal,
    AccessSettings,
    AccessVerificationError,
    CloudflareAccessVerifier,
)
from .identity import AuthenticatedPrincipal, IdentityRepository


SESSION_COOKIE_NAME = "__Host-smartploy_session"
PUBLIC_AUTH_PATHS = frozenset(
    {
        "/auth/login",
        "/auth/callback",
        "/auth/logout",
        "/auth/logged-out",
    }
)
HEALTH_PATHS = frozenset({"/healthz", "/healthz/"})
VALID_AUTH_MODES = frozenset({"disabled", "cloudflare", "hybrid", "oidc"})


class AuthenticationConfigurationError(ValueError):
    pass


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise AuthenticationConfigurationError(f"{name} must be a boolean")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise AuthenticationConfigurationError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise AuthenticationConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _https_origin(value: str, name: str) -> str:
    text = str(value or "").strip().rstrip("/")
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise AuthenticationConfigurationError(f"{name} must be an origin-only HTTPS URL")
    return text


@dataclass(frozen=True)
class AuthenticationSettings:
    environment: str
    mode: str

    @classmethod
    def from_env(cls) -> "AuthenticationSettings":
        environment = os.getenv("SMARTPLOY_ENVIRONMENT", "development").strip().casefold()
        if environment not in {"development", "test", "production"}:
            raise AuthenticationConfigurationError(
                "SMARTPLOY_ENVIRONMENT must be development, test or production"
            )

        configured = os.getenv("SMARTPLOY_AUTH_MODE", "").strip().casefold()
        if configured:
            mode = configured
        elif environment == "production":
            mode = "cloudflare"
        else:
            mode = "disabled"

        if mode not in VALID_AUTH_MODES:
            raise AuthenticationConfigurationError(
                "SMARTPLOY_AUTH_MODE must be disabled, cloudflare, hybrid or oidc"
            )
        if environment == "production" and mode == "disabled":
            raise AuthenticationConfigurationError(
                "production authentication cannot be disabled"
            )
        return cls(environment=environment, mode=mode)

    @property
    def oidc_enabled(self) -> bool:
        return self.mode in {"hybrid", "oidc"}

    @property
    def cloudflare_enabled(self) -> bool:
        return self.mode in {"cloudflare", "hybrid"}


@dataclass(frozen=True)
class OIDCSettings:
    issuer: str
    client_id: str
    public_origin: str
    redirect_uri: str
    post_logout_redirect_uri: str
    scope: str
    session_ttl_seconds: int
    state_ttl_seconds: int

    @property
    def metadata_url(self) -> str:
        return self.issuer + "/.well-known/openid-configuration"

    @classmethod
    def from_env(
        cls,
        authentication: AuthenticationSettings,
    ) -> "OIDCSettings | None":
        if not authentication.oidc_enabled:
            return None

        issuer = _https_origin(
            os.getenv("SMARTPLOY_OIDC_ISSUER", ""),
            "SMARTPLOY_OIDC_ISSUER",
        )
        public_origin = _https_origin(
            os.getenv("SMARTPLOY_PUBLIC_ORIGIN", ""),
            "SMARTPLOY_PUBLIC_ORIGIN",
        )
        client_id = os.getenv("SMARTPLOY_OIDC_CLIENT_ID", "").strip()
        if not client_id or len(client_id) > 2048:
            raise AuthenticationConfigurationError(
                "SMARTPLOY_OIDC_CLIENT_ID is required when OIDC is enabled"
            )

        redirect_uri = os.getenv(
            "SMARTPLOY_OIDC_REDIRECT_URI",
            public_origin + "/auth/callback",
        ).strip()
        post_logout = os.getenv(
            "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI",
            public_origin + "/auth/logged-out",
        ).strip()
        if redirect_uri != public_origin + "/auth/callback":
            raise AuthenticationConfigurationError(
                "SMARTPLOY_OIDC_REDIRECT_URI must equal the SmartPloy public callback"
            )
        if post_logout != public_origin + "/auth/logged-out":
            raise AuthenticationConfigurationError(
                "SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI must equal the SmartPloy logout callback"
            )

        scope = " ".join(
            part
            for part in os.getenv(
                "SMARTPLOY_OIDC_SCOPE",
                "openid profile email",
            ).split()
            if part
        )
        if "openid" not in scope.split():
            raise AuthenticationConfigurationError(
                "SMARTPLOY_OIDC_SCOPE must include openid"
            )

        return cls(
            issuer=issuer,
            client_id=client_id,
            public_origin=public_origin,
            redirect_uri=redirect_uri,
            post_logout_redirect_uri=post_logout,
            scope=scope,
            session_ttl_seconds=_bounded_int(
                "SMARTPLOY_SESSION_TTL_SECONDS",
                43200,
                300,
                604800,
            ),
            state_ttl_seconds=_bounded_int(
                "SMARTPLOY_OIDC_STATE_TTL_SECONDS",
                600,
                60,
                1800,
            ),
        )


@dataclass(frozen=True)
class ApplicationSession:
    session_hash: str
    user_id: str
    issuer: str
    subject: str
    email: str
    auth_source: str
    provider_session_id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def principal(self) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            issuer=self.issuer,
            subject=self.subject,
            email=self.email,
            auth_source=self.auth_source,
        ).normalized()


@dataclass(frozen=True)
class SessionIssue:
    token: str
    record: ApplicationSession


def _session_hash(token: str) -> str:
    return sha256(str(token or "").encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemorySessionRepository:
    def __init__(self) -> None:
        self._items: dict[str, ApplicationSession] = {}

    def create(
        self,
        *,
        user_id: str,
        principal: AuthenticatedPrincipal,
        provider_session_id: str = "",
        ttl_seconds: int,
    ) -> SessionIssue:
        item = principal.normalized()
        token = secrets.token_urlsafe(32)
        now = _utc_now()
        record = ApplicationSession(
            session_hash=_session_hash(token),
            user_id=user_id,
            issuer=item.issuer,
            subject=item.subject,
            email=item.email,
            auth_source=item.auth_source or "oidc",
            provider_session_id=str(provider_session_id or "").strip(),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self._items[record.session_hash] = record
        return SessionIssue(token=token, record=record)

    def get(self, token: str) -> ApplicationSession | None:
        key = _session_hash(token)
        item = self._items.get(key)
        if item is None or item.revoked_at is not None or item.expires_at <= _utc_now():
            return None
        return item

    def revoke(self, token: str) -> None:
        key = _session_hash(token)
        item = self._items.get(key)
        if item is None:
            return
        self._items[key] = ApplicationSession(
            **{
                **item.__dict__,
                "revoked_at": _utc_now(),
            }
        )

    def revoke_user(self, user_id: str) -> int:
        count = 0
        for key, item in list(self._items.items()):
            if item.user_id == user_id and item.revoked_at is None:
                self._items[key] = ApplicationSession(
                    **{
                        **item.__dict__,
                        "revoked_at": _utc_now(),
                    }
                )
                count += 1
        return count

    def revoke_provider_session(self, issuer: str, provider_session_id: str) -> int:
        count = 0
        for key, item in list(self._items.items()):
            if (
                item.issuer == issuer
                and item.provider_session_id == provider_session_id
                and item.revoked_at is None
            ):
                self._items[key] = ApplicationSession(
                    **{
                        **item.__dict__,
                        "revoked_at": _utc_now(),
                    }
                )
                count += 1
        return count


class PostgresSessionRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> ApplicationSession:
        return ApplicationSession(
            session_hash=str(row[0]),
            user_id=str(row[1]),
            issuer=str(row[2]),
            subject=str(row[3]),
            email=str(row[4] or ""),
            auth_source=str(row[5] or "oidc"),
            provider_session_id=str(row[6] or ""),
            created_at=row[7],
            last_seen_at=row[8],
            expires_at=row[9],
            revoked_at=row[10],
        )

    def create(
        self,
        *,
        user_id: str,
        principal: AuthenticatedPrincipal,
        provider_session_id: str = "",
        ttl_seconds: int,
    ) -> SessionIssue:
        item = principal.normalized()
        token = secrets.token_urlsafe(32)
        key = _session_hash(token)
        now = _utc_now()
        expires = now + timedelta(seconds=ttl_seconds)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_sessions (
                        session_hash, user_id, issuer, subject, email, auth_source,
                        provider_session_id, created_at, last_seen_at, expires_at,
                        revoked_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                    RETURNING session_hash, user_id, issuer, subject, email, auth_source,
                              provider_session_id, created_at, last_seen_at, expires_at,
                              revoked_at
                    """,
                    (
                        key,
                        user_id,
                        item.issuer,
                        item.subject,
                        item.email,
                        item.auth_source or "oidc",
                        str(provider_session_id or "").strip(),
                        now,
                        now,
                        expires,
                        Jsonb({}),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return SessionIssue(token=token, record=self._from_row(row))

    def get(self, token: str) -> ApplicationSession | None:
        key = _session_hash(token)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_hash, user_id, issuer, subject, email, auth_source,
                           provider_session_id, created_at, last_seen_at, expires_at,
                           revoked_at
                    FROM smartploy_sessions
                    WHERE session_hash = %s
                      AND revoked_at IS NULL
                      AND expires_at > now()
                    """,
                    (key,),
                )
                row = cur.fetchone()
                if row is not None:
                    cur.execute(
                        """
                        UPDATE smartploy_sessions
                        SET last_seen_at = now()
                        WHERE session_hash = %s
                        """,
                        (key,),
                    )
            conn.commit()
        return self._from_row(row) if row else None

    def revoke(self, token: str) -> None:
        key = _session_hash(token)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_sessions
                    SET revoked_at = COALESCE(revoked_at, now())
                    WHERE session_hash = %s
                    """,
                    (key,),
                )
            conn.commit()

    def revoke_user(self, user_id: str) -> int:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_sessions
                    SET revoked_at = COALESCE(revoked_at, now())
                    WHERE user_id = %s AND revoked_at IS NULL
                    """,
                    (user_id,),
                )
                count = cur.rowcount
            conn.commit()
        return int(count or 0)

    def revoke_provider_session(self, issuer: str, provider_session_id: str) -> int:
        if not provider_session_id:
            return 0
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_sessions
                    SET revoked_at = COALESCE(revoked_at, now())
                    WHERE issuer = %s
                      AND provider_session_id = %s
                      AND revoked_at IS NULL
                    """,
                    (issuer, provider_session_id),
                )
                count = cur.rowcount
            conn.commit()
        return int(count or 0)


class MemoryOIDCStateCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[str, datetime]] = {}

    async def set(self, key: str, value: str, expires: int) -> None:
        self._items[_session_hash(key)] = (
            value,
            _utc_now() + timedelta(seconds=int(expires)),
        )

    async def get(self, key: str) -> str | None:
        item = self._items.get(_session_hash(key))
        if item is None:
            return None
        value, expires = item
        if expires <= _utc_now():
            self._items.pop(_session_hash(key), None)
            return None
        return value

    async def delete(self, key: str) -> None:
        self._items.pop(_session_hash(key), None)


class PostgresOIDCStateCache:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    async def set(self, key: str, value: str, expires: int) -> None:
        await asyncio.to_thread(self._set_sync, key, value, expires)

    def _set_sync(self, key: str, value: str, expires: int) -> None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_oidc_state (
                        cache_key_hash, payload, expires_at, created_at
                    )
                    VALUES (%s, %s, now() + (%s * interval '1 second'), now())
                    ON CONFLICT (cache_key_hash) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        expires_at = EXCLUDED.expires_at,
                        created_at = now()
                    """,
                    (_session_hash(key), value, int(expires)),
                )
            conn.commit()

    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_sync, key)

    def _get_sync(self, key: str) -> str | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT payload
                    FROM smartploy_oidc_state
                    WHERE cache_key_hash = %s
                      AND expires_at > now()
                    """,
                    (_session_hash(key),),
                )
                row = cur.fetchone()
        return str(row[0]) if row else None

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    def _delete_sync(self, key: str) -> None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM smartploy_oidc_state WHERE cache_key_hash = %s",
                    (_session_hash(key),),
                )
            conn.commit()


def build_oidc_registry(settings: OIDCSettings, cache: Any) -> OAuth:
    oauth = OAuth(cache=cache)
    oauth.register(
        "obum_identity",
        client_id=settings.client_id,
        server_metadata_url=settings.metadata_url,
        code_challenge_method="S256",
        client_kwargs={
            "scope": settings.scope,
            "token_endpoint_auth_method": "none",
        },
    )
    return oauth


class SmartployAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        *,
        authentication: AuthenticationSettings,
        sessions: MemorySessionRepository | PostgresSessionRepository,
        access_settings: AccessSettings,
        identity_repository: IdentityRepository,
        access_verifier: CloudflareAccessVerifier | None = None,
    ) -> None:
        super().__init__(app)
        self.authentication = authentication
        self.sessions = sessions
        self.access_settings = access_settings
        self.identity_repository = identity_repository
        self.access_verifier = access_verifier
        if (
            authentication.cloudflare_enabled
            and access_settings.enabled
            and self.access_verifier is None
        ):
            self.access_verifier = CloudflareAccessVerifier(access_settings)

    async def _authorize_principal(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        principal: AuthenticatedPrincipal,
        *,
        session_user_id: str = "",
    ) -> Response:
        # Account status is checked against the authoritative backend on EVERY
        # protected request. A previously valid cookie or Cloudflare assertion
        # must not outlive an account's disabled status.
        try:
            binding = await asyncio.to_thread(
                self.identity_repository.resolve_or_create, principal
            )
        except Exception:
            # Database outages are not a reason to reuse an old cached status.
            return self._deny(
                503, "identity_unavailable",
                "SmartPloy account verification is temporarily unavailable.",
            )
        if binding.status != "active":
            return self._deny(
                403, "account_disabled", "SmartPloy account access is disabled.",
            )
        if session_user_id and binding.user_id != session_user_id:
            # Identity linking after session issuance must require a new login:
            # otherwise the old cookie could unexpectedly switch tenant.
            return self._deny(
                401, "session_identity_changed",
                "The account linked to this session changed. Sign in again.",
                login_url="/auth/login",
            )

        request.state.smartploy_principal = principal
        request.state.smartploy_binding = binding
        return await call_next(request)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if (
            path in HEALTH_PATHS
            or self.authentication.mode == "disabled"
            or (self.authentication.oidc_enabled and path in PUBLIC_AUTH_PATHS)
        ):
            # Logout must remain reachable even for a disabled user so that
            # their browser can clear its old application session.
            return await call_next(request)

        if self.authentication.oidc_enabled:
            raw_session = request.cookies.get(SESSION_COOKIE_NAME, "")
            if raw_session:
                record = await asyncio.to_thread(self.sessions.get, raw_session)
                if record is not None:
                    return await self._authorize_principal(
                        request, call_next, record.principal(),
                        session_user_id=record.user_id,
                    )

        if self.authentication.cloudflare_enabled and self.access_settings.enabled:
            assertion = request.headers.get(ACCESS_ASSERTION_HEADER, "")
            if assertion:
                if self.access_verifier is None:
                    return self._deny(
                        503,
                        "access_verifier_unavailable",
                        "Cloudflare Access verification is unavailable.",
                    )
                try:
                    verified = self.access_verifier.verify(assertion)
                except AccessVerificationError as exc:
                    status = 403 if exc.code == "identity_denied" else 401
                    return self._deny(status, exc.code, str(exc))
                if not isinstance(verified, AccessPrincipal):
                    return self._deny(
                        503, "identity_unavailable",
                        "SmartPloy account verification is temporarily unavailable.",
                    )
                return await self._authorize_principal(
                    request, call_next,
                    AuthenticatedPrincipal(
                        issuer=verified.issuer,
                        subject=verified.subject,
                        email=verified.email,
                        auth_source="cloudflare_access",
                    ).normalized(),
                )

        if self.authentication.mode == "cloudflare":
            return self._deny(
                401,
                "access_token_missing",
                "A verified Cloudflare Access assertion is required.",
            )
        return self._deny(
            401,
            "authentication_required",
            "Authentication is required.",
            login_url="/auth/login" if self.authentication.oidc_enabled else "",
        )

    @staticmethod
    def _deny(
        status_code: int,
        code: str,
        message: str,
        *,
        login_url: str = "",
    ) -> JSONResponse:
        payload: dict[str, Any] = {"error": {"code": code, "message": message}}
        if login_url:
            payload["login_url"] = login_url
        response = JSONResponse(status_code=status_code, content=payload)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response


def set_session_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ttl_seconds,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


__all__ = [
    "ApplicationSession",
    "AuthenticationConfigurationError",
    "AuthenticationSettings",
    "MemoryOIDCStateCache",
    "MemorySessionRepository",
    "OIDCSettings",
    "PostgresOIDCStateCache",
    "PostgresSessionRepository",
    "PUBLIC_AUTH_PATHS",
    "SESSION_COOKIE_NAME",
    "SessionIssue",
    "SmartployAuthenticationMiddleware",
    "build_oidc_registry",
    "clear_session_cookie",
    "set_session_cookie",
]

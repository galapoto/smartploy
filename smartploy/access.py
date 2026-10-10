"""Cloudflare Access verification for SmartPloy's protected production API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping
import os

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


ACCESS_ASSERTION_HEADER = "Cf-Access-Jwt-Assertion"
FIXED_ACCESS_ALGORITHM = "RS256"
MAX_ACCESS_TOKEN_BYTES = 32_768
REQUIRED_ACCESS_CLAIMS = ("exp", "iat", "iss", "aud", "sub", "email", "type")
HEALTH_PATHS = frozenset({"/healthz", "/healthz/"})


class AccessConfigurationError(ValueError):
    pass


class AccessVerificationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise AccessConfigurationError(f"{name} must be a boolean")


@dataclass(frozen=True)
class AccessSettings:
    environment: str
    enabled: bool
    issuer: str
    audience: str
    allowed_email: str
    leeway_seconds: int = 30
    jwks_cache_seconds: int = 300
    network_timeout_seconds: int = 5

    @classmethod
    def from_env(cls) -> "AccessSettings":
        environment = os.getenv("SMARTPLOY_ENVIRONMENT", "development").strip().casefold()
        if environment not in {"development", "test", "production"}:
            raise AccessConfigurationError(
                "SMARTPLOY_ENVIRONMENT must be development, test or production"
            )

        enabled = _bool_env("SMARTPLOY_ACCESS_ENABLED", False)
        issuer = os.getenv("SMARTPLOY_ACCESS_ISSUER", "").strip().rstrip("/")
        audience = os.getenv("SMARTPLOY_ACCESS_AUDIENCE", "").strip()
        allowed_email = os.getenv("SMARTPLOY_ACCESS_ALLOWED_EMAIL", "").strip().casefold()

        if environment == "production" and not enabled:
            raise AccessConfigurationError(
                "SMARTPLOY_ACCESS_ENABLED must be true in production"
            )

        if enabled:
            if not issuer.startswith("https://"):
                raise AccessConfigurationError(
                    "SMARTPLOY_ACCESS_ISSUER must be an HTTPS URL"
                )
            if "?" in issuer or "#" in issuer:
                raise AccessConfigurationError(
                    "SMARTPLOY_ACCESS_ISSUER must not contain query or fragment"
                )
            if not audience or len(audience) > 2048:
                raise AccessConfigurationError(
                    "SMARTPLOY_ACCESS_AUDIENCE is required when Access is enabled"
                )
            if (
                not allowed_email
                or "@" not in allowed_email
                or len(allowed_email) > 320
                or "," in allowed_email
            ):
                raise AccessConfigurationError(
                    "SMARTPLOY_ACCESS_ALLOWED_EMAIL must contain exactly one approved email"
                )

        return cls(
            environment=environment,
            enabled=enabled,
            issuer=issuer,
            audience=audience,
            allowed_email=allowed_email,
        )


@dataclass(frozen=True)
class AccessPrincipal:
    email: str
    subject: str
    issuer: str
    audience: str
    issued_at: datetime
    expires_at: datetime
    key_id: str

    @property
    def subject_fingerprint(self) -> str:
        return sha256(self.subject.encode("utf-8")).hexdigest()[:16]

    def public_dict(self) -> dict[str, Any]:
        return {
            "authenticated": True,
            "email": self.email,
            "subject_fingerprint": self.subject_fingerprint,
            "auth_source": "cloudflare_access",
        }


SigningKeyResolver = Callable[[str], Any]


class CloudflareAccessVerifier:
    """Verify Access application JWTs using fixed SmartPloy-owned policy."""

    def __init__(
        self,
        settings: AccessSettings,
        *,
        signing_key_resolver: SigningKeyResolver | None = None,
    ) -> None:
        if not settings.enabled:
            raise AccessConfigurationError("Access verification is disabled")
        self.settings = settings
        self.jwks_url = f"{settings.issuer}/cdn-cgi/access/certs"
        self._jwk_client: PyJWKClient | None = None

        if signing_key_resolver is None:
            self._jwk_client = PyJWKClient(
                self.jwks_url,
                cache_keys=True,
                cache_jwk_set=True,
                lifespan=settings.jwks_cache_seconds,
                timeout=settings.network_timeout_seconds,
            )
            self._signing_key_resolver = self._resolve_cloudflare_key
        else:
            self._signing_key_resolver = signing_key_resolver

    def _resolve_cloudflare_key(self, token: str) -> Any:
        if self._jwk_client is None:  # pragma: no cover
            raise AccessVerificationError(
                "jwks_client_unavailable",
                "Cloudflare public-key resolution is unavailable.",
            )
        return self._jwk_client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> AccessPrincipal:
        normalized = str(token or "").strip()
        if not normalized:
            raise AccessVerificationError(
                "access_token_missing",
                "A verified Cloudflare Access assertion is required.",
            )
        if len(normalized.encode("utf-8")) > MAX_ACCESS_TOKEN_BYTES:
            raise AccessVerificationError(
                "access_token_too_large",
                "The Cloudflare Access assertion exceeds the configured limit.",
            )

        try:
            header = jwt.get_unverified_header(normalized)
        except InvalidTokenError as exc:
            raise AccessVerificationError(
                "access_token_malformed",
                "The Cloudflare Access assertion is malformed.",
            ) from exc

        algorithm = str(header.get("alg") or "")
        key_id = str(header.get("kid") or "").strip()
        if algorithm != FIXED_ACCESS_ALGORITHM:
            raise AccessVerificationError(
                "access_algorithm_denied",
                "The Cloudflare Access assertion uses an unsupported algorithm.",
            )
        if not key_id or len(key_id) > 512:
            raise AccessVerificationError(
                "access_key_id_invalid",
                "The Cloudflare Access assertion has no valid key identifier.",
            )

        try:
            signing_key = self._signing_key_resolver(normalized)
            payload = jwt.decode(
                normalized,
                key=signing_key,
                algorithms=[FIXED_ACCESS_ALGORITHM],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                leeway=self.settings.leeway_seconds,
                options={
                    "require": list(REQUIRED_ACCESS_CLAIMS),
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except AccessVerificationError:
            raise
        except (InvalidTokenError, PyJWKClientError, OSError, TimeoutError) as exc:
            raise AccessVerificationError(
                "access_token_invalid",
                "The Cloudflare Access assertion could not be verified.",
            ) from exc
        except Exception as exc:
            raise AccessVerificationError(
                "access_verification_unavailable",
                "Cloudflare Access verification is unavailable.",
            ) from exc

        token_type = str(payload.get("type") or "").strip().casefold()
        if token_type != "app":
            raise AccessVerificationError(
                "access_token_type_denied",
                "The assertion is not a Cloudflare Access application token.",
            )

        email = str(payload.get("email") or "").strip().casefold()
        subject = str(payload.get("sub") or "").strip()
        if not email or "@" not in email or len(email) > 320:
            raise AccessVerificationError(
                "access_email_invalid",
                "The Access token does not contain a valid email claim.",
            )
        if email != self.settings.allowed_email:
            raise AccessVerificationError(
                "identity_denied",
                "The authenticated identity is not the approved SmartPloy owner.",
            )
        if not subject or len(subject) > 1024:
            raise AccessVerificationError(
                "access_subject_invalid",
                "The Access token does not contain a valid subject claim.",
            )

        return AccessPrincipal(
            email=email,
            subject=subject,
            issuer=str(payload["iss"]),
            audience=_audience_text(payload["aud"]),
            issued_at=_timestamp_claim(payload, "iat"),
            expires_at=_timestamp_claim(payload, "exp"),
            key_id=key_id,
        )


def _audience_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _timestamp_claim(payload: Mapping[str, Any], name: str) -> datetime:
    raw = payload.get(name)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise AccessVerificationError(
            f"access_{name}_invalid",
            f"The Access token {name} claim is invalid.",
        )
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise AccessVerificationError(
            f"access_{name}_invalid",
            f"The Access token {name} claim is invalid.",
        ) from exc


class CloudflareAccessMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        settings: AccessSettings,
        verifier: CloudflareAccessVerifier | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.verifier = verifier
        if settings.enabled and verifier is None:
            self.verifier = CloudflareAccessVerifier(settings)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path in HEALTH_PATHS or not self.settings.enabled:
            return await call_next(request)

        if self.verifier is None:  # pragma: no cover
            return self._deny(
                503,
                "access_verifier_unavailable",
                "Cloudflare Access verification is unavailable.",
            )

        try:
            principal = self.verifier.verify(
                request.headers.get(ACCESS_ASSERTION_HEADER, "")
            )
        except AccessVerificationError as exc:
            status_code = 403 if exc.code == "identity_denied" else 401
            return self._deny(status_code, exc.code, str(exc))

        request.state.smartploy_principal = principal
        return await call_next(request)

    @staticmethod
    def _deny(status_code: int, code: str, message: str) -> JSONResponse:
        response = JSONResponse(
            status_code=status_code,
            content={"error": {"code": code, "message": message}},
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response


__all__ = [
    "ACCESS_ASSERTION_HEADER",
    "AccessConfigurationError",
    "AccessPrincipal",
    "AccessSettings",
    "AccessVerificationError",
    "CloudflareAccessMiddleware",
    "CloudflareAccessVerifier",
    "FIXED_ACCESS_ALGORITHM",
    "HEALTH_PATHS",
    "MAX_ACCESS_TOKEN_BYTES",
    "REQUIRED_ACCESS_CLAIMS",
]

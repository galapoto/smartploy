"""Smartploy FastAPI service."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from authlib.integrations.base_client import OAuthError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from .access import AccessPrincipal, AccessSettings, CloudflareAccessVerifier
from .application_storage import MemoryApplicationRepository, PostgresApplicationRepository
from .application_workspace import WorkspaceError, WorkspaceRevisionConflict, new_workspace, render_document
from .application_workspace_storage import MemoryWorkspaceRepository, PostgresWorkspaceRepository
from .browser_handoff import HandoffError, make_browser_packet, review_handoff
from .browser_receipt import ReceiptError, validate_browser_receipt
from .browser_receipt_storage import (
    ReceiptConflict, MemoryBrowserReceiptRepository, PostgresBrowserReceiptRepository,
)
from .local_drafting import LocalDraftClient, LocalDraftError, LocalDraftSettings
from .cv_import import CVImportError, parse_cv
from .cv_storage import MemoryCVRepository, PostgresCVRepository
from .profile import FACT_TYPES, ProfileFact
from .identity import (
    AuthenticatedPrincipal,
    IdentityRepository,
    MemoryIdentityRepository,
    PostgresIdentityRepository,
    UserProfileBinding,
)
from .domain import JobSearchFilters, SourceObservation, SourcePolicy
from .obumai import ObumAIClient, ObumAIError, ObumAISettings
from .operator_access import OperatorAccessPolicy
from .oidc import (
    AuthenticationSettings,
    MemoryOIDCStateCache,
    MemorySessionRepository,
    OIDCSettings,
    PostgresOIDCStateCache,
    PostgresSessionRepository,
    SESSION_COOKIE_NAME,
    SmartployAuthenticationMiddleware,
    build_oidc_registry,
    clear_session_cookie,
    set_session_cookie,
)
from .private_saved_jobs import (
    MemoryPrivateSavedJobRepository,
    PostgresPrivateSavedJobRepository,
    PrivateSavedJobError,
)
from .preparation_storage import MemoryPreparationRepository, PostgresPreparationRepository
from .preparations import PreparationNotEligible
from .profile_storage import MemoryProfileRepository, PostgresProfileRepository
from .search_preferences import SearchPreferenceConflict, SearchPreferenceError, search_jobs
from .search_preference_storage import MemorySearchPreferenceRepository, PostgresSearchPreferenceRepository
from .service import SmartployService
from .storage import MemoryJobRepository, PostgresJobRepository
from .worker_schedule import PostgresWorkerTaskRepository


class SourcePolicyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    display_name: str
    source_class: str
    allowed_modes: List[str]
    terms_review_status: str = "approved"
    active: bool = True
    notes: str = ""


class SourceObservationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_mode: str
    source_url: str = ""
    raw_text: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    observed_at: Optional[str] = None
    posted_at: str = ""
    source_external_id: str = ""


class FiltersPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sectors: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    work_modes: List[str] = Field(default_factory=list)
    seniority: List[str] = Field(default_factory=list)
    minimum_salary_eur: Optional[int] = None
    excluded_employers: List[str] = Field(default_factory=list)
    excluded_terms: List[str] = Field(default_factory=list)
    include_unknown: bool = True


class IngestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation: SourceObservationPayload
    filters: Optional[FiltersPayload] = None


def _allowed_hosts() -> tuple[str, ...]:
    raw = os.getenv("SMARTPLOY_ALLOWED_HOSTS", "").strip()
    if not raw:
        return ()
    hosts = tuple(item.strip().casefold() for item in raw.split(",") if item.strip())
    if not hosts:
        return ()
    for host in hosts:
        if "*" in host or "/" in host or "://" in host:
            raise ValueError("SMARTPLOY_ALLOWED_HOSTS must contain exact host names only")
    return hosts


def _public_origin() -> str:
    value = os.getenv("SMARTPLOY_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("SMARTPLOY_PUBLIC_ORIGIN must be an origin-only HTTPS URL")
    return value


class CVUploadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(min_length=24, max_length=7_000_000)


class PrivateSavedJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(min_length=1, max_length=160)
    role_title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=12000)
    location: str = Field(default="", max_length=160)
    application_url: str = Field(default="", max_length=2048)


class ProfileFactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=700)
    approved: bool = False


class FactApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool


class SearchPreferencesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    roles: list[str] = Field(default_factory=list, max_length=12)
    locations: list[str] = Field(default_factory=list, max_length=12)
    languages: list[str] = Field(default_factory=list, max_length=3)
    work_modes: list[str] = Field(default_factory=list, max_length=3)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    skills: list[str] = Field(default_factory=list, max_length=16)
    seniority: str = "any"
    expected_revision: int = Field(ge=0)


class WorkspaceEditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    cv_text: str = Field(min_length=1, max_length=30000)
    cover_letter_text: str = Field(min_length=1, max_length=10000)


class LocalAISuggestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    acknowledge_local_ai_processing: bool


class BrowserHandoffPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirm_private_data_transfer: bool


class BrowserReceiptImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_user_observed: bool
    receipt: dict[str, Any]


class WorkspaceAppliedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_external_application: bool
    expected_revision: int = Field(ge=1)
    reference: str = Field(default="", max_length=250)


class ObumAITaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=64)
    instructions: str = Field(default="", max_length=20_000)


def _sanitize_worker_metadata(value: Any) -> Any:
    blocked_terms = (
        "password",
        "secret",
        "credential",
        "authorization",
        "subscription_key",
        "api_key",
        "access_token",
        "http_headers",
    )
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            folded = str(key).casefold()
            if any(term in folded for term in blocked_terms):
                continue
            result[str(key)] = _sanitize_worker_metadata(item)
        return result
    if isinstance(value, list):
        return [_sanitize_worker_metadata(item) for item in value]
    return value


def _worker_snapshot() -> dict[str, Any]:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if not dsn:
        return {
            "configured": False,
            "ready": False,
            "count": 0,
            "tasks": [],
            "error": "",
        }

    try:
        tasks = PostgresWorkerTaskRepository(dsn).list()
    except Exception as exc:
        return {
            "configured": True,
            "ready": False,
            "count": 0,
            "tasks": [],
            "error": type(exc).__name__,
        }

    now = datetime.now(timezone.utc)
    projected = []
    for task in tasks:
        lease_active = bool(task.lease_until and task.lease_until > now)
        projected.append(
            {
                "task_id": task.task_id,
                "task_kind": task.task_kind,
                "enabled": task.enabled,
                "cadence_seconds": task.cadence_seconds,
                "next_run_at": task.next_run_at.isoformat(),
                "last_started_at": task.last_started_at.isoformat() if task.last_started_at else "",
                "last_completed_at": (
                    task.last_completed_at.isoformat() if task.last_completed_at else ""
                ),
                "last_status": task.last_status,
                "consecutive_failures": task.consecutive_failures,
                "last_error": task.last_error,
                "lease_active": lease_active,
                "lease_until": task.lease_until.isoformat() if task.lease_until else "",
                "metadata": _sanitize_worker_metadata(dict(task.metadata or {})),
            }
        )
    return {
        "configured": True,
        "ready": True,
        "count": len(projected),
        "tasks": projected,
        "error": "",
    }


def _principal_from_request(request: Request) -> AuthenticatedPrincipal | None:
    principal = getattr(request.state, "smartploy_principal", None)
    if isinstance(principal, AuthenticatedPrincipal):
        return principal.normalized()
    if isinstance(principal, AccessPrincipal):
        return AuthenticatedPrincipal(
            issuer=principal.issuer,
            subject=principal.subject,
            email=principal.email,
            auth_source="cloudflare_access",
        ).normalized()
    return None


def _build_identity_repository() -> IdentityRepository:
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    if dsn:
        return PostgresIdentityRepository(dsn)
    return MemoryIdentityRepository()


def _build_service() -> SmartployService:
    obum_settings = ObumAISettings.from_env()
    client = ObumAIClient(obum_settings) if obum_settings else None

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    profile_id = os.getenv("SMARTPLOY_PROFILE_ID", "default").strip() or "default"
    if dsn:
        repository = PostgresJobRepository(dsn)
        profile_repository = PostgresProfileRepository(dsn, profile_id=profile_id)
        preparation_repository = PostgresPreparationRepository(dsn)
        application_repository = PostgresApplicationRepository(dsn)
    else:
        repository = MemoryJobRepository()
        profile_repository = MemoryProfileRepository(profile_id=profile_id)
        preparation_repository = MemoryPreparationRepository()
        application_repository = MemoryApplicationRepository()

    service = SmartployService(
        repository=repository,
        profile_repository=profile_repository,
        preparation_repository=preparation_repository,
        application_repository=application_repository,
        obumai=client,
    )
    service.register_source(
        SourcePolicy(
            source_id="manual-import",
            display_name="Manual import",
            source_class="manual",
            allowed_modes=("manual",),
            terms_review_status="approved",
        )
    )
    return service


def create_app(
    service: SmartployService | None = None,
    *,
    access_verifier: CloudflareAccessVerifier | None = None,
    identity_repository: IdentityRepository | None = None,
    oidc_client: Any | None = None,
    session_repository: Any | None = None,
    oidc_state_cache: Any | None = None,
) -> FastAPI:
    active = service or _build_service()
    authentication = AuthenticationSettings.from_env()
    access_settings = AccessSettings.from_env(
        require_enabled_in_production=authentication.cloudflare_enabled
    )
    oidc_settings = OIDCSettings.from_env(authentication)
    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()

    sessions = session_repository
    if sessions is None:
        sessions = PostgresSessionRepository(dsn) if dsn else MemorySessionRepository()

    state_cache = oidc_state_cache
    if state_cache is None:
        state_cache = PostgresOIDCStateCache(dsn) if dsn else MemoryOIDCStateCache()

    oidc_registry = None
    oidc_remote = oidc_client
    if oidc_settings is not None and oidc_remote is None:
        oidc_registry = build_oidc_registry(oidc_settings, state_cache)
        oidc_remote = oidc_registry.create_client("obum_identity")

    resolved_identities = identity_repository or _build_identity_repository()
    app = FastAPI(title="Smartploy API", version="0.5.0")
    allowed_hosts = _allowed_hosts()
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.add_middleware(
        SmartployAuthenticationMiddleware,
        authentication=authentication,
        sessions=sessions,
        access_settings=access_settings,
        identity_repository=resolved_identities,
        access_verifier=access_verifier,
    )
    app.state.smartploy = active
    app.state.public_origin = _public_origin()
    app.state.authentication = authentication
    app.state.access_settings = access_settings
    app.state.oidc_settings = oidc_settings
    app.state.oidc_registry = oidc_registry
    app.state.oidc_client = oidc_remote
    app.state.session_repository = sessions
    app.state.identity_repository = resolved_identities
    # Unconfigured authenticated operators cannot mutate global job inventory.
    app.state.operator_access = OperatorAccessPolicy.from_env()
    app.state.tenant_services = {}
    app.state.cv_repository = PostgresCVRepository(dsn) if dsn else MemoryCVRepository()
    app.state.workspace_repository = PostgresWorkspaceRepository(dsn) if dsn else MemoryWorkspaceRepository()
    app.state.browser_receipts = PostgresBrowserReceiptRepository(dsn) if dsn else MemoryBrowserReceiptRepository()
    app.state.local_ai = LocalDraftClient(LocalDraftSettings.from_env())
    app.state.search_preferences = (
        PostgresSearchPreferenceRepository(dsn) if dsn else MemorySearchPreferenceRepository()
    )
    app.state.private_saved_jobs = (
        PostgresPrivateSavedJobRepository(dsn) if dsn
        else MemoryPrivateSavedJobRepository()
    )

    def tenant_context(request: Request) -> tuple[SmartployService, UserProfileBinding | None]:
        principal = _principal_from_request(request)
        if principal is None:
            return active, None

        binding = getattr(request.state, "smartploy_binding", None)
        if not isinstance(binding, UserProfileBinding):
            # Auth-disabled fixtures have no verified principal; otherwise
            # request middleware must have validated and bound this account.
            if authentication.mode != "disabled":
                raise HTTPException(status_code=503, detail="Verified account binding is unavailable")
            binding = app.state.identity_repository.resolve_or_create(principal)
        if binding.status != "active":
            raise HTTPException(status_code=403, detail="SmartPloy account access is disabled")
        request.state.smartploy_binding = binding

        cached = app.state.tenant_services.get(binding.profile_id)
        if cached is not None:
            return cached, binding

        dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
        if dsn:
            tenant = SmartployService(
                repository=active.repository,
                profile_repository=PostgresProfileRepository(dsn, profile_id=binding.profile_id),
                preparation_repository=PostgresPreparationRepository(
                    dsn, profile_id=binding.profile_id
                ),
                application_repository=PostgresApplicationRepository(
                    dsn, profile_id=binding.profile_id
                ),
                obumai=active.obumai,
            )
        else:
            tenant = SmartployService(
                repository=active.repository,
                profile_repository=MemoryProfileRepository(profile_id=binding.profile_id),
                preparation_repository=MemoryPreparationRepository(profile_id=binding.profile_id),
                application_repository=MemoryApplicationRepository(profile_id=binding.profile_id),
                obumai=active.obumai,
            )
        app.state.tenant_services[binding.profile_id] = tenant
        return tenant, binding

    @app.get("/healthz")
    def health() -> JSONResponse:
        """Public liveness/provenance contract; never return account metadata.

        The existing guarded release script consumes storage readiness,
        Access posture, worker readiness/count and external-action status.
        Keep those machine-readable *safe* fields, but not default profile
        counts/types, tenant IDs, raw worker errors or authentication config.
        More detailed worker and profile views require authenticated APIs.
        """
        storage = active.storage_status()
        worker = _worker_snapshot()
        safe = {
            "ok": bool(storage.get("ready")),
            "service": "smartploy",
            "public_origin": app.state.public_origin,
            "storage": {
                "mode": str(storage.get("mode") or "unknown"),
                "ready": bool(storage.get("ready")),
            },
            "obumai_configured": active.obumai is not None,
            "access": {
                "enabled": access_settings.enabled,
                "environment": access_settings.environment,
                "owner_restricted": bool(access_settings.allowed_email),
            },
            "worker": {
                "configured": bool(worker.get("configured")),
                "ready": bool(worker.get("ready")),
                "count": int(worker.get("count") or 0),
            },
            "external_actions_authorized": False,
        }
        return JSONResponse(
            content=safe,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/auth/login")
    async def auth_login(request: Request):
        if oidc_settings is None or oidc_remote is None:
            raise HTTPException(status_code=404, detail="OIDC login is not enabled")
        request.scope.setdefault("session", {})
        return await oidc_remote.authorize_redirect(
            request,
            oidc_settings.redirect_uri,
        )

    @app.api_route("/auth/callback", methods=["GET", "POST"])
    async def auth_callback(request: Request):
        if oidc_settings is None or oidc_remote is None:
            raise HTTPException(status_code=404, detail="OIDC login is not enabled")
        request.scope.setdefault("session", {})
        try:
            token = await oidc_remote.authorize_access_token(request)
        except OAuthError as exc:
            raise HTTPException(status_code=401, detail="OIDC callback validation failed") from exc

        userinfo = token.get("userinfo") if isinstance(token, dict) else None
        if not userinfo:
            raise HTTPException(status_code=401, detail="OIDC user identity is missing")
        claims = dict(userinfo)
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise HTTPException(status_code=401, detail="OIDC subject is missing")

        principal = AuthenticatedPrincipal(
            issuer=oidc_settings.issuer,
            subject=subject,
            email=str(claims.get("email") or "").strip(),
            auth_source="oidc",
            claims={},
        ).normalized()
        binding = await asyncio.to_thread(
            app.state.identity_repository.resolve_or_create, principal
        )
        if binding.status != "active":
            raise HTTPException(
                status_code=403, detail="SmartPloy account access is disabled",
                headers={"Cache-Control": "no-store"},
            )
        issued = await asyncio.to_thread(
            sessions.create,
            user_id=binding.user_id,
            principal=principal,
            provider_session_id=str(claims.get("sid") or "").strip(),
            ttl_seconds=oidc_settings.session_ttl_seconds,
        )

        response = RedirectResponse(url="/", status_code=303)
        set_session_cookie(response, issued.token, oidc_settings.session_ttl_seconds)
        return response

    @app.api_route("/auth/logout", methods=["GET", "POST"])
    async def auth_logout(request: Request):
        raw_session = request.cookies.get(SESSION_COOKIE_NAME, "")
        if raw_session:
            await __import__("asyncio").to_thread(sessions.revoke, raw_session)

        if oidc_settings is not None and oidc_remote is not None:
            request.scope.setdefault("session", {})
            try:
                response = await oidc_remote.logout_redirect(
                    request,
                    post_logout_redirect_uri=oidc_settings.post_logout_redirect_uri,
                    client_id=oidc_settings.client_id,
                )
            except Exception:
                response = RedirectResponse(url="/auth/logged-out", status_code=303)
        else:
            response = RedirectResponse(url="/", status_code=303)
        clear_session_cookie(response)
        return response

    @app.get("/auth/logged-out")
    async def auth_logged_out():
        response = RedirectResponse(url="/", status_code=303)
        clear_session_cookie(response)
        return response

    @app.get("/api/v1/session")
    def session(request: Request) -> dict[str, Any]:
        principal = _principal_from_request(request)
        if principal is None:
            return {
                "authenticated": False,
                "email": "",
                "user_id": "",
                "profile_id": "",
                "subject_fingerprint": "",
                "auth_source": "none",
            }
        _, binding = tenant_context(request)
        if binding is None:
            raise HTTPException(status_code=500, detail="identity binding unavailable")
        return {
            "authenticated": True,
            **binding.to_public_dict(),
            "subject_fingerprint": principal.subject_fingerprint,
            "auth_source": principal.auth_source or "external_identity",
        }

    @app.get("/api/v1/profile/status")
    def profile_status(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        return tenant.profile_summary()

    @app.get("/api/v1/profile/facts")
    def profile_facts(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        facts = tenant.profile_repository.list_facts()
        return {"facts": [item.to_dict() for item in facts], "count": len(facts)}

    @app.post("/api/v1/profile/facts", status_code=201)
    def add_profile_fact(payload: ProfileFactPayload, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        if payload.fact_type not in FACT_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported profile fact type")
        try:
            fact = ProfileFact(
                fact_type=payload.fact_type,
                value=payload.value,
                source="user-confirmed" if payload.approved else "user-entered",
                approved=payload.approved,
            ).normalized()
            saved = tenant.profile_repository.upsert_fact(fact)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"fact": saved.to_dict()}

    @app.patch("/api/v1/profile/facts/{fact_id}")
    def approve_profile_fact(fact_id: str, payload: FactApprovalPayload, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        fact = next(
            (item for item in tenant.profile_repository.list_facts() if item.fact_id == fact_id),
            None,
        )
        if fact is None:
            raise HTTPException(status_code=404, detail="Profile fact not found")
        saved = tenant.profile_repository.upsert_fact(replace(fact, approved=payload.approved))
        return {"fact": saved.to_dict()}

    @app.delete("/api/v1/profile/facts/{fact_id}")
    def delete_profile_fact(fact_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        if not tenant.profile_repository.delete_fact(fact_id):
            raise HTTPException(status_code=404, detail="Profile fact not found")
        return {"deleted": True}

    @app.get("/api/v1/profile/cv")
    def get_cv(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        item = app.state.cv_repository.get(tenant.profile_repository.profile_id)
        return item.summary() if item else {"present": False}

    @app.post("/api/v1/profile/cv")
    def upload_cv(payload: CVUploadPayload, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        try:
            filename, media_type, raw, text = parse_cv(
                payload.filename, payload.content_base64
            )
        except CVImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        item = app.state.cv_repository.put(
            tenant.profile_repository.profile_id, filename, media_type, raw, text
        )
        # CV text is a private preview only. It is never auto-approved or sent to ObumAI.
        return item.summary()

    @app.get("/api/v1/profile/cv/download")
    def download_cv(request: Request) -> Response:
        tenant, _ = tenant_context(request)
        item = app.state.cv_repository.get(tenant.profile_repository.profile_id)
        if item is None:
            raise HTTPException(status_code=404, detail="No CV uploaded")
        ext = ".pdf" if item.media_type == "application/pdf" else ".docx"
        return Response(
            content=item.content,
            media_type=item.media_type,
            headers={
                "Content-Disposition": 'attachment; filename="smartploy-cv' + ext + '"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    @app.delete("/api/v1/profile/cv")
    def delete_cv(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        if not app.state.cv_repository.delete(tenant.profile_repository.profile_id):
            raise HTTPException(status_code=404, detail="No CV uploaded")
        return {"deleted": True}

    def require_shared_ingestion_operator(request: Request) -> None:
        # Only local, auth-disabled development/test fixtures can use legacy
        # unscoped HTTP ingestion. Production rejects disabled authentication.
        if authentication.mode == "disabled":
            return
        _, binding = tenant_context(request)
        if not app.state.operator_access.allows(binding):
            raise HTTPException(
                status_code=403,
                detail="Operator authorization required for shared job sources",
                headers={"Cache-Control": "no-store"},
            )

    @app.post("/api/v1/sources")
    def register_source(payload: SourcePolicyPayload, request: Request) -> dict[str, Any]:
        require_shared_ingestion_operator(request)
        try:
            policy = active.register_source(
                SourcePolicy(
                    source_id=payload.source_id,
                    display_name=payload.display_name,
                    source_class=payload.source_class,
                    allowed_modes=tuple(payload.allowed_modes),
                    terms_review_status=payload.terms_review_status,
                    active=payload.active,
                    notes=payload.notes,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"source": policy.__dict__}

    @app.get("/api/v1/sources/health")
    def list_source_health() -> dict[str, Any]:
        items = [item.to_dict() for item in active.list_source_health()]
        return {"sources": items, "count": len(items)}

    @app.get("/api/v1/sources/{source_id}/health")
    def get_source_health(source_id: str) -> dict[str, Any]:
        item = active.source_health(source_id)
        if item is None:
            raise HTTPException(status_code=404, detail="source health not found")
        return item.to_dict()

    @app.post("/api/v1/jobs/ingest")
    def ingest(payload: IngestPayload, request: Request) -> dict[str, Any]:
        require_shared_ingestion_operator(request)
        obs = payload.observation
        filters = payload.filters
        observation = SourceObservation(
            source_id=obs.source_id,
            source_mode=obs.source_mode,
            source_url=obs.source_url,
            raw_text=obs.raw_text,
            payload=obs.payload,
            observed_at=obs.observed_at or SourceObservation.__dataclass_fields__["observed_at"].default_factory(),
            posted_at=obs.posted_at,
            source_external_id=obs.source_external_id,
        )
        cfg = None
        if filters is not None:
            cfg = JobSearchFilters(
                sectors=tuple(filters.sectors),
                languages=tuple(filters.languages),
                locations=tuple(filters.locations),
                work_modes=tuple(filters.work_modes),
                seniority=tuple(filters.seniority),
                minimum_salary_eur=filters.minimum_salary_eur,
                excluded_employers=tuple(filters.excluded_employers),
                excluded_terms=tuple(filters.excluded_terms),
                include_unknown=filters.include_unknown,
            )
        return active.ingest(observation, filters=cfg).to_dict()

    def private_saved_jobs_profile(request: Request) -> str:
        # Authenticated requests resolve their own stable profile. The legacy
        # unprotected development fixture remains usable only in disabled mode.
        tenant, binding = tenant_context(request)
        if binding is None and authentication.mode != "disabled":
            raise HTTPException(status_code=401, detail="Authentication required")
        return tenant.profile_repository.profile_id

    @app.get("/api/v1/private-jobs")
    def list_private_saved_jobs(request: Request, limit: int = 100) -> JSONResponse:
        if not 1 <= limit <= 100:
            raise HTTPException(status_code=422, detail="limit must be 1 to 100")
        profile_id = private_saved_jobs_profile(request)
        records = app.state.private_saved_jobs.list(profile_id, limit=limit)
        return JSONResponse(
            content={
                "jobs": [item.to_dict() for item in records],
                "count": len(records),
                "private": True,
            },
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/private-jobs", status_code=201)
    def create_private_saved_job(
        payload: PrivateSavedJobPayload, request: Request
    ) -> JSONResponse:
        profile_id = private_saved_jobs_profile(request)
        try:
            item = app.state.private_saved_jobs.save(profile_id, payload.model_dump())
        except PrivateSavedJobError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return JSONResponse(
            status_code=201,
            content={"status": "saved_private", "job": item.to_dict()},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.delete("/api/v1/private-jobs/{saved_job_id}")
    def remove_private_saved_job(saved_job_id: str, request: Request) -> JSONResponse:
        profile_id = private_saved_jobs_profile(request)
        if not app.state.private_saved_jobs.delete(profile_id, saved_job_id):
            raise HTTPException(status_code=404, detail="Private saved job not found")
        return JSONResponse(
            content={"deleted": True},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/v1/search-preferences")
    def get_search_preferences(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        return app.state.search_preferences.get(profile_id).to_dict()

    @app.put("/api/v1/search-preferences")
    def save_search_preferences(
        payload: SearchPreferencesPayload, request: Request
    ) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        try:
            prefs = app.state.search_preferences.save(
                profile_id, payload.model_dump(exclude={"expected_revision"}),
                expected_revision=payload.expected_revision,
            )
        except SearchPreferenceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SearchPreferenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return prefs.to_dict()

    @app.get("/api/v1/search-results")
    def user_search_results(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        preferences = app.state.search_preferences.get(profile_id)
        result = search_jobs(tenant.list_jobs(), preferences)
        return {**result, "external_actions_authorized": False}

    @app.get("/api/v1/jobs")
    def list_jobs() -> dict[str, Any]:
        items = [item.to_dict() for item in active.list_jobs()]
        return {"jobs": items, "count": len(items)}

    @app.get("/api/v1/rankings")
    def rankings(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        items = [item.to_dict() for item in tenant.rankings()]
        return {"rankings": items, "count": len(items)}

    @app.get("/api/v1/jobs/{canonical_key}/score")
    def score_job(canonical_key: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        try:
            return tenant.score_job(canonical_key).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @app.post("/api/v1/jobs/{canonical_key}/prepare")
    def prepare_job(canonical_key: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        try:
            return tenant.prepare_job(canonical_key).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except PreparationNotEligible as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/v1/jobs/{canonical_key}/application-workspace")
    def start_application_workspace(canonical_key: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        candidate = tenant.get_job(canonical_key)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Job not found")
        profile = tenant.profile()
        cv = app.state.cv_repository.get(profile.profile_id)
        try:
            proposed = new_workspace(
                candidate, profile,
                source_cv_text=cv.text if cv else "",
                source_cv_sha256=cv.digest if cv else "",
            )
        except WorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        stored, created = app.state.workspace_repository.create_or_get(proposed)
        return {"workspace": stored.to_dict(), "created": created}

    @app.get("/api/v1/application-workspaces")
    def list_application_workspaces(request: Request, limit: int = 100) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        pid = tenant.profile_repository.profile_id
        items = app.state.workspace_repository.list(pid, limit=limit)
        return {"workspaces": [item.to_dict() for item in items], "count": len(items)}

    @app.get("/api/v1/local-ai/status")
    def local_ai_status(request: Request) -> dict[str, Any]:
        tenant_context(request)
        return app.state.local_ai.status()

    @app.post("/api/v1/application-workspaces/{workspace_id}/ai-suggestions")
    def application_ai_suggestions(
        workspace_id: str, payload: LocalAISuggestPayload, request: Request
    ) -> dict[str, Any]:
        if payload.acknowledge_local_ai_processing is not True:
            raise HTTPException(status_code=422, detail="Explicit consent for local processing is required")
        tenant, _ = tenant_context(request)
        pid = tenant.profile_repository.profile_id
        current = app.state.workspace_repository.get(pid, workspace_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        if current.status != "draft" or current.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="Review the current saved draft before requesting AI")
        if app.state.browser_receipts.get(pid, workspace_id) is not None:
            raise HTTPException(status_code=409, detail="This submitted application already has a browser-observed confirmation")
        candidate = tenant.get_job(current.canonical_key)
        if candidate is None or not candidate.source_current:
            raise HTTPException(status_code=409, detail="Job is no longer available")
        if candidate.description_fingerprint != current.job_fingerprint:
            raise HTTPException(status_code=409, detail="The employer job text changed; review it before generating")
        try:
            suggestion = app.state.local_ai.suggest(candidate, tenant.profile())
        except LocalDraftError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # Suggestions are never committed; a concurrent edit invalidates the proposal.
        latest = app.state.workspace_repository.get(pid, workspace_id)
        if latest is None or latest.revision != payload.expected_revision or latest.status != "draft":
            raise HTTPException(status_code=409, detail="Draft changed during AI generation; reload and retry")
        return {"suggestion": suggestion, "workspace_revision": latest.revision}

    @app.get("/api/v1/application-workspaces/{workspace_id}/handoff-readiness")
    def browser_handoff_readiness(workspace_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        item = app.state.workspace_repository.get(tenant.profile_repository.profile_id, workspace_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        job = tenant.get_job(item.canonical_key)
        result = review_handoff(item, job, tenant.profile())
        if app.state.browser_receipts.get(tenant.profile_repository.profile_id, workspace_id) is not None:
            result["ready"] = False
            result["blockers"].append("An employer confirmation is already recorded for this application")
        return result

    @app.post("/api/v1/application-workspaces/{workspace_id}/browser-packet")
    def create_browser_handoff_packet(
        workspace_id: str, payload: BrowserHandoffPayload, request: Request
    ) -> JSONResponse:
        if payload.confirm_private_data_transfer is not True:
            raise HTTPException(status_code=422, detail="Confirm the per-job personal-data transfer")
        tenant, _ = tenant_context(request)
        item = app.state.workspace_repository.get(tenant.profile_repository.profile_id, workspace_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        if item.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="Document revision changed; review and retry")
        if app.state.browser_receipts.get(tenant.profile_repository.profile_id, workspace_id) is not None:
            raise HTTPException(status_code=409, detail="An employer confirmation is already recorded for this application")
        job = tenant.get_job(item.canonical_key)
        try:
            packet = make_browser_packet(item, job, tenant.profile())
        except HandoffError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(
            {"packet": packet, "external_actions_performed": False},
            headers={"Cache-Control": "private, no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/v1/application-workspaces/{workspace_id}/browser-receipt")
    def browser_receipt_state(workspace_id: str, request: Request) -> JSONResponse:
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        owner = app.state.workspace_repository.get(profile_id, workspace_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        item = app.state.browser_receipts.get(profile_id, workspace_id)
        return JSONResponse(
            {"present": item is not None, "receipt": item.to_dict() if item else None},
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/v1/application-workspaces/{workspace_id}/browser-receipt")
    def record_browser_receipt(
        workspace_id: str, payload: BrowserReceiptImportPayload, request: Request
    ) -> JSONResponse:
        if payload.confirm_user_observed is not True:
            raise HTTPException(status_code=422, detail="Confirm you personally inspected the employer receipt")
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        workspace = app.state.workspace_repository.get(profile_id, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        try:
            receipt = validate_browser_receipt(workspace, payload.receipt)
            item = app.state.browser_receipts.record(receipt)
        except ReceiptError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ReceiptConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(
            {"receipt": item.to_dict(), "external_confirmation_verified": False},
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/v1/application-workspaces/{workspace_id}")
    def get_application_workspace(workspace_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        item = app.state.workspace_repository.get(tenant.profile_repository.profile_id, workspace_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        return {"workspace": item.to_dict()}

    @app.put("/api/v1/application-workspaces/{workspace_id}")
    def edit_application_workspace(
        workspace_id: str, payload: WorkspaceEditPayload, request: Request
    ) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        if app.state.browser_receipts.get(tenant.profile_repository.profile_id, workspace_id) is not None:
            raise HTTPException(
                status_code=409,
                detail="This application has an observed employer receipt and its submitted documents are frozen",
            )
        try:
            item = app.state.workspace_repository.edit(
                tenant.profile_repository.profile_id, workspace_id,
                expected_revision=payload.expected_revision,
                cv_text=payload.cv_text, cover_letter_text=payload.cover_letter_text,
            )
        except WorkspaceRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkspaceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        return {"workspace": item.to_dict()}

    @app.post("/api/v1/application-workspaces/{workspace_id}/report-applied")
    def report_external_application(
        workspace_id: str, payload: WorkspaceAppliedPayload, request: Request
    ) -> dict[str, Any]:
        if payload.confirmed_external_application is not True:
            raise HTTPException(status_code=422, detail="Explicit personal confirmation is required")
        tenant, _ = tenant_context(request)
        try:
            item = app.state.workspace_repository.report_applied(
                tenant.profile_repository.profile_id, workspace_id,
                expected_revision=payload.expected_revision,
                reference=payload.reference,
            )
        except WorkspaceRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkspaceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        return {"workspace": item.to_dict(), "external_confirmation_verified": False}

    @app.delete("/api/v1/application-workspaces/{workspace_id}")
    def remove_application_workspace(workspace_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        if not app.state.workspace_repository.delete(profile_id, workspace_id):
            raise HTTPException(status_code=404, detail="Application workspace not found")
        app.state.browser_receipts.delete(profile_id, workspace_id)
        return {"deleted": True}

    @app.get("/api/v1/application-workspaces/{workspace_id}/download/{kind}/{file_format}")
    def download_application_document(
        workspace_id: str, kind: str, file_format: str, request: Request
    ) -> Response:
        tenant, _ = tenant_context(request)
        item = app.state.workspace_repository.get(tenant.profile_repository.profile_id, workspace_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        if kind not in {"cv", "letter"} or file_format not in {"pdf", "docx"}:
            raise HTTPException(status_code=404, detail="Document format not available")
        try:
            content, mime, filename = render_document(
                item, kind=kind, file_format=file_format,
            )
        except WorkspaceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(
            content=content, media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox",
            },
        )

    @app.get("/api/v1/applications/summary")
    def application_summary(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        return tenant.application_summary()

    @app.get("/api/v1/applications")
    def list_applications(request: Request, limit: int = 100) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        bounded = max(1, min(limit, 500))
        items = [item.to_dict() for item in tenant.list_applications(limit=bounded)]
        return {"applications": items, "count": len(items)}

    @app.get("/api/v1/applications/{application_id}/events")
    def application_events(application_id: str, request: Request, limit: int = 500) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        item = tenant.get_application(application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="application not found")
        bounded = max(1, min(limit, 2000))
        events = [event.to_dict() for event in tenant.application_events(application_id, limit=bounded)]
        return {"events": events, "count": len(events)}

    @app.get("/api/v1/applications/{application_id}")
    def get_application(application_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        item = tenant.get_application(application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="application not found")
        return item.to_dict()

    @app.get("/api/v1/worker/tasks")
    def worker_tasks() -> dict[str, Any]:
        return _worker_snapshot()

    @app.get("/api/v1/dashboard")
    def dashboard(request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        return {
            **tenant.dashboard(),
            "worker": _worker_snapshot(),
        }

    @app.get("/api/v1/preparations")
    def list_preparations(request: Request, limit: int = 100) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        bounded = max(1, min(limit, 500))
        items = [item.to_dict() for item in tenant.list_preparations(limit=bounded)]
        return {"preparations": items, "count": len(items)}

    @app.get("/api/v1/preparations/{package_id}")
    def get_preparation(package_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        item = tenant.get_preparation(package_id)
        if item is None:
            raise HTTPException(status_code=404, detail="preparation not found")
        return item.to_dict()

    @app.post("/api/v1/preparations/{package_id}/refresh")
    def refresh_preparation(package_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        try:
            return tenant.refresh_preparation(package_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="preparation not found") from exc
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/jobs/{canonical_key}")
    def get_job(canonical_key: str) -> dict[str, Any]:
        item = active.get_job(canonical_key)
        if item is None:
            raise HTTPException(status_code=404, detail="job not found")
        return item.to_dict()

    @app.post("/api/v1/jobs/{canonical_key}/obumai")
    def submit_obumai(
        canonical_key: str,
        payload: ObumAITaskPayload,
        request: Request,
    ) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        try:
            return tenant.submit_obumai(
                canonical_key,
                action=payload.action,
                instructions=payload.instructions,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/obumai/jobs/{job_id}")
    def get_obumai_job(job_id: str, request: Request) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        if tenant.obumai is None:
            raise HTTPException(status_code=503, detail="ObumAI integration is not configured")
        if tenant.get_preparation_by_obum_job_id(job_id) is None:
            raise HTTPException(status_code=404, detail="ObumAI job not found")
        try:
            return tenant.obumai.get_job(job_id)
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/obumai/jobs/{job_id}/events")
    def get_obumai_events(
        job_id: str,
        request: Request,
        after_sequence: int = 0,
    ) -> dict[str, Any]:
        tenant, _ = tenant_context(request)
        if tenant.obumai is None:
            raise HTTPException(status_code=503, detail="ObumAI integration is not configured")
        if tenant.get_preparation_by_obum_job_id(job_id) is None:
            raise HTTPException(status_code=404, detail="ObumAI job not found")
        try:
            return tenant.obumai.get_events(job_id, after_sequence=after_sequence)
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "smartploy.api:app",
        host=os.getenv("SMARTPLOY_HOST", "127.0.0.1"),
        port=int(os.getenv("SMARTPLOY_PORT", "8090")),
        reload=False,
    )


if __name__ == "__main__":
    main()

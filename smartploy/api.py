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
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from .access import AccessPrincipal, AccessSettings, CloudflareAccessVerifier
from .application_storage import MemoryApplicationRepository, PostgresApplicationRepository
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
from .preparation_storage import MemoryPreparationRepository, PostgresPreparationRepository
from .preparations import PreparationNotEligible
from .profile_storage import MemoryProfileRepository, PostgresProfileRepository
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


class ProfileFactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=700)
    approved: bool = False


class FactApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool


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

    app = FastAPI(title="Smartploy API", version="0.5.0")
    allowed_hosts = _allowed_hosts()
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.add_middleware(
        SmartployAuthenticationMiddleware,
        authentication=authentication,
        sessions=sessions,
        access_settings=access_settings,
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
    app.state.identity_repository = identity_repository or _build_identity_repository()
    app.state.tenant_services = {}
    app.state.cv_repository = PostgresCVRepository(dsn) if dsn else MemoryCVRepository()

    def tenant_context(request: Request) -> tuple[SmartployService, UserProfileBinding | None]:
        principal = _principal_from_request(request)
        if principal is None:
            return active, None

        binding = app.state.identity_repository.resolve_or_create(principal)
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
    def health() -> dict[str, Any]:
        storage = active.storage_status()
        worker = _worker_snapshot()
        return {
            "ok": bool(storage.get("ready")),
            "service": "smartploy",
            "public_origin": app.state.public_origin,
            "storage": storage,
            "profile": active.profile_summary(),
            "obumai_configured": active.obumai is not None,
            "authentication": {
                "mode": authentication.mode,
                "oidc_enabled": authentication.oidc_enabled,
                "cloudflare_fallback_enabled": authentication.cloudflare_enabled,
            },
            "access": {
                "enabled": access_settings.enabled,
                "environment": access_settings.environment,
                "owner_restricted": bool(access_settings.allowed_email),
            },
            "worker": {
                "configured": worker["configured"],
                "ready": worker["ready"],
                "count": worker["count"],
                "error": worker["error"],
            },
            "external_actions_authorized": False,
        }

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
        binding = app.state.identity_repository.resolve_or_create(principal)
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

    @app.post("/api/v1/sources")
    def register_source(payload: SourcePolicyPayload) -> dict[str, Any]:
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
    def ingest(payload: IngestPayload) -> dict[str, Any]:
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

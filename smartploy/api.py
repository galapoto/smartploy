"""Smartploy FastAPI service."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import re
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.base_client import OAuthError
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import RedirectResponse, Response, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool
import uvicorn
from psycopg import Error as PostgresError

from .access import AccessPrincipal, AccessSettings, CloudflareAccessVerifier
from .ai_processing_consent import (
    ConsentIdentityError, JobAIConsentRepository, MemoryJobAIConsentRepository,
    PostgresJobAIConsentRepository,
)
from .auto_draft_shortlist import prepare_profile_shortlist
from .training_directory import TrainingDirectoryError, load_training_programs
from .application_storage import MemoryApplicationRepository, PostgresApplicationRepository
from .application_workspace import (
    WorkspaceError, WorkspaceRevisionConflict, cover_letter_proposal,
    new_workspace, render_document,
)
from .application_workspace_storage import MemoryWorkspaceRepository, PostgresWorkspaceRepository
from .application_agents import ApplicationAgentConflict, PostgresApplicationAgentRepository
from .browser_handoff import HandoffError, approved_fields_sha256, make_browser_packet, review_handoff
from .employer_submit_claim_storage import EmployerSubmitClaimDenied, PostgresEmployerSubmitClaimRepository
from .employer_review_intent_storage import (
    EmployerReviewIntentDenied, PostgresEmployerReviewIntentRepository,
)
from .employer_automation_rights import (
    ACTION, LEVER_API_ACTION, ASHBY_API_ACTION, PostgresEmployerAutomationRightsRepository,
)
from .lever_partner_submit import (
    LeverPartnerRegistry, LeverPartnerTransport, LeverPartnerUnavailable,
    LeverPartnerUncertain, PostgresPartnerApplicationReceipts,
)
from .ashby_partner_submit import (
    AshbyPartnerRegistry, AshbyPartnerTransport, AshbyPartnerUnavailable,
    AshbyPartnerUncertain,
)
from .employer_final_action_gate import EmployerFinalActionDenied
from .employer_final_action_gate import PostgresEmployerFinalActionGate
from .browser_receipt import ReceiptError, validate_browser_receipt
from .browser_receipt_storage import (
    ReceiptConflict, MemoryBrowserReceiptRepository, PostgresBrowserReceiptRepository,
)
from .local_drafting import LocalDraftClient, LocalDraftError, LocalDraftSettings
from .cv_import import CVImportError, parse_cv
from .cv_job_matching import cv_job_matches
from .cv_storage import MemoryCVRepository, PostgresCVRepository
from .profile import FACT_TYPES, ProfileFact
from .identity import (
    AuthenticatedPrincipal,
    IdentityRepository,
    MemoryIdentityRepository,
    PostgresIdentityRepository,
    UserProfileBinding,
)
from .domain import JobSearchFilters, SourceObservation, SourcePolicy, canonical_json
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
    OIDC_FLOW_COOKIE_NAME,
    SmartployAuthenticationMiddleware,
    authlib_oidc_session_marker,
    build_oidc_registry,
    clear_oidc_flow_cookie,
    clear_session_cookie,
    consume_browser_bound_oidc_flow,
    set_oidc_flow_cookie,
    set_session_cookie,
    start_browser_bound_oidc_flow,
)
from .private_saved_jobs import (
    MemoryPrivateSavedJobRepository,
    PostgresPrivateSavedJobRepository,
    PrivateSavedJobError,
)
from .preparation_storage import MemoryPreparationRepository, PostgresPreparationRepository
from .preparations import (
    PREPARATION_ACTION, PreparationNotEligible,
    approved_evidence_snapshot, preparation_job_snapshot,
)
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
    auto_draft_enabled: StrictBool = False
    auto_agent_tracking_enabled: StrictBool = False
    expected_revision: int = Field(ge=0)


class ApplicationWorkspaceStartPayload(BaseModel):
    """Optional in-app-only agent for an explicitly selected AutoApply job.

    Existing manual/assisted clients send no body and keep their old behavior.
    No employer action, model call, email, or worker activation is authorized.
    """
    model_config = ConfigDict(extra="forbid")
    start_private_agent: StrictBool = False
    confirm_in_app_tracking_only: StrictBool = False


class WorkspaceEditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    cv_text: str = Field(min_length=1, max_length=30000)
    cover_letter_text: str = Field(min_length=1, max_length=10000)


class ApplicationAgentMilestonePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, le=2147483647)
    milestone: Literal[
        "recruiter_replied", "interview", "offer", "rejected", "hired"
    ]
    confirmed_personally_observed: StrictBool = False


class ApplicationAgentReportedFollowupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, le=2147483647)
    confirmed_sent_by_applicant: StrictBool = False


class ApplicationAgentTransitionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, le=2147483647)


class LocalAISuggestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    acknowledge_local_ai_processing: bool


class EvidenceLetterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, le=2147483647)
    language: Literal["fi", "en"]


class BrowserHandoffPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirm_private_data_transfer: bool


class EmployerReviewIntentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_cv_pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_reviewed_application: StrictBool
    acknowledge_manual_only: StrictBool


class LeverPartnerApplicationPayload(BaseModel):
    """Real provider transfer only after exact signed-in applicant click."""
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_cv_pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_fields_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_cv_pdf_size: int = Field(ge=12, le=2 * 1024 * 1024)
    explicit_final_user_approval: StrictBool
    approve_employer_data_transfer: StrictBool
    affirm_reviewed_employer_form: StrictBool


class BrowserReviewVerificationPayload(BaseModel):
    """Secret-free, exact packet fingerprints; NO browser execution grant."""
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_cv_pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_fields_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_application_url_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_cv_pdf_size: int = Field(ge=12, le=2 * 1024 * 1024)


class BrowserFinalAttemptPayload(BrowserReviewVerificationPayload):
    """Separate explicit final-click decision for one reviewed employer job."""
    confirm_one_job_final_click: StrictBool
    acknowledge_external_employer_transfer: StrictBool
    acknowledge_no_automatic_retry: StrictBool


class BrowserReceiptImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_user_observed: bool
    receipt: dict[str, Any]


class WorkspaceAppliedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_external_application: bool
    expected_revision: int = Field(ge=1)
    reference: str = Field(default="", max_length=250)


class AIProcessingConsentPayload(BaseModel):
    """A per-job, literal-true opt-in for legacy durable ObumAI processing."""
    model_config = ConfigDict(extra="forbid")
    acknowledge_obumai_processing: StrictBool


class ObumAITaskPayload(AIProcessingConsentPayload):
    action: str = Field(min_length=1, max_length=64)
    instructions: str = Field(default="", max_length=20_000)


class GrantUnattendedAIConsentPayload(BaseModel):
    """Grant one future-draft permission for today's job + approved facts."""
    model_config = ConfigDict(extra="forbid")
    canonical_key: str = Field(min_length=1, max_length=256)
    acknowledge_obumai_processing: StrictBool


# These are reasoning/draft tasks; an arbitrary action string must never be
# interpreted by a downstream agent as permission for external side effects.
SELF_SERVICE_OBUMAI_ACTIONS = frozenset({"fit_analysis", PREPARATION_ACTION})


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
    processing_consent_repository: JobAIConsentRepository | None = None,
) -> FastAPI:
    active = service or _build_service()
    authentication = AuthenticationSettings.from_env()
    access_settings = AccessSettings.from_env(
        require_enabled_in_production=authentication.cloudflare_enabled
    )
    oidc_settings = OIDCSettings.from_env(authentication)
    public_origin = _public_origin()
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
        oidc_public_origin=oidc_settings.public_origin if oidc_settings else public_origin,
        access_verifier=access_verifier,
    )
    app.state.smartploy = active
    app.state.public_origin = public_origin
    app.state.authentication = authentication
    app.state.access_settings = access_settings
    app.state.oidc_settings = oidc_settings
    app.state.oidc_registry = oidc_registry
    app.state.oidc_client = oidc_remote
    app.state.session_repository = sessions
    app.state.identity_repository = resolved_identities
    # Empty allowlist denies every authenticated browser user shared writes.
    # Production operators must be granted an explicit stable server user ID.
    app.state.operator_access = OperatorAccessPolicy.from_env()
    app.state.tenant_services = {}
    app.state.cv_repository = PostgresCVRepository(dsn) if dsn else MemoryCVRepository()
    app.state.workspace_repository = PostgresWorkspaceRepository(dsn) if dsn else MemoryWorkspaceRepository()
    # Headless Agent Zero requires durable PostgreSQL; memory mode is not a fake agent.
    app.state.application_agent_repository = PostgresApplicationAgentRepository(dsn) if dsn else None
    app.state.browser_receipts = PostgresBrowserReceiptRepository(dsn) if dsn else MemoryBrowserReceiptRepository()
    # SP15b: read-only employer claim posture. No memory fallback, issuer or final-click API.
    app.state.employer_claims = PostgresEmployerSubmitClaimRepository(dsn) if dsn else None
    app.state.employer_review_intents = PostgresEmployerReviewIntentRepository(dsn) if dsn else None
    # Independent reviewed employer terms are NOT job-discovery SourcePolicy.
    # SP15e: read-only posture. No web issuer/redeemer or browser final click.
    app.state.employer_rights = PostgresEmployerAutomationRightsRepository(dsn) if dsn else None
    app.state.employer_final_actions = PostgresEmployerFinalActionGate(dsn) if dsn else None
    # Default OFF in existing production installations. This flag cannot
    # bypass one-job independent employer rights or user review.
    app.state.browser_final_enabled = (
        os.getenv("SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED", "false").strip().lower()
        == "true"
    )
    app.state.partner_lever_registry = LeverPartnerRegistry.from_env()
    app.state.partner_lever_transport = LeverPartnerTransport()
    app.state.partner_lever_receipts = PostgresPartnerApplicationReceipts(dsn) if dsn else None
    # SP52: same owner/claim/receipt ledger, but separate employer-issued
    # posting credentials and distinct exact Ashby rights action scope.
    app.state.partner_ashby_registry = AshbyPartnerRegistry.from_env()
    app.state.partner_ashby_transport = AshbyPartnerTransport()
    app.state.partner_ashby_receipts = app.state.partner_lever_receipts
    app.state.local_ai = LocalDraftClient(LocalDraftSettings.from_env())
    app.state.search_preferences = (
        PostgresSearchPreferenceRepository(dsn) if dsn else MemorySearchPreferenceRepository()
    )
    app.state.private_saved_jobs = (
        PostgresPrivateSavedJobRepository(dsn) if dsn
        else MemoryPrivateSavedJobRepository()
    )
    app.state.processing_consents = processing_consent_repository or (
        PostgresJobAIConsentRepository(dsn) if dsn
        else MemoryJobAIConsentRepository()
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
        build_revision = os.getenv("SMARTPLOY_APP_VERSION", "").strip().lower()
        # Dockerfile APP_VERSION is derived from the reviewed Git SHA; never
        # echo arbitrary build args or user-configured strings into public health.
        release_revision = (
            build_revision if re.fullmatch(r"[0-9a-f]{12}", build_revision) else ""
        )
        safe = {
            "ok": bool(storage.get("ready")),
            "service": "smartploy",
            "release_revision": release_revision,
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
        response = await oidc_remote.authorize_redirect(request, oidc_settings.redirect_uri)
        # Authlib caches PKCE + nonce in PostgreSQL. Its modern CSRF protection
        # also requires a browser-specific marker across the ZITADEL redirect.
        # The previous ephemeral request.scope["session"] was lost on redirect.
        state_values = parse_qs(urlsplit(response.headers.get("location", "")).query).get("state", [])
        if len(state_values) != 1:
            raise HTTPException(status_code=502, detail="OIDC login could not be initiated")
        try:
            browser_token = await start_browser_bound_oidc_flow(
                state_cache, state_values[0], oidc_settings.state_ttl_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="OIDC login could not be initiated") from exc
        set_oidc_flow_cookie(response, browser_token, oidc_settings.state_ttl_seconds)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.api_route("/auth/callback", methods=["GET", "POST"])
    async def auth_callback(request: Request):
        if oidc_settings is None or oidc_remote is None:
            raise HTTPException(status_code=404, detail="OIDC login is not enabled")
        if request.method == "POST":
            # ZITADEL currently uses GET/query callbacks; preserve fail-closed
            # form-post compatibility only when the form is parseable.
            try:
                state = str((await request.form()).get("state") or "")
            except Exception:
                state = ""
        else:
            state = request.query_params.get("state", "")
        browser_token = request.cookies.get(OIDC_FLOW_COOKIE_NAME, "")
        if not await consume_browser_bound_oidc_flow(state_cache, state, browser_token):
            raise HTTPException(status_code=401, detail="OIDC callback validation failed")
        # The marker is issued ONLY after verifying the independent,
        # host-only browser cookie against the single-use PostgreSQL binding.
        # Authlib still validates OAuth state, PKCE and OIDC ID-token nonce.
        marker_key, marker_value = authlib_oidc_session_marker(
            state, oidc_settings.state_ttl_seconds,
        )
        request.scope["session"] = {marker_key: marker_value}
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
        clear_oidc_flow_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        return response

    # These pages contain no account-specific values, cookies or identity
    # details. A cross-site GET navigation must never revoke a session.
    def logout_page(content: str, *, status_code: int = 200) -> Response:
        return Response(
            content=content,
            status_code=status_code,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": (
                    "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                    "form-action 'self'; style-src 'unsafe-inline'"
                ),
            },
        )

    @app.get("/auth/logout")
    async def auth_logout_confirmation() -> Response:
        if oidc_settings is None:
            raise HTTPException(status_code=404, detail="OIDC logout is not enabled")
        return logout_page(
            """<!doctype html><html lang="en"><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Sign out | SmartPloy</title><style>
            body{background:#f5f7f8;color:#18343c;font:16px/1.6 system-ui,sans-serif;
                 min-height:100vh;display:grid;place-items:center;margin:0;padding:1rem}
            main{max-width:450px;background:white;padding:2rem;border-radius:20px;
                 box-shadow:0 12px 38px #18343c12}
            h1{font-size:1.7rem;line-height:1.25}
            button{background:#175b62;color:white;border:0;border-radius:10px;
                   padding:0.85rem 1.4rem;font:inherit;font-weight:650;cursor:pointer}
            a{color:#175b62;margin-left:1rem}
            small{display:block;margin-top:1.5rem;color:#50676b}
            </style></head><body><main><strong>SmartPloy</strong>
            <h1>Sign out of SmartPloy?</h1>
            <p>Confirm to end this browser's SmartPloy session.
            This will not submit a job application or change your profile.</p>
            <form method="post" action="/auth/logout">
              <button type="submit">Confirm sign out</button>
              <a href="/">Cancel</a>
            </form><small>Your identity provider may have its own session.</small>
            </main></body></html>"""
        )

    @app.post("/auth/logout")
    async def auth_logout(request: Request) -> Response:
        if oidc_settings is None:
            raise HTTPException(status_code=404, detail="OIDC logout is not enabled")

        # A browser form POST supplies Origin. SameSite=Lax alone does not
        # stop requests from another same-site subdomain. Do not rely on
        # caller-controlled Host or reverse-proxy forwarding headers.
        if (
            request.headers.get("origin", "") != oidc_settings.public_origin
            or request.headers.get("sec-fetch-site", "").strip().casefold()
            not in {"", "same-origin", "none"}
        ):
            return SmartployAuthenticationMiddleware._deny(
                403, "csrf_origin_denied",
                "Confirm sign-out from the SmartPloy website.",
            )

        raw_session = request.cookies.get(SESSION_COOKIE_NAME, "")
        if raw_session:
            try:
                await asyncio.to_thread(sessions.revoke, raw_session)
            except Exception:
                # Clearing a browser cookie does NOT prove that the backing
                # database session was revoked. Do not claim full sign-out or
                # redirect to the identity provider in this failure mode.
                response = logout_page(
                    """<!doctype html><html lang="en"><head><meta charset="utf-8">
                    <title>Sign-out incomplete | SmartPloy</title></head>
                    <body><main><h1>Sign-out could not be completed</h1>
                    <p>Your browser cookie has been cleared, but the server
                    could not confirm session revocation. Close this browser
                    on a shared device and contact support if necessary.</p>
                    <a href="/auth/login">Sign in again</a></main></body></html>""",
                    status_code=503,
                )
                clear_session_cookie(response)
                return response

        if oidc_remote is not None:
            request.scope.setdefault("session", {})
            try:
                response = await oidc_remote.logout_redirect(
                    request,
                    post_logout_redirect_uri=oidc_settings.post_logout_redirect_uri,
                    client_id=oidc_settings.client_id,
                )
            except Exception:
                # Local session is revoked; provider logout is not confirmed.
                response = RedirectResponse(url="/auth/logged-out", status_code=303)
        else:
            response = RedirectResponse(url="/auth/logged-out", status_code=303)
        clear_session_cookie(response)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/auth/logged-out")
    async def auth_logged_out() -> Response:
        # A direct external GET must be inert: do not revoke or even clear an
        # existing cookie here. The protected POST already did both.
        return logout_page(
            """<!doctype html><html lang="en"><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>SmartPloy sign-out</title></head><body>
            <main><h1>SmartPloy sign-out</h1>
            <p>If you confirmed sign-out, your local SmartPloy session has ended.
            Signing out of your identity provider may require a separate step.</p>
            <a href="/auth/login">Sign in</a></main></body></html>"""
        )

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

    @app.get("/api/v1/profile/cv/matches")
    def cv_first_job_matches(
        request: Request,
        limit: int = Query(default=40, ge=1, le=100),
        recommended_offset: int = Query(default=0, ge=0, le=100000),
        other_offset: int = Query(default=0, ge=0, le=100000),
        query: str = Query(default="", max_length=120),
        selected_job_key: str = Query(default="", max_length=160),
    ) -> JSONResponse:
        """Owner-bound, paged CV search of the ENTIRE current job ledger.

        Separate lane offsets preserve the original ranking. The selected
        posting is independently pinned by exact current canonical key,
        even if it falls outside both page windows. No employer actions.
        """
        if any(ord(char) < 32 for char in query + selected_job_key):
            raise HTTPException(status_code=422, detail="Unsupported CV search value")
        tenant, _ = tenant_context(request)
        profile_id = tenant.profile_repository.profile_id
        cv = app.state.cv_repository.get(profile_id)
        result = cv_job_matches(
            cv, tenant.list_jobs(), profile_id=profile_id,
            max_items=limit, recommended_offset=recommended_offset,
            other_offset=other_offset, query=query,
            selected_job_key=selected_job_key,
        )
        return JSONResponse(result, headers={"Cache-Control": "private, no-store"})

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
        # Unauthenticated local test/development APIs preserve the legacy
        # manual-ingest fixtures. Production disallows disabled auth entirely.
        if authentication.mode == "disabled":
            return

        # The auth middleware supplies the verified principal; resolve its
        # canonical user ID (including explicitly linked provider identities).
        # Do not inspect email, headers, or client-provided role claims.
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

    # This is a permission ledger, not an automatic AI scheduler or a consent
    # inferred from configuring ObumAI. All operations need verified identity.
    def consent_context(request: Request) -> tuple[SmartployService, UserProfileBinding]:
        tenant, binding = tenant_context(request)
        if binding is None:
            raise HTTPException(status_code=401, detail="Verified sign-in is required for AI processing consent")
        return tenant, binding

    @app.get("/api/v1/ai-processing-consents")
    def ai_processing_consents(request: Request, limit: int = 100) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
        _, binding = consent_context(request)
        items = app.state.processing_consents.list(binding, limit=limit)
        return {
            "consents": [item.to_dict() for item in items],
            "count": len(items),
            "private": True,
            "unattended_processing_enabled": False,
        }

    @app.get("/api/v1/ai-processing-consents/events")
    def ai_processing_consent_events(request: Request, limit: int = 100) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
        _, binding = consent_context(request)
        events = app.state.processing_consents.events(binding, limit=limit)
        return {
            "events": [event.to_dict() for event in events],
            "count": len(events),
            "private": True,
            "history_type": "consent_grant_and_withdrawal_only",
        }

    @app.post("/api/v1/ai-processing-consents")
    def grant_ai_processing_consent(
        payload: GrantUnattendedAIConsentPayload, request: Request,
    ) -> dict[str, Any]:
        if payload.acknowledge_obumai_processing is not True:
            raise HTTPException(status_code=422, detail="Explicit ObumAI consent is required")
        tenant, binding = consent_context(request)
        candidate = tenant.get_job(payload.canonical_key)
        if candidate is None:
            raise HTTPException(status_code=404, detail="job not found")
        if not candidate.source_current:
            raise HTTPException(status_code=409, detail="This job is no longer current")
        # A source without an explicitly affirmative forwarding decision
        # cannot be turned into a third-party AI permission by the user.
        if candidate.job.raw.get("external_ai_forwarding_allowed") is not True:
            raise HTTPException(status_code=409, detail="Job source does not authorize AI forwarding")
        evidence = approved_evidence_snapshot(tenant.profile())
        if not evidence.get("approved_fact_count"):
            raise HTTPException(status_code=409, detail="Approve profile evidence before consenting")
        job_snapshot = preparation_job_snapshot(candidate)
        job_hash = sha256(canonical_json(job_snapshot).encode("utf-8")).hexdigest()
        evidence_hash = sha256(canonical_json(evidence).encode("utf-8")).hexdigest()
        try:
            item, changed = app.state.processing_consents.grant(
                binding, candidate.canonical_key, job_hash, evidence_hash,
            )
        except ConsentIdentityError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        # No AI request, automatic preparation registration, or employer action.
        return {
            "consent": item.to_dict(),
            "created_or_updated": changed,
            "processing_started": False,
            "external_actions_authorized": False,
        }

    @app.delete("/api/v1/ai-processing-consents/{consent_id}")
    def revoke_ai_processing_consent(consent_id: str, request: Request) -> dict[str, Any]:
        _, binding = consent_context(request)
        item = app.state.processing_consents.revoke(binding, consent_id)
        if item is None:
            # Another user's consent ID is indistinguishable from a missing ID.
            raise HTTPException(status_code=404, detail="consent not found")
        return {
            "consent": item.to_dict(),
            "revoked": True,
            "future_processing_authorized": False,
            "external_actions_authorized": False,
        }

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

    @app.post("/api/v1/auto-draft/prepare")
    def prepare_automatic_application_drafts(request: Request) -> JSONResponse:
        """Opted-in user prepares their own exact matching IT job drafts NOW.

        No ObumAI calls, ATS submits, browser clicks or provider consent
        inference. The original middleware authenticates & checks CSRF;
        expected-user-ID must match the verified account before writes.
        """
        tenant, binding = tenant_context(request)
        if (
            binding is None
            or request.headers.get("Origin", "") != public_origin
            or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
            or request.headers.get("Sec-Fetch-Site", "").casefold() not in
                {"", "same-origin", "none"}
        ):
            raise HTTPException(status_code=403, detail="Verified same-origin user required")
        pref = app.state.search_preferences.get(binding.profile_id)
        if not pref.auto_draft_enabled or pref.mode != "personalized":
            raise HTTPException(status_code=409, detail="Enable automatic draft preparation in your private job settings")
        cv_repo = app.state.cv_repository
        try:
            summary = prepare_profile_shortlist(
                binding.profile_id,
                preferences_repository=app.state.search_preferences,
                job_repository=tenant.repository,
                profile_repository=tenant.profile_repository,
                cv_repository=cv_repo,
                workspace_repository=app.state.workspace_repository,
                application_agent_repository=app.state.application_agent_repository,
            )
        except Exception:
            # Do not leak candidate CV, source URLs, DB secrets or private IDs.
            raise HTTPException(status_code=503, detail="Automatic draft preparation unavailable") from None
        return JSONResponse(
            summary.public_counts(),
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/v1/training-programs")
    def training_program_directory() -> JSONResponse:
        """Read-only provider destinations, never active-vacancy or application data."""
        try:
            programmes = load_training_programs()
        except TrainingDirectoryError:
            raise HTTPException(status_code=503, detail="Training programme directory unavailable") from None
        return JSONResponse({
            "programs": programmes,
            "count": len(programmes),
            "opening_status": "check_provider",
            "job_count_included": 0,
            "external_actions_authorized": False,
        }, headers={"Cache-Control": "private, no-store"})

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
    def prepare_job(
        canonical_key: str, payload: AIProcessingConsentPayload, request: Request
    ) -> dict[str, Any]:
        # Legacy /prepare submits approved profile evidence and job text to
        # ObumAI. Unlike /application-workspace, this is NOT local-only editing.
        if payload.acknowledge_obumai_processing is not True:
            raise HTTPException(
                status_code=422,
                detail="Explicit per-job consent for ObumAI processing is required",
            )
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
    def start_application_workspace(
        canonical_key: str, request: Request,
        payload: ApplicationWorkspaceStartPayload | None = None,
    ) -> dict[str, Any]:
        tenant, binding = tenant_context(request)
        wants_agent = bool(payload and payload.start_private_agent)
        # This is an explicit, one-job candidate decision, not inferred from
        # CV upload or job discovery. Reuse the same origin/user boundary as
        # the original POST /application-workspaces/{id}/agent action.
        if wants_agent:
            if payload is None or payload.confirm_in_app_tracking_only is not True:
                raise HTTPException(
                    status_code=422,
                    detail="Explicit in-app-only application tracking acknowledgement required",
                )
            if (
                binding is None
                or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
                or request.headers.get("Origin", "") != public_origin
                or request.headers.get("Sec-Fetch-Site", "").casefold()
                    not in {"", "same-origin", "none"}
            ):
                raise HTTPException(
                    status_code=403, detail="Verified same-origin application owner required",
                )
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
        result: dict[str, Any] = {"workspace": stored.to_dict(), "created": created}
        if wants_agent:
            # Reuse SP22/31 Postgres case identity, atomic idempotence, and
            # worker task. A missing migration/DB does not erase the user's
            # successfully saved draft or fabricate a tracking case.
            agent = None
            agent_created = False
            if app.state.application_agent_repository is not None:
                try:
                    agent, agent_created = app.state.application_agent_repository.create_or_get(
                        profile.profile_id, stored.workspace_id
                    )
                except PostgresError:
                    pass
            result["agent_tracking"] = {
                "requested": True,
                "state": agent["state"] if agent is not None else "unavailable",
                "created": agent_created,
                "external_actions_performed": 0,
                "worker_wake_verified": False,
            }
        return result


    def application_agent_context(
        request: Request, *, mutate: bool = False
    ) -> tuple[PostgresApplicationAgentRepository, str]:
        tenant, binding = tenant_context(request)
        if binding is None:
            raise HTTPException(status_code=403, detail="Verified account required for application agents")
        if mutate and (
            request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
            or request.headers.get("Origin", public_origin) != public_origin
            or request.headers.get("Sec-Fetch-Site", "").casefold()
                not in {"", "same-origin", "none"}
        ):
            raise HTTPException(status_code=403, detail="Verified same-origin account action required")
        repo = app.state.application_agent_repository
        if repo is None:
            raise HTTPException(
                status_code=503,
                detail="Durable application agents require PostgreSQL and deployment migration",
            )
        return repo, tenant.profile_repository.profile_id

    @app.get("/api/v1/application-workspaces/{workspace_id}/agent")
    def get_workspace_application_agent(workspace_id: str, request: Request) -> JSONResponse:
        """Owner-bound O(1) case lookup, including accounts with >100 cases."""
        repo, owner = application_agent_context(request)
        try:
            agent = repo.get_for_workspace(owner, workspace_id)
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agent unavailable") from exc
        return JSONResponse(
            {"present": agent is not None, "agent": agent,
             "external_actions_authorized": False},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/application-workspaces/{workspace_id}/agent")
    def start_application_agent(workspace_id: str, request: Request) -> JSONResponse:
        repo, owner = application_agent_context(request, mutate=True)
        try:
            agent, created = repo.create_or_get(owner, workspace_id)
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agent storage unavailable") from exc
        if agent is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        return JSONResponse(
            {"agent": agent, "created": created, "external_actions_performed": 0},
            status_code=201 if created else 200,
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/v1/application-agents")
    def list_application_agents(
        request: Request, limit: int = Query(default=100, ge=1, le=100)
    ) -> JSONResponse:
        repo, owner = application_agent_context(request)
        try:
            agents = repo.list(owner, limit=limit)
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agents unavailable") from exc
        return JSONResponse(
            {"agents": agents, "count": len(agents), "external_actions_authorized": False},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/v1/application-agents/inbox")
    def read_application_agent_inbox(
        request: Request,
        limit: int = Query(default=25, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
    ) -> JSONResponse:
        """Owned next-action queue, read only: never imply a worker ran."""
        repo, owner = application_agent_context(request)
        try:
            result = repo.inbox(owner, limit=limit, offset=offset)
        except PostgresError as exc:
            raise HTTPException(
                status_code=503, detail="Application agent inbox unavailable",
            ) from exc
        return JSONResponse(
            result, headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/application-agents/inbox/check-due")
    def check_due_application_agent_inbox(request: Request) -> JSONResponse:
        """SP37: candidate-requested private reconciliation, 10 cases maximum.

        The existing OIDC expected-user/same-origin mutation gate runs before
        any case read or write. Only owner-scoped due/status-changed agents
        are checked; no employer actions, out-of-app sends or worker opt-in.
        """
        repo, owner = application_agent_context(request, mutate=True)
        try:
            result = repo.check_due_inbox(owner, limit=10)
        except PostgresError as exc:
            raise HTTPException(
                status_code=503,
                detail="Private application inbox check unavailable",
            ) from exc
        return JSONResponse(
            {"checked_in_app": True, **result},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/v1/application-agents/{agent_id}")
    def read_application_agent(
        agent_id: str, request: Request,
        after_sequence: int = Query(default=0, ge=0, le=2147483647),
    ) -> JSONResponse:
        repo, owner = application_agent_context(request)
        try:
            agent = repo.get(owner, agent_id)
            events = repo.events(owner, agent_id, after_sequence=after_sequence) if agent else []
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agent unavailable") from exc
        if agent is None:
            raise HTTPException(status_code=404, detail="Application agent not found")
        return JSONResponse(
            {"agent": agent, "events": events, "count": len(events),
             "next_cursor": events[-1]["sequence"] if events else after_sequence,
             "external_actions_authorized": False},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/application-agents/{agent_id}/check-now")
    def check_application_agent_now(agent_id: str, request: Request) -> JSONResponse:
        """User-initiated, owner-scoped in-app reconciliation; never employer I/O.

        Reuses the original leased worker's idempotent PostgreSQL case engine,
        but scopes both the status reconciliation AND due event to precisely
        this signed-in owner's agent. This is not proof a background task ran.
        """
        repo, owner = application_agent_context(request, mutate=True)
        try:
            current = repo.get(owner, agent_id)
            if current is None:
                raise HTTPException(status_code=404, detail="Application agent not found")
            if current["state"] != "active":
                raise HTTPException(
                    status_code=409,
                    detail="Only an active private application agent can be checked",
                )
            outcome = repo.process_due(
                limit=1, profile_id=owner, agent_id=agent_id,
            )
            latest = repo.get(owner, agent_id)
        except PostgresError as exc:
            raise HTTPException(
                status_code=503, detail="Application agent check unavailable",
            ) from exc
        if latest is None:
            # A concurrent account erasure or deletion cannot leak case data.
            raise HTTPException(status_code=404, detail="Application agent not found")
        return JSONResponse(
            {
                "agent": latest,
                "checked_in_app": True,
                "workspace_updates_reconciled": outcome["workspace_updates_reconciled"],
                "in_app_reminders": outcome["in_app_reminders"],
                "external_actions_performed": 0,
                "employer_contacts": 0,
                "background_worker_verified": False,
            },
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/application-agents/{agent_id}/milestone")
    def report_candidate_milestone(
        agent_id: str, payload: ApplicationAgentMilestonePayload,
        request: Request,
    ) -> JSONResponse:
        if payload.confirmed_personally_observed is not True:
            raise HTTPException(
                status_code=422, detail="Personally confirm this recruiter outcome"
            )
        repo, owner = application_agent_context(request, mutate=True)
        try:
            agent = repo.record_milestone(
                owner, agent_id, milestone=payload.milestone,
                expected_revision=payload.expected_revision,
            )
        except ApplicationAgentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agent unavailable") from exc
        if agent is None:
            raise HTTPException(status_code=404, detail="Application agent not found")
        return JSONResponse(
            {"agent": agent, "milestone_source": "candidate_self_report",
             "employer_response_verified": False, "external_actions_performed": 0},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/application-agents/{agent_id}/followup-sent")
    def report_candidate_followup_sent(
        agent_id: str, payload: ApplicationAgentReportedFollowupPayload,
        request: Request,
    ) -> JSONResponse:
        if payload.confirmed_sent_by_applicant is not True:
            raise HTTPException(
                status_code=422, detail="Confirm that you personally sent the follow-up"
            )
        repo, owner = application_agent_context(request, mutate=True)
        try:
            agent = repo.log_candidate_followup(
                owner, agent_id, expected_revision=payload.expected_revision,
            )
        except ApplicationAgentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agent unavailable") from exc
        if agent is None:
            raise HTTPException(status_code=404, detail="Application agent not found")
        return JSONResponse(
            {"agent": agent, "record_source": "candidate_self_report",
             "external_delivery_verified": False, "external_actions_performed": 0},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/v1/application-agents/{agent_id}/{action}")
    def change_application_agent(
        agent_id: str, action: str, payload: ApplicationAgentTransitionPayload,
        request: Request,
    ) -> JSONResponse:
        if action not in {"pause", "resume", "close"}:
            raise HTTPException(status_code=404, detail="Application agent action not found")
        repo, owner = application_agent_context(request, mutate=True)
        try:
            agent = repo.transition(
                owner, agent_id, action=action,
                expected_revision=payload.expected_revision,
            )
        except ApplicationAgentConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PostgresError as exc:
            raise HTTPException(status_code=503, detail="Application agent unavailable") from exc
        if agent is None:
            raise HTTPException(status_code=404, detail="Application agent not found")
        return JSONResponse(
            {"agent": agent, "external_actions_performed": 0},
            headers={"Cache-Control": "private, no-store"},
        )

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

    @app.post("/api/v1/application-workspaces/{workspace_id}/letter-proposal")
    def preview_evidence_letter(
        workspace_id: str, payload: EvidenceLetterPayload, request: Request,
    ) -> JSONResponse:
        """Applicant-selected Finnish/English draft, no AI or document write.

        Reuses the exact original workspace owner, posting-fingerprint and
        approved-facts boundaries used by existing Application Studio drafts.
        This is NOT an employer send or a model action.
        """
        tenant, binding = tenant_context(request)
        if binding is None or (
            request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
            or request.headers.get("Origin", public_origin) != public_origin
            or request.headers.get("Sec-Fetch-Site", "").casefold()
                not in {"", "same-origin", "none"}
        ):
            raise HTTPException(
                status_code=403, detail="Verified same-origin account action required",
            )
        pid = tenant.profile_repository.profile_id
        current = app.state.workspace_repository.get(pid, workspace_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        if current.status != "draft" or current.revision != payload.expected_revision:
            raise HTTPException(
                status_code=409, detail="Review the current saved draft before changing its language",
            )
        if app.state.browser_receipts.get(pid, workspace_id) is not None:
            raise HTTPException(
                status_code=409, detail="Submitted application already has a browser receipt",
            )
        candidate = tenant.get_job(current.canonical_key)
        if candidate is None or not candidate.source_current:
            raise HTTPException(status_code=409, detail="Employer posting is no longer current")
        if candidate.description_fingerprint != current.job_fingerprint:
            raise HTTPException(
                status_code=409, detail="The employer posting changed; review it first",
            )
        profile = tenant.profile()
        approved_before = tuple(
            sorted((f.fact_id, f.fact_type, f.value) for f in profile.approved_facts)
        )
        proposed = cover_letter_proposal(
            candidate, profile, language=payload.language,
        )
        # Do not return old approved facts after a deletion/approval change or
        # another tab's edit while a private proposal was being generated.
        latest = app.state.workspace_repository.get(pid, workspace_id)
        latest_profile = tenant.profile()
        approved_after = tuple(
            sorted((f.fact_id, f.fact_type, f.value) for f in latest_profile.approved_facts)
        )
        if (
            latest is None or latest.status != "draft"
            or latest.revision != payload.expected_revision
            or approved_after != approved_before
        ):
            raise HTTPException(
                status_code=409,
                detail="Draft or approved profile changed; reload and retry",
            )
        return JSONResponse(
            {
                "cover_letter": proposed,
                "language": payload.language,
                "workspace_revision": latest.revision,
                "review_required": True,
                "saved": False,
                "external_actions_performed": 0,
                "employer_contacts": 0,
            },
            headers={"Cache-Control": "private, no-store"},
        )

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

    def existing_employer_claim(binding: UserProfileBinding, workspace: Any) -> Any:
        """Read the immutable cross-source/owner claim before offering another packet.

        Called only after the request middleware bound a verified user. An
        unavailable database is not permission to assume no previous attempt.
        """
        ledger = app.state.employer_claims
        if ledger is None:
            raise HTTPException(
                status_code=503, detail="Durable employer attempt ledger is unavailable"
            )
        try:
            try:
                found = ledger.get_for_employer_url(binding, workspace.application_url)
            except EmployerSubmitClaimDenied:
                found = None  # Unsupported ATS: owner/canonical-key lookup only.
            return found or ledger.get(binding, workspace.canonical_key)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="Employer attempt status cannot be verified"
            ) from exc

    @app.get("/api/v1/application-workspaces/{workspace_id}/employer-attempt")
    def employer_attempt_status(workspace_id: str, request: Request) -> JSONResponse:
        """Read-only, signed-in OIDC posture. No browser-submit authority.

        Never serve this endpoint to anonymous/disabled-auth fixtures,
        unbound Access-only principals or an extension origin. No tokens,
        applicant documents, account IDs or employer URLs are returned.
        """
        tenant, binding = tenant_context(request)
        if (
            binding is None or not authentication.oidc_enabled
            or not request.cookies.get(SESSION_COOKIE_NAME)
        ):
            raise HTTPException(status_code=403, detail="Signed-in SmartPloy account required")
        if request.headers.get("Sec-Fetch-Site", "").casefold() not in {"", "same-origin", "none"}:
            raise HTTPException(status_code=403, detail="Use the SmartPloy website")
        origin = request.headers.get("Origin", "")
        if origin and origin != public_origin:
            raise HTTPException(status_code=403, detail="Use the SmartPloy website")
        if app.state.employer_claims is None:
            raise HTTPException(status_code=503, detail="Durable employer attempt ledger unavailable")
        workspace = app.state.workspace_repository.get(binding.profile_id, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        claim = existing_employer_claim(binding, workspace)
        return JSONResponse(
            {
                "previous_attempt_reserved": claim is not None,
                "state": claim.state if claim is not None else "not_reserved",
                "requires_human_reconciliation": claim is not None,
                "automatic_employer_submit_authorized": False,
                "external_confirmation_verified": False,
                "cross_device_server_claim_required": True,
            },
            headers={
                "Cache-Control": "private, no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

    def signed_in_employer_review(request: Request) -> UserProfileBinding:
        """Reuse verified OIDC identity and same-origin middleware, no CF fallback.

        A content-script or a different-origin page never receives a new
        browser authorization by presenting an arbitrary account header.
        """
        _, binding = tenant_context(request)
        if (
            binding is None or not authentication.oidc_enabled
            or not request.cookies.get(SESSION_COOKIE_NAME)
        ):
            raise HTTPException(status_code=403, detail="Signed-in SmartPloy session required")
        fetch_site = request.headers.get("Sec-Fetch-Site", "").casefold()
        if fetch_site not in {"", "same-origin", "none"}:
            raise HTTPException(status_code=403, detail="Use SmartPloy on the same origin")
        supplied_origin = request.headers.get("Origin", "")
        if supplied_origin and supplied_origin != public_origin:
            raise HTTPException(status_code=403, detail="Use SmartPloy on the same origin")
        return binding

    def _review_intent_repository() -> PostgresEmployerReviewIntentRepository:
        repo = app.state.employer_review_intents
        if repo is None:
            raise HTTPException(status_code=503, detail="Durable review state unavailable")
        return repo

    def _review_workspace(
        workspace_id: str, binding: UserProfileBinding,
    ) -> Any:
        workspace = app.state.workspace_repository.get(binding.profile_id, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        return workspace

    @app.get("/api/v1/application-workspaces/{workspace_id}/submit-review-intent")
    def read_employer_review_intent(workspace_id: str, request: Request) -> JSONResponse:
        binding = signed_in_employer_review(request)
        repo = _review_intent_repository()
        workspace = _review_workspace(workspace_id, binding)
        try:
            item = repo.get(binding, workspace.application_url)
        except EmployerReviewIntentDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Review state unavailable") from exc
        status = item.public_status(
            workspace_id=workspace_id, revision=workspace.revision
        ) if item else {
            "review_recorded": False, "review_state": "not_recorded",
            "expires_at": "", "automatic_employer_submit_authorized": False,
            "external_actions_performed": False, "browser_grant_issued": False,
        }
        return JSONResponse(
            status, headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"},
        )

    @app.post("/api/v1/application-workspaces/{workspace_id}/submit-review-intent")
    def record_employer_review_intent(
        workspace_id: str, payload: EmployerReviewIntentPayload, request: Request,
    ) -> JSONResponse:
        binding = signed_in_employer_review(request)
        if (
            request.headers.get("Origin", "") != public_origin
            or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
        ):
            raise HTTPException(status_code=403, detail="Verified same-origin account review required")
        if (
            payload.confirm_reviewed_application is not True
            or payload.acknowledge_manual_only is not True
        ):
            raise HTTPException(status_code=422, detail="Explicit final-review acknowledgement required")
        repo = _review_intent_repository()
        workspace = _review_workspace(workspace_id, binding)
        tenant, _ = tenant_context(request)
        if app.state.employer_claims is None:
            raise HTTPException(status_code=503, detail="Employer attempt ledger unavailable")
        if existing_employer_claim(binding, workspace) is not None:
            raise HTTPException(status_code=409, detail="A prior employer attempt requires reconciliation")
        if workspace.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="Application revision changed")
        try:
            packet = make_browser_packet(workspace, tenant.get_job(workspace.canonical_key), tenant.profile())
        except HandoffError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if (
            packet["document_sha256"] != payload.expected_document_sha256
            or packet["cv_pdf_sha256"] != payload.expected_cv_pdf_sha256
        ):
            raise HTTPException(status_code=409, detail="Reviewed CV/document hashes changed")
        try:
            item, fresh = repo.prepare(
                binding, workspace_id=workspace_id,
                expected_revision=workspace.revision,
                expected_application_url=workspace.application_url,
                expected_job_fingerprint=workspace.job_fingerprint,
                expected_document_sha256=packet["document_sha256"],
                expected_cv_pdf_sha256=packet["cv_pdf_sha256"],
                explicit_user_review=True, acknowledge_no_automatic_submit=True,
            )
        except EmployerReviewIntentDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Review persistence unavailable") from exc
        return JSONResponse(
            {
                **item.public_status(workspace_id=workspace_id, revision=workspace.revision),
                "new_review_recorded": fresh,
            },
            headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"},
        )

    @app.delete("/api/v1/application-workspaces/{workspace_id}/submit-review-intent")
    def cancel_employer_review_intent(workspace_id: str, request: Request) -> JSONResponse:
        binding = signed_in_employer_review(request)
        if (
            request.headers.get("Origin", "") != public_origin
            or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
        ):
            raise HTTPException(status_code=403, detail="Verified same-origin cancellation required")
        repo = _review_intent_repository()
        workspace = _review_workspace(workspace_id, binding)
        try:
            item = repo.cancel(binding, application_url=workspace.application_url)
        except EmployerReviewIntentDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Review cancellation unavailable") from exc
        return JSONResponse(
            {
                "review_recorded": False, "review_state": "cancelled" if item else "not_recorded",
                "expires_at": "", "automatic_employer_submit_authorized": False,
                "external_actions_performed": False, "browser_grant_issued": False,
            },
            headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"},
        )

    @app.get("/api/v1/application-workspaces/{workspace_id}/final-action-readiness")
    def final_action_readiness(workspace_id: str, request: Request) -> JSONResponse:
        """Private READ-ONLY source/rights posture. NEVER a browser click grant."""
        binding = signed_in_employer_review(request)
        workspace = _review_workspace(workspace_id, binding)
        rights_repo = app.state.employer_rights
        final_repo = app.state.employer_final_actions
        review_repo = app.state.employer_review_intents
        if (
            rights_repo is None or final_repo is None or review_repo is None
            or app.state.employer_claims is None
        ):
            raise HTTPException(
                status_code=503, detail="Durable employer-action policy unavailable"
            )
        try:
            policy = rights_repo.inspect(workspace.application_url)
            review = review_repo.get(binding, workspace.application_url)
            approval = final_repo.get(binding, workspace.application_url)
            claim = existing_employer_claim(binding, workspace)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="Employer action readiness unavailable"
            ) from exc
        reviewed = bool(
            review and review.public_status(
                workspace_id=workspace_id, revision=workspace.revision
            )["review_recorded"]
        )
        final_approved = bool(
            approval and approval.public_status(
                workspace_id=workspace_id, revision=workspace.revision
            )["approval_recorded"]
        )
        reasons: list[str] = []
        if not policy["operator_permission_reviewed"]:
            reasons.append("independent_employer_permission_missing")
        if not reviewed:
            reasons.append("current_applicant_review_missing")
        if not final_approved:
            reasons.append("separate_final_user_approval_missing")
        if claim is not None:
            reasons.append("previous_employer_attempt_requires_reconciliation")
        if not app.state.browser_final_enabled:
            reasons.append("reviewed_browser_submit_disabled_in_production")
        return JSONResponse(
            {
                "operator_permission_reviewed": policy["operator_permission_reviewed"],
                "current_applicant_review_recorded": reviewed,
                "separate_final_user_approval_recorded": final_approved,
                "previous_employer_attempt_reserved": claim is not None,
                "trusted_one_use_browser_redemption_available": app.state.browser_final_enabled,
                "final_browser_click_authorized": False,
                "employer_submission_performed": False,
                "employer_receipt_verified": False,
                "blockers": reasons,
            },
            headers={
                "Cache-Control": "private, no-store",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
            },
        )

    def _partner_ready(
        workspace_id: str, request: Request, *, provider: str,
    ) -> tuple[UserProfileBinding, Any, Any, dict[str, object]]:
        """One read-only applicant review/rights contract; provider scopes stay isolated."""
        if provider not in {"lever", "ashby"}:
            raise HTTPException(status_code=409, detail="Unsupported provider")
        binding = signed_in_employer_review(request)
        workspace = _review_workspace(workspace_id, binding)
        receipts = (
            app.state.partner_ashby_receipts if provider == "ashby"
            else app.state.partner_lever_receipts
        )
        if (
            app.state.employer_final_actions is None
            or app.state.employer_review_intents is None
            or app.state.employer_rights is None
            or app.state.employer_claims is None or receipts is None
        ):
            raise HTTPException(status_code=503, detail="Durable partner submission unavailable")
        tenant, _ = tenant_context(request)
        registry = (
            app.state.partner_ashby_registry if provider == "ashby"
            else app.state.partner_lever_registry
        )
        config = registry.public_readiness(workspace.application_url)
        scope = ASHBY_API_ACTION if provider == "ashby" else LEVER_API_ACTION
        try:
            rights = app.state.employer_rights.inspect(
                workspace.application_url, action_scope=scope
            )
            review = app.state.employer_review_intents.get(binding, workspace.application_url)
            receipt = receipts.get(binding, workspace.application_url, provider=provider)
            prior = existing_employer_claim(binding, workspace)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="Partner-readiness lookup unavailable"
            ) from exc
        reviewed = bool(
            review and review.public_status(
                workspace_id=workspace_id, revision=workspace.revision
            )["review_recorded"]
        )
        packet = None
        try:
            packet = make_browser_packet(
                workspace, tenant.get_job(workspace.canonical_key), tenant.profile()
            )
        except HandoffError:
            pass
        current = packet is not None
        authorized = bool(
            config["partner_api_configured"] and rights["operator_permission_reviewed"]
            and current and receipt is None and prior is None
        )
        review_evidence = {
            "workspace_id": packet["workspace_id"],
            "revision": packet["revision"],
            "document_sha256": packet["document_sha256"],
            "cv_pdf_sha256": packet["cv_pdf_sha256"],
            "approved_fields_sha256": packet["approved_fields_sha256"],
            "cv_pdf_size": packet["cv_pdf_size"],
            "expires_at": packet["expires_at"],
        } if authorized and packet is not None else None
        return binding, workspace, tenant, {
            "partner_provider": provider,
            "partner_api_configured": config["partner_api_configured"],
            "independent_partner_rights_reviewed": rights["operator_permission_reviewed"],
            "current_applicant_review_recorded": reviewed,
            "current_document_and_posting_ready": current,
            "prior_employer_attempt": prior is not None,
            "provider_acknowledged": receipt is not None,
            "eligible_for_explicit_partner_submit": bool(authorized and reviewed),
            "review_evidence": review_evidence,
            "review_evidence_is_authorization": False,
            "unattended_auto_apply_enabled": False,
            "automatic_retry_authorized": False,
        }

    def _partner_lever_ready(
        workspace_id: str, request: Request,
    ) -> tuple[UserProfileBinding, Any, Any, dict[str, object]]:
        return _partner_ready(workspace_id, request, provider="lever")

    @app.post("/api/v1/application-workspaces/{workspace_id}/browser-final-attempt")
    def reserve_verified_browser_final_attempt(
        workspace_id: str, payload: BrowserFinalAttemptPayload, request: Request,
    ) -> JSONResponse:
        """Burn exactly one employer attempt before any browser final click.

        Only invoked from the signed-in first-party tab via the user-operated
        companion. A claim is NOT a sent application or a bearer capability;
        browser execution is a separate, explicit user click with a local
        no-retry lock. This route makes NO outbound employer HTTP request.
        """
        if not app.state.browser_final_enabled:
            raise HTTPException(status_code=403, detail="Reviewed employer browser submit is not enabled")
        binding = signed_in_employer_review(request)
        if (
            request.headers.get("Origin", "") != public_origin
            or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
        ):
            raise HTTPException(status_code=403, detail="Same-origin verified applicant required")
        if (
            payload.confirm_one_job_final_click is not True
            or payload.acknowledge_external_employer_transfer is not True
            or payload.acknowledge_no_automatic_retry is not True
        ):
            raise HTTPException(status_code=422, detail="Fresh final-click approval and single-attempt acknowledgment required")
        if (
            app.state.employer_final_actions is None
            or app.state.employer_claims is None
            or app.state.employer_rights is None
            or app.state.employer_review_intents is None
        ):
            raise HTTPException(status_code=503, detail="Durable final-action authorization unavailable")
        workspace = _review_workspace(workspace_id, binding)
        if workspace.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="Reviewed application revision changed")
        if existing_employer_claim(binding, workspace) is not None:
            raise HTTPException(status_code=409, detail="Prior employer attempt requires reconciliation")
        tenant, _ = tenant_context(request)
        try:
            packet = make_browser_packet(
                workspace, tenant.get_job(workspace.canonical_key), tenant.profile()
            )
        except HandoffError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if (
            packet["document_sha256"] != payload.expected_document_sha256
            or packet["cv_pdf_sha256"] != payload.expected_cv_pdf_sha256
            or packet["cv_pdf_size"] != payload.expected_cv_pdf_size
            or packet["approved_fields_sha256"] != payload.expected_fields_sha256
            or sha256(packet["application_url"].encode("utf-8")).hexdigest()
               != payload.expected_application_url_sha256
        ):
            raise HTTPException(status_code=409, detail="Reviewed employer, CV PDF or approved fields changed")
        # Both calls reuse original SP15e atomic permission/review/claim gates,
        # including independent two-person rights and sticky cross-device DB
        # uniqueness. Even if this process crashes, a committed reservation
        # cannot silently become a second application.
        try:
            approval, _ = app.state.employer_final_actions.approve(
                binding, workspace_id=workspace_id,
                expected_revision=workspace.revision,
                expected_application_url=workspace.application_url,
                expected_job_fingerprint=workspace.job_fingerprint,
                expected_document_sha256=packet["document_sha256"],
                expected_cv_pdf_sha256=packet["cv_pdf_sha256"],
                expected_fields_sha256=payload.expected_fields_sha256,
                explicit_final_user_approval=True,
                acknowledge_external_employer_transfer=True,
                action_scope=ACTION,
            )
            reserved = app.state.employer_final_actions.consume_once_for_trusted_adapter(
                binding, approval_id=approval.approval_id,
                workspace_id=workspace_id, expected_revision=workspace.revision,
                expected_application_url=workspace.application_url,
                expected_job_fingerprint=workspace.job_fingerprint,
                expected_document_sha256=packet["document_sha256"],
                expected_cv_pdf_sha256=packet["cv_pdf_sha256"],
                expected_fields_sha256=payload.expected_fields_sha256,
                action_scope=ACTION,
            )
        except EmployerFinalActionDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Final employer claim unavailable; check attempt status before any retry") from exc
        return JSONResponse(
            {
                "claim_reserved": True,
                "claim_id": reserved.claim.claim_id,
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat(),
                "external_actions_performed": False,
                "provider_acknowledged": False,
                "automatic_retry_authorized": False,
                "one_job_browser_click_permitted": True,
            },
            headers={
                "Cache-Control": "private, no-store",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/v1/application-workspaces/{workspace_id}/partner-lever-readiness")
    def partner_lever_readiness(workspace_id: str, request: Request) -> JSONResponse:
        _, _, _, readiness = _partner_lever_ready(workspace_id, request)
        return JSONResponse(
            readiness,
            headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.get("/api/v1/application-workspaces/{workspace_id}/partner-lever-receipt")
    def partner_lever_receipt(workspace_id: str, request: Request) -> JSONResponse:
        binding = signed_in_employer_review(request)
        workspace = _review_workspace(workspace_id, binding)
        if app.state.partner_lever_receipts is None:
            raise HTTPException(status_code=503, detail="Provider receipt storage unavailable")
        try:
            receipt = app.state.partner_lever_receipts.get(binding, workspace.application_url)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Provider receipt unavailable") from exc
        return JSONResponse(
            {"present": receipt is not None,
             "receipt": receipt.public_status() if receipt else None},
            headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.post("/api/v1/application-workspaces/{workspace_id}/partner-lever-apply")
    def submit_to_authorized_lever_partner(
        workspace_id: str, payload: LeverPartnerApplicationPayload, request: Request,
    ) -> JSONResponse:
        """The only supported REAL submission endpoint, gated by partner key.

        Never invokes this endpoint from background jobs or the Chrome
        companion. The actual user must deliberately click and confirm a
        reviewed application on the signed-in SmartPloy first-party origin.
        """
        binding = signed_in_employer_review(request)
        if (
            request.headers.get("Origin", "") != public_origin
            or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
        ):
            raise HTTPException(status_code=403, detail="Same-origin verified applicant required")
        if (
            payload.explicit_final_user_approval is not True
            or payload.approve_employer_data_transfer is not True
            or payload.affirm_reviewed_employer_form is not True
        ):
            raise HTTPException(status_code=422, detail="Fresh explicit user review and transfer consent required")
        binding, workspace, tenant, readiness = _partner_lever_ready(workspace_id, request)
        if not readiness["eligible_for_explicit_partner_submit"]:
            raise HTTPException(
                status_code=409,
                detail="The employer lacks reviewed partner rights, current CV review or has an existing attempt",
            )
        if payload.expected_revision != workspace.revision:
            raise HTTPException(status_code=409, detail="Saved application revision changed")
        try:
            posting = app.state.partner_lever_registry.match(workspace.application_url)
            packet = make_browser_packet(
                workspace, tenant.get_job(workspace.canonical_key), tenant.profile()
            )
            cv_pdf, _, _ = render_document(workspace, kind="cv", file_format="pdf")
        except (LeverPartnerUnavailable, HandoffError, WorkspaceError) as exc:
            raise HTTPException(status_code=409, detail="Approved partner packet unavailable") from exc
        if (
            packet["document_sha256"] != payload.expected_document_sha256
            or packet["cv_pdf_sha256"] != payload.expected_cv_pdf_sha256
            or packet["cv_pdf_size"] != payload.expected_cv_pdf_size
            or approved_fields_sha256(packet["fields"]) != payload.expected_fields_sha256
            or sha256(cv_pdf).hexdigest() != payload.expected_cv_pdf_sha256
        ):
            raise HTTPException(status_code=409, detail="Approved PDF, contact or job snapshot drifted")
        try:
            approval, _ = app.state.employer_final_actions.approve(
                binding,workspace_id=workspace_id,
                expected_revision=workspace.revision,
                expected_application_url=workspace.application_url,
                expected_job_fingerprint=workspace.job_fingerprint,
                expected_document_sha256=packet["document_sha256"],
                expected_cv_pdf_sha256=packet["cv_pdf_sha256"],
                expected_fields_sha256=payload.expected_fields_sha256,
                explicit_final_user_approval=True,
                acknowledge_external_employer_transfer=True,
                action_scope=LEVER_API_ACTION,
            )
            reserved = app.state.employer_final_actions.consume_once_for_trusted_adapter(
                binding,approval_id=approval.approval_id,workspace_id=workspace_id,
                expected_revision=workspace.revision,
                expected_application_url=workspace.application_url,
                expected_job_fingerprint=workspace.job_fingerprint,
                expected_document_sha256=packet["document_sha256"],
                expected_cv_pdf_sha256=packet["cv_pdf_sha256"],
                expected_fields_sha256=payload.expected_fields_sha256,
                action_scope=LEVER_API_ACTION,
            )
        except EmployerFinalActionDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Final submission reservation unavailable") from exc
        # Sticky attempt COMMITTED before any external request; another device
        # can never POST the same employer job, even on timeout or crash.
        try:
            ack = app.state.partner_lever_transport.send(
                posting,application_url=workspace.application_url,
                fields=packet["fields"],pdf=cv_pdf,
            )
        except LeverPartnerUncertain as exc:
            try:
                app.state.employer_claims.mark_uncertain(
                    binding,reserved.claim.claim_id,code=exc.code
                )
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail="Employer outcome uncertain and claim retained; operator review required",
                ) from None
            return JSONResponse(
                {
                    "state":"outcome_uncertain","provider_acknowledged":False,
                    "automatic_retry_authorized":False,
                    "employer_hiring_decision_verified":False,
                    "requires_human_reconciliation":True,
                },status_code=202,headers={"Cache-Control":"private, no-store"},
            )
        except Exception:
            # Unanticipated transport error after the durable reservation:
            # NEVER try the external call again. No secrets in client detail.
            raise HTTPException(
                status_code=503,
                detail="Employer outcome cannot be confirmed; reserved attempt requires reconciliation",
            ) from None
        try:
            confirmed = app.state.partner_lever_receipts.record(
                binding,reserved.claim,ack
            )
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Lever may have acknowledged the application but local receipt is unavailable",
            ) from None
        return JSONResponse(
            {
                "state":"provider_acknowledged",
                **confirmed.public_status(),
                "external_actions_performed":True,
            },
            headers={"Cache-Control":"private, no-store", "Referrer-Policy":"no-referrer"},
        )

    @app.post("/api/v1/application-workspaces/{workspace_id}/verify-reviewed-packet")
    def verify_reviewed_packet_for_companion(
        workspace_id: str, payload: BrowserReviewVerificationPayload, request: Request,
    ) -> JSONResponse:
        """Signed-in SmartPloy origin checks approved document before assisted fill.

        This response is NON-BEARER, non-transferrable and never a grant to
        submit to an employer. Site cookie and account ID stay within SmartPloy.
        There is no CORS/extension endpoint or final browser action.
        """
        binding = signed_in_employer_review(request)
        if (
            request.headers.get("Origin", "") != public_origin
            or request.headers.get("X-Smartploy-Expected-User-Id", "") != binding.user_id
        ):
            raise HTTPException(status_code=403, detail="Signed-in same-origin review required")
        repo = _review_intent_repository()
        workspace = _review_workspace(workspace_id, binding)
        if app.state.employer_claims is None:
            raise HTTPException(status_code=503, detail="Employer attempt ledger unavailable")
        if workspace.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="Application revision changed")
        if existing_employer_claim(binding, workspace) is not None:
            raise HTTPException(status_code=409, detail="Prior attempt requires reconciliation")
        tenant, _ = tenant_context(request)
        try:
            packet = make_browser_packet(
                workspace, tenant.get_job(workspace.canonical_key), tenant.profile()
            )
        except HandoffError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if (
            packet["document_sha256"] != payload.expected_document_sha256
            or packet["cv_pdf_sha256"] != payload.expected_cv_pdf_sha256
            or packet["cv_pdf_size"] != payload.expected_cv_pdf_size
            or approved_fields_sha256(packet["fields"]) != payload.expected_fields_sha256
            or sha256(packet["application_url"].encode("utf-8")).hexdigest()
               != payload.expected_application_url_sha256
        ):
            raise HTTPException(status_code=409, detail="Reviewed packet fields, job or PDF changed")
        try:
            item = repo.verify_for_companion(
                binding, workspace_id=workspace_id,
                expected_revision=payload.expected_revision,
                expected_application_url=workspace.application_url,
                expected_job_fingerprint=workspace.job_fingerprint,
                expected_document_sha256=packet["document_sha256"],
                expected_cv_pdf_sha256=packet["cv_pdf_sha256"],
            )
        except EmployerReviewIntentDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Review verification unavailable") from exc
        return JSONResponse(
            {
                "review_verified": True,
                "review_state": "pending",
                "expires_at": item.expires_at.isoformat(),
                "automatic_employer_submit_authorized": False,
                "external_actions_performed": False,
                "browser_grant_issued": False,
            },
            headers={
                "Cache-Control": "private, no-store",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/v1/application-workspaces/{workspace_id}/handoff-readiness")
    def browser_handoff_readiness(workspace_id: str, request: Request) -> dict[str, Any]:
        tenant, binding = tenant_context(request)
        item = app.state.workspace_repository.get(tenant.profile_repository.profile_id, workspace_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        # Keep human-reviewed autofill but never issue a fresh packet once
        # this signed-in account's employer job has a durable attempt.
        claim = existing_employer_claim(binding, item) if binding else None
        job = tenant.get_job(item.canonical_key)
        result = review_handoff(item, job, tenant.profile())
        if claim is not None:
            result["ready"] = False
            result["blockers"].append(
                "This employer job already has an attempt reserved across devices. "
                "Reconcile its outcome before any new application."
            )
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
        tenant, binding = tenant_context(request)
        item = app.state.workspace_repository.get(tenant.profile_repository.profile_id, workspace_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Application workspace not found")
        if binding and existing_employer_claim(binding, item) is not None:
            raise HTTPException(
                status_code=409,
                detail="This employer job already has a reserved attempt. Do not retry.",
            )
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
        if payload.acknowledge_obumai_processing is not True:
            raise HTTPException(
                status_code=422,
                detail="Explicit per-job consent for ObumAI processing is required",
            )
        if payload.action not in SELF_SERVICE_OBUMAI_ACTIONS:
            raise HTTPException(
                status_code=422,
                detail="Only approved SmartPloy reasoning or document-draft actions are allowed",
            )
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

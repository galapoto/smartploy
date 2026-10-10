"""Smartploy FastAPI service."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from .access import (
    AccessPrincipal,
    AccessSettings,
    CloudflareAccessMiddleware,
    CloudflareAccessVerifier,
)
from .application_storage import MemoryApplicationRepository, PostgresApplicationRepository
from .artifact_storage import MemoryArtifactRepository, PostgresArtifactRepository
from .domain import JobSearchFilters, SourceObservation, SourcePolicy
from .obumai import ObumAIClient, ObumAIError, ObumAISettings
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
        artifact_repository = PostgresArtifactRepository(dsn)
    else:
        repository = MemoryJobRepository()
        profile_repository = MemoryProfileRepository(profile_id=profile_id)
        preparation_repository = MemoryPreparationRepository()
        application_repository = MemoryApplicationRepository()
        artifact_repository = MemoryArtifactRepository()

    service = SmartployService(
        repository=repository,
        profile_repository=profile_repository,
        preparation_repository=preparation_repository,
        application_repository=application_repository,
        artifact_repository=artifact_repository,
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
) -> FastAPI:
    active = service or _build_service()
    access_settings = AccessSettings.from_env()
    app = FastAPI(title="Smartploy API", version="0.5.0")
    allowed_hosts = _allowed_hosts()
    if allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.add_middleware(
        CloudflareAccessMiddleware,
        settings=access_settings,
        verifier=access_verifier,
    )
    app.state.smartploy = active
    app.state.public_origin = _public_origin()
    app.state.access_settings = access_settings

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

    @app.get("/api/v1/session")
    def session(request: Request) -> dict[str, Any]:
        principal = getattr(request.state, "smartploy_principal", None)
        if isinstance(principal, AccessPrincipal):
            return principal.public_dict()
        return {
            "authenticated": False,
            "email": "",
            "subject_fingerprint": "",
            "auth_source": "none",
        }

    @app.get("/api/v1/profile/status")
    def profile_status() -> dict[str, Any]:
        return active.profile_summary()

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
    def rankings() -> dict[str, Any]:
        items = [item.to_dict() for item in active.rankings()]
        return {"rankings": items, "count": len(items)}

    @app.get("/api/v1/jobs/{canonical_key}/score")
    def score_job(canonical_key: str) -> dict[str, Any]:
        try:
            return active.score_job(canonical_key).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @app.post("/api/v1/jobs/{canonical_key}/prepare")
    def prepare_job(canonical_key: str) -> dict[str, Any]:
        try:
            return active.prepare_job(canonical_key).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except PreparationNotEligible as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/applications/summary")
    def application_summary() -> dict[str, Any]:
        return active.application_summary()

    @app.get("/api/v1/applications")
    def list_applications(limit: int = 100) -> dict[str, Any]:
        bounded = max(1, min(limit, 500))
        items = []
        for application in active.list_applications(limit=bounded):
            value = application.to_dict()
            value["artifacts"] = [
                artifact.to_dict()
                for artifact in active.list_artifacts(application.package_id)
            ]
            items.append(value)
        return {"applications": items, "count": len(items)}

    @app.get("/api/v1/applications/{application_id}/events")
    def application_events(application_id: str, limit: int = 500) -> dict[str, Any]:
        item = active.get_application(application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="application not found")
        bounded = max(1, min(limit, 2000))
        events = [event.to_dict() for event in active.application_events(application_id, limit=bounded)]
        return {"events": events, "count": len(events)}

    @app.get("/api/v1/applications/{application_id}")
    def get_application(application_id: str) -> dict[str, Any]:
        item = active.get_application(application_id)
        if item is None:
            raise HTTPException(status_code=404, detail="application not found")
        return item.to_dict()

    @app.get("/api/v1/worker/tasks")
    def worker_tasks() -> dict[str, Any]:
        return _worker_snapshot()

    @app.get("/api/v1/dashboard")
    def dashboard() -> dict[str, Any]:
        return {
            **active.dashboard(),
            "worker": _worker_snapshot(),
        }

    @app.get("/api/v1/preparations")
    def list_preparations(limit: int = 100) -> dict[str, Any]:
        bounded = max(1, min(limit, 500))
        items = [item.to_dict() for item in active.list_preparations(limit=bounded)]
        return {"preparations": items, "count": len(items)}

    @app.get("/api/v1/preparations/{package_id}")
    def get_preparation(package_id: str) -> dict[str, Any]:
        item = active.get_preparation(package_id)
        if item is None:
            raise HTTPException(status_code=404, detail="preparation not found")
        return item.to_dict()

    @app.get("/api/v1/preparations/{package_id}/artifacts")
    def preparation_artifacts(package_id: str) -> dict[str, Any]:
        if active.get_preparation(package_id) is None:
            raise HTTPException(status_code=404, detail="preparation not found")
        items = [item.to_dict() for item in active.list_artifacts(package_id)]
        return {"artifacts": items, "count": len(items)}

    @app.get("/api/v1/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str) -> dict[str, Any]:
        item = active.get_artifact(artifact_id)
        if item is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return item.to_dict()

    @app.get("/api/v1/artifacts/{artifact_id}/download")
    def download_artifact(artifact_id: str) -> Response:
        item = active.get_artifact(artifact_id)
        if item is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        value = item.normalized()
        return Response(
            content=value.content,
            media_type=value.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{value.filename}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    @app.post("/api/v1/preparations/{package_id}/refresh")
    def refresh_preparation(package_id: str) -> dict[str, Any]:
        try:
            return active.refresh_preparation(package_id).to_dict()
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
    def submit_obumai(canonical_key: str, payload: ObumAITaskPayload) -> dict[str, Any]:
        try:
            return active.submit_obumai(
                canonical_key,
                action=payload.action,
                instructions=payload.instructions,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/obumai/jobs/{job_id}")
    def get_obumai_job(job_id: str) -> dict[str, Any]:
        if active.obumai is None:
            raise HTTPException(status_code=503, detail="ObumAI integration is not configured")
        try:
            return active.obumai.get_job(job_id)
        except ObumAIError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/obumai/jobs/{job_id}/events")
    def get_obumai_events(job_id: str, after_sequence: int = 0) -> dict[str, Any]:
        if active.obumai is None:
            raise HTTPException(status_code=503, detail="ObumAI integration is not configured")
        try:
            return active.obumai.get_events(job_id, after_sequence=after_sequence)
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

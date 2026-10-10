"""Smartploy FastAPI service."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from .domain import JobSearchFilters, SourceObservation, SourcePolicy
from .obumai import ObumAIClient, ObumAIError, ObumAISettings
from .profile_storage import MemoryProfileRepository, PostgresProfileRepository
from .service import SmartployService
from .storage import MemoryJobRepository, PostgresJobRepository


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


class ObumAITaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=64)
    instructions: str = Field(default="", max_length=20_000)


def _build_service() -> SmartployService:
    obum_settings = ObumAISettings.from_env()
    client = ObumAIClient(obum_settings) if obum_settings else None

    dsn = os.getenv("SMARTPLOY_DATABASE_URL", "").strip()
    profile_id = os.getenv("SMARTPLOY_PROFILE_ID", "default").strip() or "default"
    if dsn:
        repository = PostgresJobRepository(dsn)
        profile_repository = PostgresProfileRepository(dsn, profile_id=profile_id)
    else:
        repository = MemoryJobRepository()
        profile_repository = MemoryProfileRepository(profile_id=profile_id)

    service = SmartployService(
        repository=repository,
        profile_repository=profile_repository,
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


def create_app(service: SmartployService | None = None) -> FastAPI:
    active = service or _build_service()
    app = FastAPI(title="Smartploy API", version="0.3.0")
    app.state.smartploy = active

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        storage = active.storage_status()
        return {
            "ok": bool(storage.get("ready")),
            "service": "smartploy",
            "storage": storage,
            "profile": active.profile_summary(),
            "obumai_configured": active.obumai is not None,
            "external_actions_authorized": False,
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

"""Environment-driven continuous Smartploy worker task registry."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os

from .application_storage import PostgresApplicationRepository
from .auto_application_queue import per_profile_draft_lock, prepare_matching_application_drafts
from .cv_storage import PostgresCVRepository
from .employer_submit_claim_storage import PostgresEmployerSubmitClaimRepository
from .identity import PostgresIdentityRepository
from .application_workspace_storage import PostgresWorkspaceRepository
from .search_preference_storage import PostgresSearchPreferenceRepository
from .obumai import ObumAIClient, ObumAIError, ObumAISettings
from .preparation_storage import PostgresPreparationRepository, REFRESHABLE_PREPARATION_STATES
from .profile_storage import PostgresProfileRepository
from .service import SmartployService
from .sources.jobmarket_finland import (
    JobMarketFinlandAdapter,
    JobMarketFinlandSettings,
    compute_modified_window,
)
from .sources.jobmarket_finland_polling import poll_jobmarket_finland
from .sources.kuntarekry import KuntarekryFeedAdapter, KuntarekryFeedSettings
from .sources.polling import poll_feed
from .sources.public_ats import (
    PublicATSRuntimeSettings,
    build_public_ats_adapter,
    load_public_ats_sources,
)
from .sources.public_ats_polling import poll_public_ats
from .storage import PostgresJobRepository
from .worker_schedule import WorkerTaskResult, WorkerTaskSpec


ACTIVE_PREPARATION_STATES = REFRESHABLE_PREPARATION_STATES


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    if maximum is not None:
        value = min(value, maximum)
    return value


def _auto_prepare_opt_in() -> bool:
    """Never infer user permission from ObumAI service configuration.

    A worker capable of polling existing preparation statuses is not
    automatically authorized to forward profile data to ObumAI. Only the
    literal operator opt-in "true" registers an unattended submitter.
    This operator switch is NOT per-user consent; multi-user operators
    must keep the flag off until a scoped consent record is implemented.
    """
    raw = os.getenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "false").strip().casefold()
    if raw not in {"true", "false"}:
        raise ValueError(
            "SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED must be literal true or false"
        )
    if raw == "true":
        # A global operator switch cannot establish revocable consent from
        # individual account holders. Legacy auto-prep is restricted to
        # explicitly configured nonproduction fixtures until a tenant-scoped,
        # per-job consent ledger is enforced at every dispatch/retry.
        environment = os.getenv("SMARTPLOY_ENVIRONMENT", "production").strip().casefold()
        if environment not in {"development", "test"}:
            raise ValueError(
                "Unattended ObumAI preparation is unavailable in production "
                "without per-account processing consent"
            )
    return raw == "true"


def _job_service(dsn: str) -> SmartployService:
    return SmartployService(repository=PostgresJobRepository(dsn))


def _scoped_application_service(
    dsn: str, obumai: ObumAIClient, profile_id: str,
) -> SmartployService:
    """Always scope ALL private preparation/application repositories together."""
    owner = str(profile_id or "").strip()
    if not owner:
        raise ValueError("An explicit preparation owner profile is required")
    return SmartployService(
        repository=PostgresJobRepository(dsn),
        profile_repository=PostgresProfileRepository(dsn, profile_id=owner),
        preparation_repository=PostgresPreparationRepository(dsn, profile_id=owner),
        application_repository=PostgresApplicationRepository(dsn, profile_id=owner),
        obumai=obumai,
    )


def _application_service(dsn: str, settings: ObumAISettings) -> SmartployService:
    """Legacy single-profile submitter, allowed only in synthetic test/dev."""
    profile_id = os.getenv("SMARTPLOY_PROFILE_ID", "default").strip() or "default"
    return _scoped_application_service(dsn, ObumAIClient(settings), profile_id)


def build_worker_task_specs(dsn: str) -> list[WorkerTaskSpec]:
    dsn = str(dsn or "").strip()
    if not dsn:
        raise ValueError("SMARTPLOY_DATABASE_URL is required for continuous worker tasks")

    specs: list[WorkerTaskSpec] = []

    kuntarekry = KuntarekryFeedSettings.from_env()
    if kuntarekry is not None:
        cadence = _positive_int("SMARTPLOY_WORKER_KUNTAREKRY_CADENCE_SECONDS", 600)

        def run_kuntarekry(settings=kuntarekry) -> WorkerTaskResult:
            service = _job_service(dsn)
            adapter = KuntarekryFeedAdapter(settings)
            try:
                summary = poll_feed(service, adapter)
            finally:
                adapter.close()
            return WorkerTaskResult(
                status=summary.status,
                details=summary.to_dict(),
                error=summary.error,
            )

        specs.append(
            WorkerTaskSpec(
                task_id="source:kuntarekry",
                task_kind="source",
                cadence_seconds=cadence,
                runner=run_kuntarekry,
                metadata={"source_id": "kuntarekry", "provider": "kuntarekry"},
            )
        )

    jobmarket = JobMarketFinlandSettings.from_env()
    if jobmarket is not None:
        cadence = _positive_int("SMARTPLOY_WORKER_JOBMARKET_CADENCE_SECONDS", 300)

        def run_jobmarket(settings=jobmarket) -> WorkerTaskResult:
            repository = PostgresJobRepository(dsn)
            health = repository.get_source_health("job-market-finland")
            modified_from, modified_to = compute_modified_window(
                last_success_at=health.last_success_at if health else "",
                now=datetime.now(timezone.utc),
                initial_lookback_minutes=settings.initial_lookback_minutes,
                overlap_minutes=settings.overlap_minutes,
            )
            service = SmartployService(repository=repository)
            adapter = JobMarketFinlandAdapter(settings)
            try:
                summary = poll_jobmarket_finland(
                    service,
                    adapter,
                    modified_from=modified_from,
                    modified_to=modified_to,
                )
            finally:
                adapter.close()
            return WorkerTaskResult(
                status=summary.status,
                details=summary.to_dict(),
                error=summary.error,
            )

        specs.append(
            WorkerTaskSpec(
                task_id="source:job-market-finland",
                task_kind="source",
                cadence_seconds=cadence,
                runner=run_jobmarket,
                metadata={
                    "source_id": "job-market-finland",
                    "provider": "job-market-finland",
                    "environment": jobmarket.environment,
                },
            )
        )

    ats_runtime = PublicATSRuntimeSettings.from_env()
    ats_cadence = _positive_int("SMARTPLOY_WORKER_PUBLIC_ATS_CADENCE_SECONDS", 600)
    for config in load_public_ats_sources():

        def run_ats(source_config=config) -> WorkerTaskResult:
            service = _job_service(dsn)
            adapter = build_public_ats_adapter(source_config, ats_runtime)
            try:
                summary = poll_public_ats(service, adapter)
            finally:
                adapter.close()
            return WorkerTaskResult(
                status=summary.status,
                details=summary.to_dict(),
                error=summary.error,
            )

        specs.append(
            WorkerTaskSpec(
                task_id=f"source:{config.source_id}",
                task_kind="source",
                cadence_seconds=ats_cadence,
                runner=run_ats,
                metadata={
                    "source_id": config.source_id,
                    "provider": config.provider,
                    "tenant": config.tenant,
                    "stack": config.stack,
                    "employer_sector": config.employer_sector,
                    "external_ai_forwarding_allowed": config.external_ai_forwarding_allowed,
                    "location_terms": list(config.location_terms),
                },
            )
        )

    # The already running scheduled SOURCE worker can now turn current
    # personalized matches into private, review-only application drafts.
    # This flag enables only the LOCAL scheduler, NOT consent or employer
    # authority: each active profile MUST opt in in private search settings.
    local_flag = os.getenv("SMARTPLOY_WORKER_LOCAL_AUTO_DRAFT_ENABLED","false").strip().casefold()
    if local_flag not in {"true","false"}:
        raise ValueError("SMARTPLOY_WORKER_LOCAL_AUTO_DRAFT_ENABLED must be literal true or false")
    if local_flag == "true":
        cadence = _positive_int(
            "SMARTPLOY_WORKER_LOCAL_AUTO_DRAFT_CADENCE_SECONDS",600,maximum=86400
        )

        def run_local_auto_drafts() -> WorkerTaskResult:
            identity_repo = PostgresIdentityRepository(dsn)
            search_repo = PostgresSearchPreferenceRepository(dsn)
            job_repo = PostgresJobRepository(dsn)
            cv_repo = PostgresCVRepository(dsn)
            workspace_repo = PostgresWorkspaceRepository(dsn)
            claim_repo = PostgresEmployerSubmitClaimRepository(dsn)
            # Reuse the already polled jobs. NO new web scraping, AI calls,
            # employer API operations or applicant data forwarding.
            jobs = job_repo.values()
            inspected = 0
            created = 0
            failures = 0
            for user_id,profile_id in search_repo.list_auto_draft_profiles(limit=50):
                inspected += 1
                try:
                    binding = identity_repo.get(user_id)
                    if (
                        binding is None or binding.status != "active"
                        or binding.profile_id != profile_id
                    ):
                        continue
                    # A fresh read immediately before queueing also respects
                    # settings revocation and general-mode switch.
                    preferences = search_repo.get(profile_id)
                    if not preferences.auto_drafts_enabled or preferences.mode != "personalized":
                        continue
                    profile = PostgresProfileRepository(
                        dsn,profile_id=profile_id
                    ).profile()
                    cv = cv_repo.get(profile_id)

                    def claimed(candidate, owner=binding):
                        if claim_repo.get(owner,candidate.canonical_key):
                            return True
                        from urllib.parse import urlsplit
                        host = urlsplit(candidate.job.application_url).hostname or ""
                        return host in {"jobs.lever.co","jobs.eu.lever.co"} and bool(
                            claim_repo.get_for_employer_url(
                                owner,candidate.job.application_url
                            )
                        )

                    with per_profile_draft_lock(dsn,profile_id):
                        latest=search_repo.get(profile_id)
                        if not latest.auto_drafts_enabled or latest.mode != "personalized":
                            continue
                        result = prepare_matching_application_drafts(
                            profile=profile,preferences=latest,
                            candidates=jobs,workspace_repository=workspace_repo,
                            cv_text=cv.text if cv else "",
                            cv_sha256=cv.digest if cv else "",
                            previous_attempt=claimed,
                        )
                        created += len(result.created)
                except Exception:
                    # No account data, CV text, job link, exception body or
                    # employer keys ever leave the local worker in task logs.
                    failures += 1
            return WorkerTaskResult(
                status="degraded" if failures else "healthy",
                details={
                    "opted_in_accounts_checked":inspected,
                    "private_drafts_created":created,
                    "failures":failures,
                    "external_actions_authorized":False,
                    "external_ai_forwarding_performed":False,
                    "employer_submissions":0,
                },
            )

        specs.append(WorkerTaskSpec(
            task_id="application:auto-draft-matches",
            task_kind="application_prepare",
            cadence_seconds=cadence,
            runner=run_local_auto_drafts,
            metadata={
                "per_account_opt_in_required":True,
                "external_actions_authorized":False,
                "external_ai_forwarding_performed":False,
            },
        ))

    auto_prepare_enabled = _auto_prepare_opt_in()
    obum_settings = ObumAISettings.from_env()
    if auto_prepare_enabled and obum_settings is None:
        raise ValueError(
            "Unattended ObumAI preparation cannot be enabled without ObumAI configuration"
        )
    if obum_settings is not None:
        refresh_cadence = _positive_int("SMARTPLOY_WORKER_REFRESH_CADENCE_SECONDS", 60)

        def run_prepare(settings=obum_settings) -> WorkerTaskResult:
            service = _application_service(dsn, settings)
            try:
                limit = _positive_int("SMARTPLOY_PREPARE_BATCH_LIMIT", 20, maximum=100)
                packages = service.prepare_eligible(limit=limit)
                counts = Counter(item.status for item in packages)
                return WorkerTaskResult(
                    status="healthy",
                    details={
                        "eligible_processed": len(packages),
                        "package_status_counts": dict(counts),
                        "external_actions_authorized": False,
                    },
                )
            finally:
                if service.obumai is not None:
                    service.obumai.close()

        def run_refresh(settings=obum_settings) -> WorkerTaskResult:
            preparations = PostgresPreparationRepository(dsn)
            client = ObumAIClient(settings)
            try:
                limit = _positive_int("SMARTPLOY_REFRESH_BATCH_LIMIT", 50, maximum=500)
                updated = 0
                failures = 0
                states: Counter[str] = Counter()

                # The shared query selects only remote status checks. Each
                # selected item's owning profile gets a fresh tenant-scoped
                # preparation AND application repository for read/write.
                # Never use the legacy SMARTPLOY_PROFILE_ID in this path.
                for item in preparations.list_refresh_candidates(limit=limit):
                    if item.status not in ACTIVE_PREPARATION_STATES or not item.obum_job_id:
                        continue
                    service = _scoped_application_service(dsn, client, item.profile_id)
                    try:
                        current = service.refresh_preparation(item.package_id)
                    except (ObumAIError, KeyError):
                        # Rotate only within this preparation's owner scope.
                        service.preparation_repository.defer_failed_refresh(
                            item.package_id, item.obum_job_id
                        )
                        failures += 1
                        continue
                    updated += 1
                    states[current.status] += 1

                if failures and not updated:
                    status = "failed"
                elif failures:
                    status = "degraded"
                else:
                    status = "healthy"
                error = f"{failures} preparation refreshes failed" if failures else ""
                return WorkerTaskResult(
                    status=status,
                    error=error,
                    details={
                        "updated_count": updated,
                        "failure_count": failures,
                        "status_counts": dict(states),
                        "external_actions_authorized": False,
                    },
                )
            finally:
                client.close()

        # Status refreshes can observe already-submitted preparation jobs;
        # they do not originate new AI forwarding requests.
        specs.append(
            WorkerTaskSpec(
                task_id="application:refresh-preparations",
                task_kind="application_refresh",
                cadence_seconds=refresh_cadence,
                runner=run_refresh,
                metadata={"external_actions_authorized": False},
            )
        )
        # This is deliberately opt-in. The scheduler's disable_absent()
        # disables any previously persisted prepare-eligible task on restart.
        if auto_prepare_enabled:
            prepare_cadence = _positive_int("SMARTPLOY_WORKER_PREPARE_CADENCE_SECONDS", 120)
            specs.append(
                WorkerTaskSpec(
                    task_id="application:prepare-eligible",
                    task_kind="application_prepare",
                    cadence_seconds=prepare_cadence,
                    runner=run_prepare,
                    metadata={
                        "external_actions_authorized": False,
                        "unattended_model_processing_opt_in": True,
                    },
                )
            )

    return specs

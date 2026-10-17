"""Review-only, explicitly invoked, one-shot account-bound ObumAI draft dispatch.

CRITICAL: this function is NOT registered with the production worker.
It is NOT exposed to public APIs or triggered by saving consent. A
successful provider request is never an employer submission.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from .ai_processing_consent import JobAIConsent, PostgresJobAIConsentRepository
from .consented_worker_readiness import assess_consent_readiness
from .identity import PostgresIdentityRepository
from .obumai import ObumAIClient, ObumAIError
from .obumai_dispatch_storage import (
    DraftDispatchAttempt, PostgresDraftDispatchRepository,
)
from .preparations import (
    APPLICATION_DRAFT_INSTRUCTIONS, PREPARATION_ACTION,
    approved_evidence_snapshot, build_preparation,
)
from .scoring import score_candidate
from .worker_runtime import _scoped_application_service


def _report(status: str, *, model_attempted: bool = False) -> dict[str, object]:
    # Aggregate/review-only return, no email, CV, job text or tokens.
    return {
        "status": status,
        "model_dispatch_attempted": model_attempted,
        "employer_actions_authorized": False,
        "automatic_retry_authorized": False,
        "worker_registered": False,
    }


def dispatch_consented_draft_once(
    dsn: str, consent: JobAIConsent, client: ObumAIClient,
) -> dict[str, object]:
    """Run exactly one bounded, revocation-serialized draft request.

    Never invoke via an environment flag alone. This is an internal primitive
    for independently reviewed, manually controlled test/integration flows.

    Any crash/timeout after a durable 'sending' marker is *uncertain*; no
    automatic retry may be scheduled. The provider must be reconciled by
    stable request ID, not contacted with another POST.
    """
    timeout = float(client.settings.timeout_seconds)
    if not isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("Protected outbound timeout must be between 0 and 30 seconds")
    if not dsn:
        raise ValueError("PostgreSQL is required for protected dispatch")

    identity = PostgresIdentityRepository(dsn).get(consent.user_id)
    if (
        identity is None or identity.status != "active"
        or identity.profile_id != consent.profile_id
        or not consent.active
    ):
        return _report("owner_inactive")

    ledger = PostgresJobAIConsentRepository(dsn)
    attempts = PostgresDraftDispatchRepository(dsn)

    # EXCLUSIVE consent row lock serializes workers and user withdrawal.
    # No model request is permitted outside this context manager.
    with ledger.hold_authorized_dispatch(
        identity, consent.canonical_key,
        consent.job_snapshot_sha256, consent.evidence_sha256,
    ) as locked:
        if locked.revision != consent.revision or locked.consent_id != consent.consent_id:
            return _report("consent_changed")

        service = _scoped_application_service(dsn, client, locked.profile_id)
        candidate = service.get_job(locked.canonical_key)
        profile = service.profile()
        readiness = assess_consent_readiness(locked, identity, candidate, profile)
        if readiness.reason != "ready":
            return _report(readiness.reason)
        if candidate is None:
            return _report("job_missing")

        score = score_candidate(candidate, profile)
        package = build_preparation(candidate, profile, score)
        if (
            package.package_id != readiness.package_id
            or package.job_snapshot_sha256 != locked.job_snapshot_sha256
            or package.evidence_sha256 != locked.evidence_sha256
        ):
            return _report("snapshot_changed")
        # Existing draft packages, even failed/created records, cannot cause
        # a repeat external request through this path.
        existing = service.preparation_repository.get(package.package_id)
        if existing is not None:
            return _report("existing_preparation")

        # Stable over discovery freshness changes, but unique to account,
        # current job and approved evidence through immutable package ID.
        request_id = f"smartploy:{PREPARATION_ACTION}:{package.package_id}"
        attempt, new = attempts.reserve(locked, package, request_id)
        if not new:
            return _report(f"already_{attempt.state}")

        stored, created = service.preparation_repository.create_or_get(package)
        if not created:
            # The record was created by another path during this window.
            # Leave the durable attempt blocked, never send a second request.
            return _report("existing_preparation")
        service._sync_application(stored)

        evidence = approved_evidence_snapshot(profile)
        try:
            response = client.submit_reasoning(
                action=PREPARATION_ACTION,
                candidate=candidate,
                candidate_evidence=evidence,
                instructions=APPLICATION_DRAFT_INSTRUCTIONS,
                client_request_id_override=request_id,
            )
        except ObumAIError:
            attempts.mark_uncertain(
                package.package_id, request_id, profile_id=locked.profile_id,
                code="remote_error",
            )
            return _report("uncertain", model_attempted=True)
        except Exception:
            attempts.mark_uncertain(
                package.package_id, request_id, profile_id=locked.profile_id,
                code="internal_error",
            )
            raise

        job: Any = response.get("job") if isinstance(response, dict) else None
        remote_id = str(job.get("id") or "").strip() if isinstance(job, dict) else ""
        remote_state = str(job.get("state") or "").strip().casefold() if isinstance(job, dict) else ""
        echoed = str(response.get("smartploy_client_request_id") or "") if isinstance(response, dict) else ""
        if (
            not remote_id or len(remote_id) > 255
            or remote_state not in {"queued", "running", "blocked", "completed", "failed", "cancelled"}
            or (echoed and echoed != request_id)
        ):
            attempts.mark_uncertain(
                package.package_id, request_id, profile_id=locked.profile_id,
                code="invalid_response",
            )
            return _report("uncertain", model_attempted=True)

        # Persist the provider acceptance BEFORE updating materialized drafts.
        # If the application DB write crashes, the durable remote ID allows
        # later reconciliation without a duplicate remote POST.
        attempts.acknowledge(
            package.package_id, request_id, remote_id,
            profile_id=locked.profile_id,
        )
        updated = service._apply_obum_job(stored, job, client_request_id=request_id)
        stored = service.preparation_repository.save(updated)
        service._sync_application(stored)
        return _report("acknowledged", model_attempted=True)


def reconcile_acknowledged_draft_once(
    dsn: str, attempt: DraftDispatchAttempt, client: ObumAIClient,
) -> dict[str, object]:
    """GET an accepted remote job and repair materialization, NEVER re-POST.

    This deliberately excludes 'sending' and 'uncertain' requests: they need
    provider-side idempotency-key lookup and human incident review.
    Revoked/disabled users fail closed even though a remote draft exists.
    This method is NOT registered with any automatic worker task.
    """
    if attempt.state != "acknowledged" or not attempt.obum_job_id:
        return _report("requires_operator_reconciliation")
    identity = PostgresIdentityRepository(dsn).get(attempt.user_id)
    if (
        identity is None or identity.status != "active"
        or identity.profile_id != attempt.profile_id
    ):
        return _report("owner_inactive")

    ledger = PostgresJobAIConsentRepository(dsn)
    with ledger.hold_authorized_dispatch(
        identity, attempt.canonical_key,
        attempt.job_snapshot_sha256, attempt.evidence_sha256,
    ) as locked:
        if (
            locked.consent_id != attempt.consent_id
            or locked.revision != attempt.consent_revision
        ):
            return _report("consent_changed")
        persisted = PostgresDraftDispatchRepository(dsn).get(
            attempt.package_id, profile_id=attempt.profile_id,
        )
        if (
            persisted is None or persisted.state != "acknowledged"
            or persisted.obum_job_id != attempt.obum_job_id
            or persisted.obum_request_id != attempt.obum_request_id
            or persisted.profile_id != attempt.profile_id
        ):
            return _report("attempt_changed")

        service = _scoped_application_service(dsn, client, attempt.profile_id)
        preparation = service.get_preparation(attempt.package_id)
        if (
            preparation is None
            or preparation.profile_id != attempt.profile_id
            or preparation.canonical_key != attempt.canonical_key
            or preparation.job_snapshot_sha256 != attempt.job_snapshot_sha256
            or preparation.evidence_sha256 != attempt.evidence_sha256
        ):
            return _report("preparation_missing_or_changed")
        if preparation.status in {
            "completed", "completed_unparsed", "cancelled",
        }:
            return _report("already_finalized")
        try:
            # GET is safe to repeat. No prompt or approved evidence is sent.
            job = client.get_job(attempt.obum_job_id)
        except ObumAIError:
            return _report("remote_lookup_failed")
        if (
            not isinstance(job, dict)
            or str(job.get("id") or "").strip() != attempt.obum_job_id
            or str(job.get("state") or "").strip().casefold()
            not in {"queued", "running", "blocked", "completed", "failed", "cancelled"}
        ):
            return _report("invalid_remote_projection")

        updated = service._apply_obum_job(
            preparation, job, client_request_id=attempt.obum_request_id,
        )
        saved = service.preparation_repository.save(updated)
        service._sync_application(saved)
        return _report("remote_refreshed")

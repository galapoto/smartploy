"""Durable one-shot ObumAI draft delivery ledger.

A completed/ambiguous/sending attempt is NOT permission to send again.
Durability is local only, not proof of provider-side exactly-once processing.
This ledger has no external connections or employer submission methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from psycopg import connect

from .ai_processing_consent import JobAIConsent
from .preparations import ApplicationPreparation


DispatchState = Literal["sending", "acknowledged", "uncertain"]
UNCERTAIN_CODES = frozenset({
    "remote_error", "invalid_response", "internal_error",
})


@dataclass(frozen=True)
class DraftDispatchAttempt:
    package_id: str
    user_id: str
    profile_id: str
    canonical_key: str
    consent_id: str
    consent_revision: int
    job_snapshot_sha256: str
    evidence_sha256: str
    obum_request_id: str
    state: DispatchState
    obum_job_id: str
    failure_code: str
    created_at: str
    updated_at: str

    def to_review_dict(self) -> dict[str, object]:
        # Never include user/profile IDs or raw candidate data in diagnostics.
        return {
            "package_id": self.package_id,
            "state": self.state,
            "remote_job_registered": bool(self.obum_job_id),
            "failure_code": self.failure_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "automatic_retry_authorized": False,
            "employer_submission_authorized": False,
        }


class PostgresDraftDispatchRepository:
    """Atomic claim with no lease expiry or auto retry after an uncertain send."""

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN required for durable draft dispatch")

    @staticmethod
    def _select() -> str:
        return """
            SELECT package_id, user_id, profile_id, canonical_key, consent_id,
                   consent_revision, job_snapshot_sha256, evidence_sha256,
                   obum_request_id, state, obum_job_id, failure_code,
                   created_at, updated_at
            FROM smartploy_obumai_dispatch_attempts
        """

    @staticmethod
    def _read(row) -> DraftDispatchAttempt:
        return DraftDispatchAttempt(
            package_id=str(row[0]), user_id=str(row[1]), profile_id=str(row[2]),
            canonical_key=str(row[3]), consent_id=str(row[4]),
            consent_revision=int(row[5]), job_snapshot_sha256=str(row[6]),
            evidence_sha256=str(row[7]), obum_request_id=str(row[8]),
            state=str(row[9]), obum_job_id=str(row[10] or ""),
            failure_code=str(row[11] or ""),
            created_at=row[12].isoformat(), updated_at=row[13].isoformat(),
        )

    def get(self, package_id: str, *, profile_id: str) -> DraftDispatchAttempt | None:
        if not profile_id:
            raise ValueError("An explicit owner profile is required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + " WHERE package_id = %s AND profile_id = %s",
                    (package_id, profile_id),
                )
                row = cur.fetchone()
        return self._read(row) if row else None

    def reserve(
        self, consent: JobAIConsent, package: ApplicationPreparation, request_id: str,
    ) -> tuple[DraftDispatchAttempt, bool]:
        """Reserve at most one outbound attempt for one immutable draft package.

        Caller must hold the live consent dispatch lock and independently
        recheck owner/rights/job/evidence just before this operation.
        A conflicting request ID for a different package fails closed.
        """
        if not consent.active or consent.revision < 1:
            raise ValueError("Consent must be active to reserve a dispatch")
        if (
            consent.profile_id != package.profile_id
            or consent.canonical_key != package.canonical_key
            or consent.job_snapshot_sha256 != package.job_snapshot_sha256
            or consent.evidence_sha256 != package.evidence_sha256
            or not consent.user_id.startswith("usr-")
        ):
            raise ValueError("Consent and immutable preparation do not match")
        if not (isinstance(request_id, str) and 1 <= len(request_id) <= 255):
            raise ValueError("Bounded stable provider request ID is required")

        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO smartploy_obumai_dispatch_attempts (
                        package_id, user_id, profile_id, canonical_key,
                        consent_id, consent_revision, job_snapshot_sha256,
                        evidence_sha256, obum_request_id, state
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sending'
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING package_id
                    """,
                    (
                        package.package_id, consent.user_id, consent.profile_id,
                        consent.canonical_key, consent.consent_id, consent.revision,
                        package.job_snapshot_sha256, package.evidence_sha256,
                        request_id,
                    ),
                )
                inserted = cur.fetchone() is not None
                cur.execute(
                    self._select() + " WHERE package_id = %s",
                    (package.package_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise ValueError("Provider request ID conflicts with another package")
        attempt = self._read(row)
        if (
            attempt.user_id != consent.user_id
            or attempt.profile_id != package.profile_id
            or attempt.canonical_key != package.canonical_key
            or attempt.job_snapshot_sha256 != package.job_snapshot_sha256
            or attempt.evidence_sha256 != package.evidence_sha256
            or attempt.obum_request_id != request_id
        ):
            raise ValueError("Attempt identity conflict")
        # Existing attempts, including 'sending', cannot be retried
        # automatically, regardless of consent regrant or process restart.
        return attempt, inserted

    def acknowledge(
        self, package_id: str, request_id: str, remote_id: str,
        *, profile_id: str,
    ) -> DraftDispatchAttempt:
        value = str(remote_id or "").strip()
        if not (1 <= len(value) <= 255):
            raise ValueError("A bounded verified remote job ID is required")
        if not profile_id or not request_id:
            raise ValueError("Scoped request identity required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_obumai_dispatch_attempts
                    SET state = 'acknowledged', obum_job_id = %s,
                        failure_code = '', updated_at = now()
                    WHERE package_id = %s AND profile_id = %s
                      AND obum_request_id = %s AND state = 'sending'
                    RETURNING package_id
                    """,
                    (value, package_id, profile_id, request_id),
                )
                changed = cur.fetchone() is not None
                cur.execute(
                    self._select() + " WHERE package_id = %s AND profile_id = %s",
                    (package_id, profile_id),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError("Dispatch attempt not found for owner")
        attempt = self._read(row)
        if not changed and (attempt.state != "acknowledged" or attempt.obum_job_id != value):
            raise ValueError("Cannot acknowledge a changed or uncertain attempt")
        if attempt.obum_request_id != request_id:
            raise ValueError("Provider request ID mismatch")
        return attempt

    def mark_uncertain(
        self, package_id: str, request_id: str, *, profile_id: str, code: str,
    ) -> DraftDispatchAttempt:
        if code not in UNCERTAIN_CODES:
            raise ValueError("Only sanitized failure codes may be persisted")
        if not profile_id or not request_id:
            raise ValueError("Scoped request identity required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_obumai_dispatch_attempts
                    SET state = 'uncertain', failure_code = %s, updated_at = now()
                    WHERE package_id = %s AND profile_id = %s
                      AND obum_request_id = %s AND state = 'sending'
                    RETURNING package_id
                    """,
                    (code, package_id, profile_id, request_id),
                )
                cur.execute(
                    self._select() + " WHERE package_id = %s AND profile_id = %s",
                    (package_id, profile_id),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError("Dispatch attempt not found for owner")
        attempt = self._read(row)
        if attempt.obum_request_id != request_id:
            raise ValueError("Provider request ID mismatch")
        return attempt

    def list_needing_reconciliation(
        self, *, limit: int = 100,
    ) -> list[DraftDispatchAttempt]:
        """Operator-only read path, never automatically re-sends request."""
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + """
                        WHERE state IN ('sending', 'uncertain', 'acknowledged')
                        ORDER BY updated_at ASC, package_id ASC LIMIT %s
                    """,
                    (bounded,),
                )
                rows = cur.fetchall()
        return [self._read(row) for row in rows]

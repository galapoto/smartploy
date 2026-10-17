"""Review-only account erasure quarantine; no provider deletes or hard purge.

Only an independently authenticated operator may invoke this internal module.
No route, scheduler task, UI button or public credential is installed.
Quarantine is atomic and waits for in-flight consent-protected dispatch:
identity disabled, all sessions revoked, consent withdrawn, and known
remote-work obligations recorded before commit. No declaration of erasure.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from psycopg import connect

from .domain import canonical_json


class ErasureIdentityMismatch(ValueError):
    pass


@dataclass(frozen=True)
class ErasureQuarantineStatus:
    request_id: str
    status: str
    pending_provider_obligations: int
    revoked_consents: int
    revoked_sessions: int

    def to_dict(self) -> dict[str, object]:
        # Never expose user/profile ids, emails, job text, document names or
        # individual remote IDs in an ordinary privacy status response.
        return {
            "request_id": self.request_id,
            "status": self.status,
            "processing_disabled": True,
            "sessions_revoked": True,
            "future_obumai_dispatch_authorized": False,
            "pending_provider_obligations": self.pending_provider_obligations,
            "provider_deletion_verified": False,
            "local_data_purged": False,
            "erasure_completed": False,
            "requires_operator_review": True,
        }


@dataclass(frozen=True)
class ProcessorCleanupObligation:
    obligation_id: str
    remote_job_id: str
    remote_request_id: str
    state: str

    # These remote identifiers may be personal data. No to_dict() method,
    # no public API. Operator-only processing and security-reviewed handling.


class PostgresAccountErasureRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL is required for erasure quarantine")

    @staticmethod
    def _validate(user_id: str, profile_id: str) -> None:
        if not (isinstance(user_id, str) and user_id.startswith("usr-")):
            raise ErasureIdentityMismatch("A stable SmartPloy user ID is required")
        if not (isinstance(profile_id, str) and profile_id.startswith("profile-")):
            # Explicit legacy profile claims can have a different profile ID.
            # Only syntactically valid non-empty owner profiles are accepted.
            if not (isinstance(profile_id, str) and 1 <= len(profile_id) <= 160):
                raise ErasureIdentityMismatch("An explicit owner profile ID is required")

    @staticmethod
    def _obligation_key(request_id: str, remote_job_id: str, remote_request_id: str) -> str:
        reference = "job:" + remote_job_id if remote_job_id else "request:" + remote_request_id
        material = canonical_json(["smartploy.obumai.erasure.v1", request_id, reference])
        return "erase-obligation-" + sha256(material.encode("utf-8")).hexdigest()[:40]

    def quarantine(self, user_id: str, profile_id: str) -> ErasureQuarantineStatus:
        """Wait for protected dispatch to end; disable and inventory atomically.

        A 5s lock timeout FAILS without claiming any quarantine succeeded.
        Re-running this operation is idempotent and re-inventories any newly
        visible remote IDs without re-enabling consent.
        """
        self._validate(user_id, profile_id)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('lock_timeout', '5000ms', true)")
                cur.execute(
                    """
                    SELECT u.status
                    FROM smartploy_users AS u
                    JOIN smartploy_user_profiles AS p ON p.user_id = u.user_id
                    WHERE u.user_id = %s AND p.profile_id = %s
                    FOR UPDATE OF u, p
                    """,
                    (user_id, profile_id),
                )
                if cur.fetchone() is None:
                    raise ErasureIdentityMismatch("Account/profile binding not found")

                cur.execute(
                    """
                    SELECT request_id FROM smartploy_account_erasure_requests
                    WHERE user_id = %s AND profile_id = %s FOR UPDATE
                    """,
                    (user_id, profile_id),
                )
                prior = cur.fetchone()
                request_id = str(prior[0]) if prior else "erasure-" + uuid4().hex
                if prior is None:
                    cur.execute(
                        """
                        INSERT INTO smartploy_account_erasure_requests
                            (request_id, user_id, profile_id, state)
                        VALUES (%s, %s, %s, 'quarantined')
                        """,
                        (request_id, user_id, profile_id),
                    )

                # Do not retain user email after a quarantine. Session metadata
                # is also erased, not merely marked revoked.
                cur.execute(
                    """
                    UPDATE smartploy_users
                    SET status = 'disabled', email = '', metadata = '{}'::jsonb,
                        updated_at = now()
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                cur.execute(
                    """
                    UPDATE smartploy_sessions
                    SET revoked_at = COALESCE(revoked_at, now()),
                        email = '', metadata = '{}'::jsonb
                    WHERE user_id = %s
                      AND (revoked_at IS NULL OR email <> '' OR metadata <> '{}'::jsonb)
                    """,
                    (user_id,),
                )
                revoked_sessions = cur.rowcount
                cur.execute(
                    """
                    WITH changed AS (
                        UPDATE smartploy_obumai_consents
                        SET revoked_at = now(), updated_at = now(),
                            revision = revision + 1
                        WHERE user_id = %s AND profile_id = %s
                          AND revoked_at IS NULL
                        RETURNING consent_id, user_id, profile_id, revision,
                                  job_snapshot_sha256, evidence_sha256
                    )
                    INSERT INTO smartploy_obumai_consent_events (
                        event_id, consent_id, user_id, profile_id, event_type,
                        revision, job_snapshot_sha256, evidence_sha256, occurred_at
                    )
                    SELECT 'erasure-revoke-' || consent_id || '-r' || revision,
                           consent_id, user_id, profile_id, 'revoked',
                           revision, job_snapshot_sha256, evidence_sha256, now()
                    FROM changed
                    WHERE true
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (user_id, profile_id),
                )
                revoked_consents = cur.rowcount

                # Discover both legacy remote draft jobs and modern durable
                # attempts. In-flight uncertain sends may have only a client
                # request ID, which must not be silently discarded.
                cur.execute(
                    """
                    SELECT obum_job_id, '' FROM smartploy_application_preparations
                    WHERE profile_id = %s AND obum_job_id <> ''
                    UNION ALL
                    SELECT obum_job_id, obum_request_id
                    FROM smartploy_obumai_dispatch_attempts
                    WHERE user_id = %s AND profile_id = %s
                      AND (obum_job_id <> '' OR obum_request_id <> '')
                    """,
                    (profile_id, user_id, profile_id),
                )
                for raw_job_id, raw_request_id in cur.fetchall():
                    job_id = str(raw_job_id or "")
                    remote_request_id = str(raw_request_id or "")
                    obligation_id = self._obligation_key(
                        request_id, job_id, remote_request_id,
                    )
                    cur.execute(
                        """
                        INSERT INTO smartploy_obumai_erasure_obligations (
                            obligation_id, request_id, remote_job_id,
                            remote_request_id, state
                        ) VALUES (%s, %s, %s, %s, 'requires_provider_followup')
                        ON CONFLICT (obligation_id) DO UPDATE SET
                            remote_request_id = CASE
                                WHEN smartploy_obumai_erasure_obligations.remote_request_id = ''
                                THEN EXCLUDED.remote_request_id
                                ELSE smartploy_obumai_erasure_obligations.remote_request_id
                            END
                        """,
                        (obligation_id, request_id, job_id, remote_request_id),
                    )
                cur.execute(
                    """
                    SELECT count(*) FROM smartploy_obumai_erasure_obligations
                    WHERE request_id = %s AND state = 'requires_provider_followup'
                    """,
                    (request_id,),
                )
                pending_count = int(cur.fetchone()[0])
        return ErasureQuarantineStatus(
            request_id=request_id, status="quarantined",
            pending_provider_obligations=pending_count,
            revoked_consents=revoked_consents,
            revoked_sessions=revoked_sessions,
        )

    def list_operator_obligations(
        self, request_id: str, *, limit: int = 100,
    ) -> list[ProcessorCleanupObligation]:
        """Internal operator-only inventory, not a public user/API response."""
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT obligation_id, remote_job_id, remote_request_id, state
                    FROM smartploy_obumai_erasure_obligations
                    WHERE request_id = %s ORDER BY detected_at, obligation_id LIMIT %s
                    """,
                    (request_id, bounded),
                )
                rows = cur.fetchall()
        return [
            ProcessorCleanupObligation(
                obligation_id=str(row[0]), remote_job_id=str(row[1]),
                remote_request_id=str(row[2]), state=str(row[3]),
            )
            for row in rows
        ]

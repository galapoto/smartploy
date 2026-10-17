"""Private, job-and-evidence-scoped ObumAI consent ledger (no dispatch authority).

Only an authenticated verified user may grant this permission. Consent is
bound to one immutable job/evidence snapshot, never to email or broad account
settings. A revoked or mismatched consent cannot authorize unattended work.

The worker is STILL disabled for unattended production AI: this module stores
and checks permission; it never initiates model or employer actions.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterator, Protocol
from uuid import uuid4

from psycopg import connect

from .domain import canonical_json
from .identity import UserProfileBinding


class ConsentIdentityError(ValueError):
    """The claimed account/profile pair is not an active verified identity."""


class ConsentDispatchDenied(PermissionError):
    """No current, job-specific and evidence-specific grant permits dispatch."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _consent_id(user_id: str, profile_id: str, canonical_key: str) -> str:
    digest = sha256(canonical_json(
        [user_id, profile_id, canonical_key, "obumai", "unattended_application_draft", "v1"]
    ).encode("utf-8")).hexdigest()
    return "obumai-consent-" + digest[:32]


def _check_binding(binding: UserProfileBinding) -> None:
    if (
        not isinstance(binding, UserProfileBinding)
        or binding.status != "active"
        or not binding.user_id.startswith("usr-")
        or not binding.profile_id
    ):
        raise ConsentIdentityError("An active verified SmartPloy user and profile are required")


def _check_scope(canonical_key: str, job_sha: str, evidence_sha: str) -> None:
    if not isinstance(canonical_key, str) or not (1 <= len(canonical_key) <= 256):
        raise ValueError("A bounded canonical job key is required")
    if not all(
        isinstance(value, str) and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
        for value in (job_sha, evidence_sha)
    ):
        raise ValueError("Exact SHA-256 job and approved-evidence snapshots are required")


@dataclass(frozen=True)
class JobAIConsent:
    consent_id: str
    user_id: str
    profile_id: str
    canonical_key: str
    job_snapshot_sha256: str
    evidence_sha256: str
    revision: int
    granted_at: str
    revoked_at: str = ""
    updated_at: str = ""

    @property
    def active(self) -> bool:
        return not self.revoked_at

    def to_dict(self) -> dict[str, object]:
        # No account identifiers, emails, raw profile content or job text.
        return {
            "consent_id": self.consent_id,
            "canonical_key": self.canonical_key,
            "processor": "obumai",
            "purpose": "application_draft",
            "mode": "unattended",
            "job_snapshot_sha256": self.job_snapshot_sha256,
            "evidence_sha256": self.evidence_sha256,
            "revision": self.revision,
            "granted_at": self.granted_at,
            "revoked_at": self.revoked_at,
            "active": self.active,
            "processing_started": False,
            "employer_actions_authorized": False,
        }


@dataclass(frozen=True)
class ConsentEvent:
    event_id: str
    consent_id: str
    user_id: str
    profile_id: str
    event_type: str
    revision: int
    job_snapshot_sha256: str
    evidence_sha256: str
    occurred_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "consent_id": self.consent_id,
            "event_type": self.event_type,
            "revision": self.revision,
            "job_snapshot_sha256": self.job_snapshot_sha256,
            "evidence_sha256": self.evidence_sha256,
            "occurred_at": self.occurred_at,
        }


class JobAIConsentRepository(Protocol):
    def grant(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> tuple[JobAIConsent, bool]: ...
    def revoke(self, binding: UserProfileBinding, consent_id: str) -> JobAIConsent | None: ...
    def list(self, binding: UserProfileBinding, *, limit: int = 100) -> list[JobAIConsent]: ...
    def events(self, binding: UserProfileBinding, *, limit: int = 100) -> list[ConsentEvent]: ...
    def authorized(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> bool: ...


def _event(item: JobAIConsent, event_type: str) -> ConsentEvent:
    return ConsentEvent(
        event_id="consent-event-" + uuid4().hex,
        consent_id=item.consent_id,
        user_id=item.user_id,
        profile_id=item.profile_id,
        event_type=event_type,
        revision=item.revision,
        job_snapshot_sha256=item.job_snapshot_sha256,
        evidence_sha256=item.evidence_sha256,
        occurred_at=_utc_now(),
    )


class MemoryJobAIConsentRepository:
    def __init__(self) -> None:
        self._items: dict[str, JobAIConsent] = {}
        self._events: list[ConsentEvent] = []

    def grant(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> tuple[JobAIConsent, bool]:
        _check_binding(binding)
        _check_scope(canonical_key, job_sha, evidence_sha)
        consent_id = _consent_id(binding.user_id, binding.profile_id, canonical_key)
        previous = self._items.get(consent_id)
        if previous is not None and previous.active and (
            previous.job_snapshot_sha256 == job_sha
            and previous.evidence_sha256 == evidence_sha
        ):
            return previous, False
        now = _utc_now()
        current = JobAIConsent(
            consent_id=consent_id,
            user_id=binding.user_id,
            profile_id=binding.profile_id,
            canonical_key=canonical_key,
            job_snapshot_sha256=job_sha,
            evidence_sha256=evidence_sha,
            revision=previous.revision + 1 if previous else 1,
            granted_at=now,
            updated_at=now,
        )
        self._items[consent_id] = current
        self._events.append(_event(current, "granted"))
        return current, True

    def revoke(self, binding: UserProfileBinding, consent_id: str) -> JobAIConsent | None:
        _check_binding(binding)
        current = self._items.get(consent_id)
        if (
            current is None or current.user_id != binding.user_id
            or current.profile_id != binding.profile_id
        ):
            return None
        if not current.active:
            return current
        now = _utc_now()
        revoked = replace(
            current, revision=current.revision + 1, revoked_at=now, updated_at=now
        )
        self._items[consent_id] = revoked
        self._events.append(_event(revoked, "revoked"))
        return revoked

    def list(self, binding: UserProfileBinding, *, limit: int = 100) -> list[JobAIConsent]:
        _check_binding(binding)
        return sorted(
            (x for x in self._items.values()
             if x.user_id == binding.user_id and x.profile_id == binding.profile_id),
            key=lambda x: (x.updated_at, x.consent_id), reverse=True,
        )[:max(1, min(int(limit), 100))]

    def events(self, binding: UserProfileBinding, *, limit: int = 100) -> list[ConsentEvent]:
        _check_binding(binding)
        return sorted(
            (x for x in self._events
             if x.user_id == binding.user_id and x.profile_id == binding.profile_id),
            key=lambda x: (x.occurred_at, x.event_id), reverse=True,
        )[:max(1, min(int(limit), 100))]

    def authorized(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> bool:
        try:
            _check_binding(binding)
            _check_scope(canonical_key, job_sha, evidence_sha)
        except (ConsentIdentityError, ValueError):
            return False
        current = self._items.get(_consent_id(binding.user_id, binding.profile_id, canonical_key))
        return bool(
            current and current.active
            and current.user_id == binding.user_id
            and current.profile_id == binding.profile_id
            and current.job_snapshot_sha256 == job_sha
            and current.evidence_sha256 == evidence_sha
        )


class PostgresJobAIConsentRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    @staticmethod
    def _read(row) -> JobAIConsent:
        return JobAIConsent(
            consent_id=str(row[0]),
            user_id=str(row[1]),
            profile_id=str(row[2]),
            canonical_key=str(row[3]),
            job_snapshot_sha256=str(row[4]),
            evidence_sha256=str(row[5]),
            revision=int(row[6]),
            granted_at=row[7].isoformat(),
            revoked_at=row[8].isoformat() if row[8] else "",
            updated_at=row[9].isoformat(),
        )

    @staticmethod
    def _select() -> str:
        return """
            SELECT consent_id, user_id, profile_id, canonical_key,
                   job_snapshot_sha256, evidence_sha256, revision,
                   granted_at, revoked_at, updated_at
            FROM smartploy_obumai_consents
        """

    @staticmethod
    def _check_live_identity(cursor, binding: UserProfileBinding) -> None:
        # A forged user ID, disabled account, or reassigned profile may never
        # mint a durable consent. Lock live rows through this transaction.
        cursor.execute(
            """
            SELECT 1 FROM smartploy_users AS u
            JOIN smartploy_user_profiles AS p ON p.user_id = u.user_id
            WHERE u.user_id = %s AND p.profile_id = %s AND u.status = 'active'
            FOR SHARE OF u, p
            """,
            (binding.user_id, binding.profile_id),
        )
        if cursor.fetchone() is None:
            raise ConsentIdentityError("An active verified SmartPloy user and profile are required")

    @staticmethod
    def _insert_event(cursor, item: JobAIConsent, kind: str) -> None:
        cursor.execute(
            """
            INSERT INTO smartploy_obumai_consent_events (
                event_id, consent_id, user_id, profile_id, event_type, revision,
                job_snapshot_sha256, evidence_sha256, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            """,
            (
                "consent-event-" + uuid4().hex, item.consent_id, item.user_id,
                item.profile_id, kind, item.revision,
                item.job_snapshot_sha256, item.evidence_sha256,
            ),
        )

    def grant(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> tuple[JobAIConsent, bool]:
        _check_binding(binding)
        _check_scope(canonical_key, job_sha, evidence_sha)
        consent_id = _consent_id(binding.user_id, binding.profile_id, canonical_key)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                self._check_live_identity(cur, binding)
                cur.execute(
                    """
                    INSERT INTO smartploy_obumai_consents (
                        consent_id, user_id, profile_id, canonical_key,
                        job_snapshot_sha256, evidence_sha256, revision,
                        granted_at, revoked_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 1, now(), NULL, now())
                    ON CONFLICT (consent_id) DO UPDATE SET
                        job_snapshot_sha256 = EXCLUDED.job_snapshot_sha256,
                        evidence_sha256 = EXCLUDED.evidence_sha256,
                        revision = smartploy_obumai_consents.revision + 1,
                        granted_at = now(),
                        revoked_at = NULL,
                        updated_at = now()
                    WHERE (
                        smartploy_obumai_consents.revoked_at IS NOT NULL
                        OR smartploy_obumai_consents.job_snapshot_sha256
                            IS DISTINCT FROM EXCLUDED.job_snapshot_sha256
                        OR smartploy_obumai_consents.evidence_sha256
                            IS DISTINCT FROM EXCLUDED.evidence_sha256
                    )
                    AND smartploy_obumai_consents.user_id = EXCLUDED.user_id
                    AND smartploy_obumai_consents.profile_id = EXCLUDED.profile_id
                    AND smartploy_obumai_consents.canonical_key = EXCLUDED.canonical_key
                    RETURNING consent_id, user_id, profile_id, canonical_key,
                              job_snapshot_sha256, evidence_sha256, revision,
                              granted_at, revoked_at, updated_at
                    """,
                    (
                        consent_id, binding.user_id, binding.profile_id, canonical_key,
                        job_sha, evidence_sha,
                    ),
                )
                row = cur.fetchone()
                changed = row is not None
                if row is None:
                    cur.execute(self._select() + " WHERE consent_id = %s AND user_id = %s AND profile_id = %s",
                                (consent_id, binding.user_id, binding.profile_id))
                    row = cur.fetchone()
                if row is None:
                    raise ConsentIdentityError("Consent identity conflict")
                item = self._read(row)
                if changed:
                    self._insert_event(cur, item, "granted")
        return item, changed

    def revoke(self, binding: UserProfileBinding, consent_id: str) -> JobAIConsent | None:
        _check_binding(binding)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE smartploy_obumai_consents
                    SET revoked_at = now(), updated_at = now(), revision = revision + 1
                    WHERE consent_id = %s AND user_id = %s AND profile_id = %s
                      AND revoked_at IS NULL
                    RETURNING consent_id, user_id, profile_id, canonical_key,
                              job_snapshot_sha256, evidence_sha256, revision,
                              granted_at, revoked_at, updated_at
                    """,
                    (consent_id, binding.user_id, binding.profile_id),
                )
                row = cur.fetchone()
                if row is not None:
                    current = self._read(row)
                    self._insert_event(cur, current, "revoked")
                else:
                    cur.execute(
                        self._select() + " WHERE consent_id = %s AND user_id = %s AND profile_id = %s",
                        (consent_id, binding.user_id, binding.profile_id),
                    )
                    row = cur.fetchone()
                    current = self._read(row) if row else None
        return current

    def list(self, binding: UserProfileBinding, *, limit: int = 100) -> list[JobAIConsent]:
        _check_binding(binding)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + """
                        WHERE user_id = %s AND profile_id = %s
                        ORDER BY updated_at DESC, consent_id DESC LIMIT %s
                    """,
                    (binding.user_id, binding.profile_id, max(1, min(int(limit), 100))),
                )
                rows = cur.fetchall()
        return [self._read(row) for row in rows]

    def events(self, binding: UserProfileBinding, *, limit: int = 100) -> list[ConsentEvent]:
        _check_binding(binding)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, consent_id, user_id, profile_id, event_type,
                           revision, job_snapshot_sha256, evidence_sha256, occurred_at
                    FROM smartploy_obumai_consent_events
                    WHERE user_id = %s AND profile_id = %s
                    ORDER BY occurred_at DESC, event_id DESC LIMIT %s
                    """,
                    (binding.user_id, binding.profile_id, max(1, min(int(limit), 100))),
                )
                rows = cur.fetchall()
        return [
            ConsentEvent(
                event_id=str(row[0]), consent_id=str(row[1]),
                user_id=str(row[2]), profile_id=str(row[3]),
                event_type=str(row[4]), revision=int(row[5]),
                job_snapshot_sha256=str(row[6]), evidence_sha256=str(row[7]),
                occurred_at=row[8].isoformat(),
            )
            for row in rows
        ]

    def authorized(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> bool:
        try:
            _check_binding(binding)
            _check_scope(canonical_key, job_sha, evidence_sha)
        except (ConsentIdentityError, ValueError):
            return False
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM smartploy_obumai_consents AS c
                    JOIN smartploy_users AS u ON u.user_id = c.user_id
                    JOIN smartploy_user_profiles AS p
                      ON p.user_id = u.user_id AND p.profile_id = c.profile_id
                    WHERE c.consent_id = %s AND c.user_id = %s
                      AND c.profile_id = %s AND c.canonical_key = %s
                      AND c.job_snapshot_sha256 = %s AND c.evidence_sha256 = %s
                      AND c.revoked_at IS NULL AND u.status = 'active'
                    """,
                    (
                        _consent_id(binding.user_id, binding.profile_id, canonical_key),
                        binding.user_id, binding.profile_id, canonical_key,
                        job_sha, evidence_sha,
                    ),
                )
                return cur.fetchone() is not None

    def list_active_verified(self, *, limit: int = 100) -> list[JobAIConsent]:
        """Internal read-only planning candidates, NOT dispatch authorization.

        The active-account JOIN keeps stale/deleted/disabled accounts out of
        candidate scans. Recheck identity, source, snapshots and consent under
        lock at the actual transmission boundary, never trust this list alone.
        """
        bounded = max(1, min(int(limit), 500))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.consent_id, c.user_id, c.profile_id, c.canonical_key,
                           c.job_snapshot_sha256, c.evidence_sha256, c.revision,
                           c.granted_at, c.revoked_at, c.updated_at
                    FROM smartploy_obumai_consents AS c
                    JOIN smartploy_users AS u ON u.user_id = c.user_id
                    JOIN smartploy_user_profiles AS p
                      ON p.user_id = u.user_id AND p.profile_id = c.profile_id
                    WHERE c.revoked_at IS NULL AND u.status = 'active'
                    ORDER BY c.updated_at ASC, c.consent_id ASC
                    LIMIT %s
                    """,
                    (bounded,),
                )
                rows = cur.fetchall()
        return [self._read(row) for row in rows]

    @contextmanager
    def hold_authorized_dispatch(
        self, binding: UserProfileBinding, canonical_key: str,
        job_sha: str, evidence_sha: str,
    ) -> Iterator[JobAIConsent]:
        """Hold DB row locks across ONE bounded outbound dispatch attempt.

        A revocation or regrant UPDATE waits for this block to finish. If it
        commits before these locks are obtained, a new dispatch is rejected.
        This serializes future sends with withdrawal, without falsely claiming
        that withdrawal cancels already in-flight requests.

        Caller MUST re-fetch live current job/profile data, check source rights
        and eligibility, and send ONLY the exact hashes locked here. Keeping
        network requests inside a DB transaction is a review-only strategy,
        not a production release decision. Never retry outside this guard.
        """
        _check_binding(binding)
        _check_scope(canonical_key, job_sha, evidence_sha)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                # Do not wait indefinitely to *start* a protected send.
                # Timeouts and DB errors fail closed; no transaction is
                # silently downgraded to the non-locking authorized() view.
                cur.execute("SELECT set_config('lock_timeout', '5000ms', true)")
                self._check_live_identity(cur, binding)
                cur.execute(
                    self._select() + """
                        WHERE consent_id = %s AND user_id = %s
                          AND profile_id = %s AND canonical_key = %s
                          AND job_snapshot_sha256 = %s AND evidence_sha256 = %s
                          AND revoked_at IS NULL
                        FOR SHARE
                    """,
                    (
                        _consent_id(binding.user_id, binding.profile_id, canonical_key),
                        binding.user_id, binding.profile_id, canonical_key,
                        job_sha, evidence_sha,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise ConsentDispatchDenied(
                        "No current permission covers this job and approved evidence"
                    )
                yield self._read(row)

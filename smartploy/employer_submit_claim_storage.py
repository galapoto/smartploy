"""SP15a: internal PostgreSQL one-shot employer claim, NOT a submission API.

Reuse the ObumAI draft-dispatch reservation pattern and account-erasure
locking. This separate employer ledger has no external submit, expiry or retry.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4
from urllib.parse import urlsplit

from psycopg import connect

from .browser_handoff import HandoffError, PLACEHOLDERS, _posting_url
from .identity import UserProfileBinding


def _employer_job_key_sha256(verified_url: str) -> str:
    """Same Lever organisation/job across source keys, regions and /apply URLs.

    Only use after browser_handoff._posting_url strictly validates the URL.
    """
    parts = urlsplit(verified_url).path.strip("/").split("/")
    # Lever host is already allowlisted; query/tracking and /apply are ignored.
    if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != "apply"):
        raise EmployerSubmitClaimDenied("Unrecognized canonical employer job")
    material = "lever-job-v1\0" + parts[0].casefold() + "\0" + parts[1].casefold()
    return sha256(material.encode("utf-8")).hexdigest()


class EmployerSubmitClaimDenied(ValueError):
    """Fail closed on ownership, approval, document, or posting drift."""


@dataclass(frozen=True)
class EmployerSubmitClaim:
    claim_id: str
    user_id: str
    profile_id: str
    canonical_key: str
    workspace_id: str
    document_revision: int
    document_sha256: str
    application_url_sha256: str
    employer_job_key_sha256: str
    state: str
    failure_code: str
    created_at: str
    updated_at: str

    def to_review_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "automatic_retry_authorized": False,
            "employer_submission_verified": False,
        }



def verified_employer_submit_preflight(
    cur, binding: UserProfileBinding, *,
    workspace_id: str, expected_revision: int,
    expected_application_url: str, expected_job_fingerprint: str,
) -> tuple[str, str, str]:
    """Reuse the SAME transactional owner/job/document checks for claim and review.

    Called with a live PostgreSQL cursor inside the caller's transaction.
    Caller must NOT treat successful preflight as external submit permission.
    """
    if (
        binding.status != "active" or not binding.user_id.startswith("usr-")
        or not binding.profile_id or not isinstance(workspace_id, str)
        or not 1 <= len(workspace_id) <= 160
        or type(expected_revision) is not int or expected_revision <= 0
        or not isinstance(expected_job_fingerprint, str)
        or not 1 <= len(expected_job_fingerprint) <= 128
    ):
        raise EmployerSubmitClaimDenied("Verified owner and saved review revision required")
    try:
        _posting_url(expected_application_url)
    except (HandoffError, TypeError) as exc:
        raise EmployerSubmitClaimDenied("Verified HTTPS Lever employer URL required") from exc

    # Same lock order as account erasure: quarantine and claim serialize.
    cur.execute(
        """SELECT u.status FROM smartploy_users AS u
           JOIN smartploy_user_profiles AS p ON p.user_id=u.user_id
           WHERE u.user_id=%s AND p.profile_id=%s
           FOR UPDATE OF u, p""",
        (binding.user_id, binding.profile_id),
    )
    owner = cur.fetchone()
    if owner is None or owner[0] != "active":
        raise EmployerSubmitClaimDenied("Account disabled or binding mismatch")
    cur.execute(
        """SELECT 1 FROM smartploy_account_erasure_requests
           WHERE user_id=%s AND profile_id=%s AND state='quarantined'""",
        (binding.user_id, binding.profile_id),
    )
    if cur.fetchone():
        raise EmployerSubmitClaimDenied("Account quarantined")
    cur.execute(
        """SELECT canonical_key, application_url, job_fingerprint,
                  revision, status, cv_text, cover_letter_text
           FROM smartploy_application_workspaces
           WHERE workspace_id=%s AND profile_id=%s FOR UPDATE""",
        (workspace_id, binding.profile_id),
    )
    w = cur.fetchone()
    if (
        w is None or w[1] != expected_application_url
        or w[2] != expected_job_fingerprint or w[3] != expected_revision
        or w[4] != "draft"
    ):
        raise EmployerSubmitClaimDenied("Saved workspace changed or already applied")
    key = str(w[0])
    cv, letter = str(w[5]), str(w[6])
    if not cv.strip() or len(letter.strip()) < 60 or PLACEHOLDERS.search(letter):
        raise EmployerSubmitClaimDenied("Application documents incomplete")
    cur.execute(
        """SELECT source_current, closed_at, candidate FROM smartploy_jobs
           WHERE canonical_key=%s FOR UPDATE""",
        (key,),
    )
    job = cur.fetchone()
    if job is None or job[0] is not True or job[1] is not None:
        raise EmployerSubmitClaimDenied("Job is no longer current")
    candidate = job[2]
    if (
        not isinstance(candidate, dict)
        or candidate.get("description_fingerprint") != expected_job_fingerprint
        or not isinstance(candidate.get("job"), dict)
        or candidate["job"].get("application_url") != expected_application_url
    ):
        raise EmployerSubmitClaimDenied("Live employer posting differs from saved review")
    cur.execute(
        """SELECT 1 FROM smartploy_browser_receipts
           WHERE profile_id=%s AND workspace_id=%s""",
        (binding.profile_id, workspace_id),
    )
    if cur.fetchone():
        raise EmployerSubmitClaimDenied("An observed receipt already exists")
    cur.execute(
        """SELECT 1 FROM smartploy_applications AS a
           JOIN smartploy_application_preparations AS p
             ON p.package_id=a.package_id
           WHERE p.profile_id=%s AND p.canonical_key=%s
             AND a.state NOT IN ('preparing','ready_for_review',
                                 'needs_review','preparation_blocked')
           LIMIT 1""",
        (binding.profile_id, key),
    )
    if cur.fetchone():
        raise EmployerSubmitClaimDenied("Previous CRM application requires reconciliation")

    return key, cv, letter

class PostgresEmployerSubmitClaimRepository:
    """Dormant server primitive until authenticated browser handoff is built.

    Caller must independently verify the session, origin, user final-action
    approval, full preflight and employer automation rights. The database
    also rechecks active owner, latest source, document and existing records.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL is mandatory for cross-device employer claims")

    @staticmethod
    def _select() -> str:
        return """SELECT claim_id, user_id, profile_id, canonical_key, workspace_id,
                         document_revision, document_sha256, application_url_sha256,
                         employer_job_key_sha256, state, failure_code, created_at, updated_at
                  FROM smartploy_employer_submit_claims"""

    @staticmethod
    def _read(row: tuple) -> EmployerSubmitClaim:
        return EmployerSubmitClaim(
            claim_id=str(row[0]), user_id=str(row[1]), profile_id=str(row[2]),
            canonical_key=str(row[3]), workspace_id=str(row[4]),
            document_revision=int(row[5]), document_sha256=str(row[6]),
            application_url_sha256=str(row[7]), employer_job_key_sha256=str(row[8]),
            state=str(row[9]), failure_code=str(row[10] or ""),
            created_at=row[11].isoformat(), updated_at=row[12].isoformat(),
        )

    def get(self, binding: UserProfileBinding, canonical_key: str) -> EmployerSubmitClaim | None:
        if not binding.user_id or not binding.profile_id or not canonical_key:
            raise EmployerSubmitClaimDenied("Explicit verified owner and job required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + " WHERE user_id=%s AND profile_id=%s AND canonical_key=%s",
                    (binding.user_id, binding.profile_id, canonical_key),
                )
                row = cur.fetchone()
        return self._read(row) if row else None

    def get_for_employer_url(
        self, binding: UserProfileBinding, application_url: str,
    ) -> EmployerSubmitClaim | None:
        """Locate a claim even when another imported source has a different key."""
        if not binding.user_id or not binding.profile_id:
            raise EmployerSubmitClaimDenied("Verified account required")
        try:
            _posting_url(application_url)
        except (HandoffError, TypeError) as exc:
            raise EmployerSubmitClaimDenied("Verified Lever employer URL required") from exc
        employer_key = _employer_job_key_sha256(application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + """
                        WHERE user_id=%s AND profile_id=%s AND employer_job_key_sha256=%s
                    """,
                    (binding.user_id, binding.profile_id, employer_key),
                )
                row = cur.fetchone()
        return self._read(row) if row else None

    def reserve(
        self, binding: UserProfileBinding, *,
        workspace_id: str, expected_revision: int,
        expected_application_url: str, expected_job_fingerprint: str,
        explicit_final_user_approval: bool, employer_submission_permitted: bool,
    ) -> tuple[EmployerSubmitClaim, bool]:
        """Only inserted=True is a new marker, NEVER a browser-click grant."""
        if explicit_final_user_approval is not True or employer_submission_permitted is not True:
            raise EmployerSubmitClaimDenied("Explicit final approval and employer rights required")
        if (
            binding.status != "active" or not binding.user_id.startswith("usr-")
            or not binding.profile_id or not isinstance(workspace_id, str)
            or not 1 <= len(workspace_id) <= 160 or type(expected_revision) is not int
            or expected_revision <= 0 or not isinstance(expected_job_fingerprint, str)
            or not 1 <= len(expected_job_fingerprint) <= 128
        ):
            raise EmployerSubmitClaimDenied("Verified owner and saved review revision required")
        try:
            _posting_url(expected_application_url)
        except (HandoffError, TypeError) as exc:
            raise EmployerSubmitClaimDenied("Verified HTTPS Lever employer URL required") from exc
        employer_key = _employer_job_key_sha256(expected_application_url)

        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('lock_timeout', '5000ms', true)")
                key, cv, letter = verified_employer_submit_preflight(
                    cur, binding, workspace_id=workspace_id,
                    expected_revision=expected_revision,
                    expected_application_url=expected_application_url,
                    expected_job_fingerprint=expected_job_fingerprint,
                )

                claim_id = "employer-claim-" + uuid4().hex
                document_hash = sha256((cv + "\0" + letter).encode("utf-8")).hexdigest()
                url_hash = sha256(expected_application_url.encode("utf-8")).hexdigest()
                cur.execute(
                    """INSERT INTO smartploy_employer_submit_claims
                       (claim_id,user_id,profile_id,canonical_key,workspace_id,
                        document_revision,document_sha256,application_url_sha256,
                        employer_job_key_sha256,state)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'reserved_unverified')
                       ON CONFLICT DO NOTHING
                       RETURNING claim_id""",
                    (claim_id, binding.user_id, binding.profile_id, key, workspace_id,
                     expected_revision, document_hash, url_hash, employer_key),
                )
                inserted = cur.fetchone() is not None
                cur.execute(
                    self._select() + """ WHERE user_id=%s AND profile_id=%s
                       AND (canonical_key=%s OR employer_job_key_sha256=%s)
                       ORDER BY created_at ASC, claim_id ASC LIMIT 1""",
                    (binding.user_id, binding.profile_id, key, employer_key),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Claim insert/read inconsistent")
        return self._read(row), inserted

    def mark_uncertain(
        self, binding: UserProfileBinding, claim_id: str, *, code: str,
    ) -> EmployerSubmitClaim:
        if code not in {"browser_error", "timeout", "unknown_outcome"}:
            raise EmployerSubmitClaimDenied("Only sanitized failure codes permitted")
        if not claim_id or not binding.user_id or not binding.profile_id:
            raise EmployerSubmitClaimDenied("Owner-scoped claim ID required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE smartploy_employer_submit_claims
                       SET state='uncertain', failure_code=%s, updated_at=now()
                       WHERE claim_id=%s AND user_id=%s AND profile_id=%s
                         AND state='reserved_unverified'""",
                    (code, claim_id, binding.user_id, binding.profile_id),
                )
                cur.execute(
                    self._select() + " WHERE claim_id=%s AND user_id=%s AND profile_id=%s",
                    (claim_id, binding.user_id, binding.profile_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise EmployerSubmitClaimDenied("Claim not found for owner")
                claim = self._read(row)
                if claim.state != "uncertain" or claim.failure_code != code:
                    raise EmployerSubmitClaimDenied("A claim cannot be reset or relabeled")
        return claim

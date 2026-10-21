"""SP15e employer final-action policy: independent of job source access rights.

Reuses SP15a employer-job identity and PostgreSQL transaction. Legal/source
evidence must be reviewed out-of-band by TWO distinct authorized operators,
then loaded through controlled migrations/operations, NOT by applicants.
No API can set rights, and no browser or account gets blanket authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg import connect

from .browser_handoff import HandoffError, _posting_url
from .employer_submit_claim_storage import (
    EmployerSubmitClaimDenied, _employer_job_key_sha256,
)

ACTION = "single_user_initiated_browser_final_submit"
LEVER_API_ACTION = "partner_lever_postings_api_submit"
ALLOWED_ACTIONS = frozenset({ACTION, LEVER_API_ACTION})
BASES = frozenset({
    "explicit_employer_authorization", "documented_partner_integration",
})


class EmployerRightsDenied(ValueError):
    """No reviewed, current, exact-employer permission for final action."""


@dataclass(frozen=True)
class ReviewedEmployerRights:
    employer_job_key_sha256: str
    permission_basis: str
    permission_evidence_sha256: str
    terms_evidence_sha256: str
    expires_at: datetime

    def public_status(self) -> dict[str, object]:
        # Do not disclose audit identities/document hashes to applicants.
        return {
            "operator_permission_reviewed": True,
            "permission_basis": self.permission_basis,
            "permission_expires_at": self.expires_at.isoformat(),
            "employer_submission_performed": False,
            "final_browser_click_authorized": False,
        }


def employer_job_key(application_url: str) -> str:
    try:
        _posting_url(application_url)
        return _employer_job_key_sha256(application_url)
    except (HandoffError, EmployerSubmitClaimDenied, TypeError) as exc:
        raise EmployerRightsDenied("Verified HTTPS employer application URL required") from exc


def approved_employer_rights_locked(
    cur, employer_job_key_sha256: str, *, action_scope: str = ACTION,
) -> ReviewedEmployerRights:
    """Must run in the SAME transaction as final approval/one-shot claim.

    FOR SHARE prevents permission revocation overtaking an in-flight
    reservation before commit. Approval is evidence, not independent legal
    proof: authorized reviewers must inspect the original signed documents.
    No SourcePolicy table, candidate text or user-supplied flag qualifies.
    """
    if (
        not isinstance(employer_job_key_sha256, str)
        or len(employer_job_key_sha256) != 64
        or any(c not in "0123456789abcdef" for c in employer_job_key_sha256)
    ):
        raise EmployerRightsDenied("Exact employer job identity required")
    if action_scope not in ALLOWED_ACTIONS:
        raise EmployerRightsDenied("Unrecognized employer submission channel")
    cur.execute(
        """SELECT permission_basis,permission_evidence_sha256,
                  terms_evidence_sha256,expires_at
           FROM smartploy_employer_automation_rights
           WHERE employer_job_key_sha256=%s
             AND action_scope=%s AND state='approved'
             AND permission_basis IN (
                  'explicit_employer_authorization','documented_partner_integration'
             )
             AND reviewed_by<>independently_approved_by
             AND reviewed_at<=now() AND expires_at>now()
           FOR SHARE""",
        (employer_job_key_sha256, action_scope),
    )
    row = cur.fetchone()
    if row is None:
        raise EmployerRightsDenied(
            "Independent, current employer automation permission has not been attested"
        )
    if (
        str(row[0]) not in BASES
        or any(not isinstance(v, str) or len(v) != 64 for v in (row[1], row[2]))
    ):
        raise EmployerRightsDenied("Invalid employer rights evidence")
    return ReviewedEmployerRights(
        employer_job_key_sha256=employer_job_key_sha256,
        permission_basis=str(row[0]),
        permission_evidence_sha256=str(row[1]),
        terms_evidence_sha256=str(row[2]),
        expires_at=row[3],
    )


class PostgresEmployerAutomationRightsRepository:
    """Read ONLY. No grant or administrative write API is provided."""

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL required for independent rights attestations")

    def inspect(self, application_url: str, *, action_scope: str = ACTION) -> dict[str, object]:
        key = employer_job_key(application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                try:
                    rights = approved_employer_rights_locked(cur, key, action_scope=action_scope)
                except EmployerRightsDenied:
                    return {
                        "operator_permission_reviewed": False,
                        "permission_basis": "",
                        "permission_expires_at": "",
                        "employer_submission_performed": False,
                        "final_browser_click_authorized": False,
                    }
        return rights.public_status()

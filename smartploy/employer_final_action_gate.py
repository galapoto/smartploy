"""SP15e: server-held, non-bearer final approval + one-shot claim boundary.

SOURCE ONLY. No API issues or consumes these records. The actual browser
transport, second user click and employer rights enforcement at the DOM
are separate unimplemented release gates. A consumed record proves only
a durable, single attempt reservation, NOT an employer submission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import re
from uuid import uuid4

from psycopg import connect

from .browser_handoff import _approved_contact, approved_fields_sha256
from .employer_automation_rights import (
    ACTION, ALLOWED_ACTIONS, EmployerRightsDenied, approved_employer_rights_locked, employer_job_key,
)
from .employer_review_intent_storage import PostgresEmployerReviewIntentRepository
from .employer_submit_claim_storage import (
    EmployerSubmitClaim, EmployerSubmitClaimDenied,
    reserve_employer_claim_locked, verified_employer_submit_preflight,
)
from .identity import UserProfileBinding
from .profile import CandidateProfile, ProfileFact

SHA = re.compile(r"^[a-f0-9]{64}$")
FINAL_APPROVAL_LIFETIME_SECONDS = 90


class EmployerFinalActionDenied(ValueError):
    """No user-approved, rights-reviewed, current single employer action."""


@dataclass(frozen=True)
class EmployerFinalApproval:
    approval_id: str
    user_id: str
    profile_id: str
    employer_job_key_sha256: str
    workspace_id: str
    revision: int
    document_sha256: str
    cv_pdf_sha256: str
    approved_fields_sha256: str
    application_url_sha256: str
    permission_evidence_sha256: str
    state: str
    created_at: datetime
    expires_at: datetime
    updated_at: datetime
    action_scope: str = ACTION

    def public_status(self, *, workspace_id: str, revision: int) -> dict[str, object]:
        return {
            "approval_recorded": (
                self.state == "approved"
                and self.workspace_id == workspace_id
                and self.revision == revision
                and self.expires_at > datetime.now(self.expires_at.tzinfo)
            ),
            "approval_state": self.state,
            "expires_at": self.expires_at.isoformat() if self.state == "approved" else "",
            "final_browser_click_authorized": False,
            "employer_submission_performed": False,
            "employer_receipt_verified": False,
        }


@dataclass(frozen=True)
class FinalActionReservation:
    """A durable internal record, intentionally NOT a browser-click grant."""

    approval_id: str
    claim: EmployerSubmitClaim

    def public_status(self) -> dict[str, object]:
        return {
            "approval_state": "consumed_unverified",
            "employer_attempt_reserved": True,
            "automatic_retry_authorized": False,
            "final_browser_click_authorized": False,
            "employer_submission_verified": False,
        }


def _request_checks(
    binding: UserProfileBinding, workspace_id: str,
    expected_revision: int, expected_document_sha256: str,
    expected_cv_pdf_sha256: str, expected_fields_sha256: str,
    expected_application_url: str,
) -> str:
    if (
        not isinstance(binding, UserProfileBinding)
        or binding.status != "active"
        or not binding.user_id.startswith("usr-")
        or not binding.profile_id
        or not isinstance(workspace_id, str) or not 1 <= len(workspace_id) <= 160
        or type(expected_revision) is not int or expected_revision <= 0
        or any(
            not isinstance(digest, str) or not SHA.fullmatch(digest)
            for digest in (
                expected_document_sha256, expected_cv_pdf_sha256,
                expected_fields_sha256,
            )
        )
    ):
        raise EmployerFinalActionDenied("Exact owner, document, PDF and final review required")
    try:
        return employer_job_key(expected_application_url)
    except EmployerRightsDenied as exc:
        raise EmployerFinalActionDenied(str(exc)) from exc


def _approved_fields_locked(cur, binding: UserProfileBinding, letter: str) -> str:
    """Reuse approved-contact mapping, but read fresh owner-scoped facts in TX.

    Locks existing rows. A future browser grant must still recheck permission,
    account and exact fields at the real click boundary.
    """
    cur.execute(
        """SELECT fact_type,value FROM smartploy_profile_facts
           WHERE profile_id=%s AND approved=true
           ORDER BY fact_type,value FOR SHARE""",
        (binding.profile_id,),
    )
    facts = tuple(
        ProfileFact(str(row[0]), str(row[1]), "reviewed-storage", approved=True)
        for row in cur.fetchall()
    )
    approved = _approved_contact(CandidateProfile(binding.profile_id, facts))
    if (
        not approved["full_name"]
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", approved["email"])
    ):
        raise EmployerFinalActionDenied("Approved applicant name and email are required")
    return approved_fields_sha256({**approved, "cover_letter": letter[:10000]})


def _review_locked(
    cur, binding: UserProfileBinding, *,
    employer_hash: str, workspace_id: str,
    expected_revision: int, expected_doc: str,
    expected_pdf: str,
) -> None:
    cur.execute(
        PostgresEmployerReviewIntentRepository._select() + """
            WHERE user_id=%s AND profile_id=%s AND employer_job_key_sha256=%s
            FOR UPDATE
        """,
        (binding.user_id, binding.profile_id, employer_hash),
    )
    row = cur.fetchone()
    if row is None:
        raise EmployerFinalActionDenied("A separate, signed-in CV and job review is required")
    current = PostgresEmployerReviewIntentRepository._item(row)
    cur.execute("SELECT now()")
    now = cur.fetchone()[0]
    if (
        current.state != "pending"
        or current.expires_at <= now
        or current.workspace_id != workspace_id
        or current.revision != expected_revision
        or current.document_sha256 != expected_doc
        or current.cv_pdf_sha256 != expected_pdf
    ):
        raise EmployerFinalActionDenied("Applicant review changed, expired or was cancelled")


class PostgresEmployerFinalActionGate:
    """Only internal one-shot state. No applicant- or extension-callable route."""

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL is mandatory for cross-device final authorization")

    @staticmethod
    def _select() -> str:
        return """SELECT approval_id,user_id,profile_id,employer_job_key_sha256,
                         workspace_id,document_revision,document_sha256,cv_pdf_sha256,
                         approved_fields_sha256,application_url_sha256,
                         permission_evidence_sha256,state,created_at,expires_at,updated_at,
                         action_scope
                  FROM smartploy_employer_final_approvals"""

    @staticmethod
    def _item(row) -> EmployerFinalApproval:
        return EmployerFinalApproval(
            approval_id=str(row[0]),user_id=str(row[1]),profile_id=str(row[2]),
            employer_job_key_sha256=str(row[3]),workspace_id=str(row[4]),
            revision=int(row[5]),document_sha256=str(row[6]),
            cv_pdf_sha256=str(row[7]),approved_fields_sha256=str(row[8]),
            application_url_sha256=str(row[9]),
            permission_evidence_sha256=str(row[10]),state=str(row[11]),
            created_at=row[12],expires_at=row[13],updated_at=row[14],
            action_scope=str(row[15]),
        )

    def approve(
        self, binding: UserProfileBinding, *,
        workspace_id: str, expected_revision: int,
        expected_application_url: str, expected_job_fingerprint: str,
        expected_document_sha256: str, expected_cv_pdf_sha256: str,
        expected_fields_sha256: str,
        explicit_final_user_approval: bool,
        acknowledge_external_employer_transfer: bool,
        action_scope: str = ACTION,
    ) -> tuple[EmployerFinalApproval, bool]:
        """Store bounded final USER intent; DOES NOT authorize an external click.

        Requires a separate earlier SP15c review, exact current applicant and
        independently attested provider rights. No session or raw document
        is accepted or stored. The future trusted browser adapter must later
        consume this exact approval atomically, after fresh user action.
        """
        if (
            explicit_final_user_approval is not True
            or acknowledge_external_employer_transfer is not True
        ):
            raise EmployerFinalActionDenied(
                "Fresh applicant final approval and external-transfer acknowledgement required"
            )
        if action_scope not in ALLOWED_ACTIONS:
            raise EmployerFinalActionDenied("Unsupported final action channel")
        employer_hash = _request_checks(
            binding,workspace_id,expected_revision,expected_document_sha256,
            expected_cv_pdf_sha256,expected_fields_sha256,expected_application_url,
        )
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('lock_timeout','5000ms',true)")
                try:
                    key, cv, letter = verified_employer_submit_preflight(
                        cur,binding,workspace_id=workspace_id,
                        expected_revision=expected_revision,
                        expected_application_url=expected_application_url,
                        expected_job_fingerprint=expected_job_fingerprint,
                    )
                    rights = approved_employer_rights_locked(cur,employer_hash, action_scope=action_scope)
                except (EmployerSubmitClaimDenied,EmployerRightsDenied) as exc:
                    raise EmployerFinalActionDenied(str(exc)) from exc
                doc_hash = sha256((cv+"\0"+letter).encode("utf-8")).hexdigest()
                if doc_hash != expected_document_sha256:
                    raise EmployerFinalActionDenied("Reviewed CV and letter fingerprint drift")
                fields_hash = _approved_fields_locked(cur,binding,letter)
                if fields_hash != expected_fields_sha256:
                    raise EmployerFinalActionDenied("Approved contact or letter changed")
                _review_locked(
                    cur,binding,employer_hash=employer_hash,
                    workspace_id=workspace_id,expected_revision=expected_revision,
                    expected_doc=doc_hash,expected_pdf=expected_cv_pdf_sha256,
                )
                cur.execute(
                    """SELECT 1 FROM smartploy_employer_submit_claims
                       WHERE user_id=%s AND profile_id=%s
                         AND (canonical_key=%s OR employer_job_key_sha256=%s)""",
                    (binding.user_id,binding.profile_id,key,employer_hash),
                )
                if cur.fetchone():
                    raise EmployerFinalActionDenied(
                        "A sticky employer attempt already requires reconciliation"
                    )
                approval_id="final-approval-"+uuid4().hex
                url_hash=sha256(expected_application_url.encode("utf-8")).hexdigest()
                cur.execute(
                    """INSERT INTO smartploy_employer_final_approvals
                       (approval_id,user_id,profile_id,employer_job_key_sha256,
                        workspace_id,document_revision,document_sha256,cv_pdf_sha256,
                        approved_fields_sha256,application_url_sha256,
                        permission_evidence_sha256,action_scope,state,expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',
                               now()+interval '90 seconds')
                       ON CONFLICT (user_id,profile_id,employer_job_key_sha256)
                       DO UPDATE SET
                         approval_id=EXCLUDED.approval_id,
                         workspace_id=EXCLUDED.workspace_id,
                         document_revision=EXCLUDED.document_revision,
                         document_sha256=EXCLUDED.document_sha256,
                         cv_pdf_sha256=EXCLUDED.cv_pdf_sha256,
                         approved_fields_sha256=EXCLUDED.approved_fields_sha256,
                         application_url_sha256=EXCLUDED.application_url_sha256,
                         permission_evidence_sha256=EXCLUDED.permission_evidence_sha256,
                         action_scope=EXCLUDED.action_scope,
                         state='approved',created_at=now(),
                         expires_at=now()+interval '90 seconds',updated_at=now()
                       WHERE smartploy_employer_final_approvals.state='cancelled'
                          OR (
                            smartploy_employer_final_approvals.state='approved'
                            AND smartploy_employer_final_approvals.expires_at<=now()
                          )
                       RETURNING approval_id""",
                    (approval_id,binding.user_id,binding.profile_id,employer_hash,
                     workspace_id,expected_revision,doc_hash,expected_cv_pdf_sha256,
                     fields_hash,url_hash,rights.permission_evidence_sha256,action_scope),
                )
                inserted = cur.fetchone() is not None
                cur.execute(
                    self._select()+"""
                        WHERE user_id=%s AND profile_id=%s
                          AND employer_job_key_sha256=%s
                    """,(binding.user_id,binding.profile_id,employer_hash),
                )
                row=cur.fetchone()
                if row is None:
                    raise RuntimeError("Final approval insertion missing")
                item=self._item(row)
                if not inserted and (
                    item.state!="approved"
                    or item.workspace_id!=workspace_id
                    or item.revision!=expected_revision
                    or item.document_sha256!=doc_hash
                    or item.cv_pdf_sha256!=expected_cv_pdf_sha256
                    or item.approved_fields_sha256!=fields_hash
                    or item.application_url_sha256!=url_hash
                    or item.permission_evidence_sha256!=rights.permission_evidence_sha256
                    or item.action_scope!=action_scope
                ):
                    raise EmployerFinalActionDenied(
                        "A different final approval exists. Cancel before creating another."
                    )
        return item,inserted

    def get(self,binding:UserProfileBinding,application_url:str)->EmployerFinalApproval|None:
        key=_request_checks(binding,"read-only",1,"a"*64,"a"*64,"a"*64,application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select()+"""
                      WHERE user_id=%s AND profile_id=%s
                        AND employer_job_key_sha256=%s
                    """,(binding.user_id,binding.profile_id,key),
                )
                row=cur.fetchone()
        return self._item(row) if row else None

    def cancel(self,binding:UserProfileBinding,application_url:str)->EmployerFinalApproval|None:
        key=_request_checks(binding,"cancel-only",1,"a"*64,"a"*64,"a"*64,application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE smartploy_employer_final_approvals
                       SET state='cancelled',updated_at=now()
                       WHERE user_id=%s AND profile_id=%s
                         AND employer_job_key_sha256=%s AND state='approved'""",
                    (binding.user_id,binding.profile_id,key),
                )
                cur.execute(
                    self._select()+"""
                      WHERE user_id=%s AND profile_id=%s
                        AND employer_job_key_sha256=%s
                    """,(binding.user_id,binding.profile_id,key),
                )
                row=cur.fetchone()
        return self._item(row) if row else None

    def consume_once_for_trusted_adapter(
        self,binding:UserProfileBinding, *,
        approval_id:str,workspace_id:str,expected_revision:int,
        expected_application_url:str,expected_job_fingerprint:str,
        expected_document_sha256:str,expected_cv_pdf_sha256:str,
        expected_fields_sha256:str,
        action_scope: str = ACTION,
    )->FinalActionReservation:
        """Internal durable handoff primitive; not exposed via HTTP/MV3.

        The future adapter MUST independently prove fresh signed-in browser
        ownership and site rights at the actual click. This method reserves
        exactly one sticky claim in the SAME transaction as approval consume.
        A successful return is not a browser authorization or employer receipt.
        """
        if action_scope not in ALLOWED_ACTIONS:
            raise EmployerFinalActionDenied("Unsupported final action channel")
        employer_hash=_request_checks(
            binding,workspace_id,expected_revision,expected_document_sha256,
            expected_cv_pdf_sha256,expected_fields_sha256,expected_application_url,
        )
        if (
            not isinstance(approval_id,str)
            or not re.fullmatch(r"final-approval-[a-f0-9]{32}",approval_id)
        ):
            raise EmployerFinalActionDenied("Exact internally verified approval required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('lock_timeout','5000ms',true)")
                try:
                    key,cv,letter=verified_employer_submit_preflight(
                        cur,binding,workspace_id=workspace_id,
                        expected_revision=expected_revision,
                        expected_application_url=expected_application_url,
                        expected_job_fingerprint=expected_job_fingerprint,
                    )
                    rights=approved_employer_rights_locked(cur,employer_hash, action_scope=action_scope)
                except (EmployerSubmitClaimDenied,EmployerRightsDenied) as exc:
                    raise EmployerFinalActionDenied(str(exc)) from exc
                doc_hash=sha256((cv+"\0"+letter).encode("utf-8")).hexdigest()
                if doc_hash!=expected_document_sha256:
                    raise EmployerFinalActionDenied("Document changed after final approval")
                fields_hash=_approved_fields_locked(cur,binding,letter)
                if fields_hash!=expected_fields_sha256:
                    raise EmployerFinalActionDenied("Approved contact changed after final approval")
                _review_locked(
                    cur,binding,employer_hash=employer_hash,workspace_id=workspace_id,
                    expected_revision=expected_revision,
                    expected_doc=doc_hash,expected_pdf=expected_cv_pdf_sha256,
                )
                cur.execute(
                    self._select()+"""
                      WHERE approval_id=%s AND user_id=%s AND profile_id=%s
                        AND employer_job_key_sha256=%s
                        AND state='approved' AND expires_at>now()
                      FOR UPDATE
                    """,(approval_id,binding.user_id,binding.profile_id,employer_hash),
                )
                row=cur.fetchone()
                if row is None:
                    raise EmployerFinalActionDenied(
                        "Final approval expired, revoked, consumed or belongs to another account"
                    )
                approved=self._item(row)
                if (
                    approved.workspace_id!=workspace_id
                    or approved.revision!=expected_revision
                    or approved.document_sha256!=doc_hash
                    or approved.cv_pdf_sha256!=expected_cv_pdf_sha256
                    or approved.approved_fields_sha256!=fields_hash
                    or approved.application_url_sha256!=sha256(
                        expected_application_url.encode("utf-8")
                    ).hexdigest()
                    or approved.permission_evidence_sha256!=rights.permission_evidence_sha256
                    or approved.action_scope!=action_scope
                ):
                    raise EmployerFinalActionDenied(
                        "Final approval, employer rights, CV or job identity drifted"
                    )
                claim,inserted=reserve_employer_claim_locked(
                    cur,binding,canonical_key=key,workspace_id=workspace_id,
                    expected_revision=expected_revision,
                    expected_application_url=expected_application_url,
                    employer_job_key_sha256=employer_hash,
                    cv_text=cv,cover_letter_text=letter,
                )
                if not inserted:
                    raise EmployerFinalActionDenied(
                        "A previous employer attempt is sticky and can never be retried automatically"
                    )
                cur.execute(
                    """UPDATE smartploy_employer_final_approvals
                       SET state='consumed_unverified',updated_at=now()
                       WHERE approval_id=%s AND user_id=%s AND profile_id=%s
                         AND state='approved' RETURNING approval_id""",
                    (approval_id,binding.user_id,binding.profile_id),
                )
                if cur.fetchone() is None:
                    raise EmployerFinalActionDenied("Final approval could not be consumed atomically")
        return FinalActionReservation(approval_id=approval_id,claim=claim)

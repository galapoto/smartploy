"""SP15c: PostgreSQL-bound, expiring final-review intent; never submit authority.

Adapts first-party ObumAI's short-lived hashed state and Agent D's approval
vs execution separation. Reuses SmartPloy SP15a's exact transactional owner/
posting/document verification. Does not issue credentials to an extension,
click an employer control or reserve an employer submit attempt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import re
from uuid import uuid4

from psycopg import connect

from .browser_handoff import HandoffError, _assisted_posting_url
from .employer_submit_claim_storage import (
    EmployerSubmitClaimDenied, _employer_job_key_sha256,
    verified_employer_submit_preflight,
)
from .identity import UserProfileBinding

TTL_SECONDS = 10 * 60
_SHA = re.compile(r"^[0-9a-f]{64}$")


class EmployerReviewIntentDenied(ValueError):
    """The signed-in owner's exact reviewed job or document is no longer valid."""


@dataclass(frozen=True)
class EmployerReviewIntent:
    intent_id: str
    user_id: str
    profile_id: str
    employer_job_key_sha256: str
    workspace_id: str
    revision: int
    document_sha256: str
    cv_pdf_sha256: str
    state: str
    created_at: datetime
    expires_at: datetime
    updated_at: datetime

    def public_status(self, *, workspace_id: str, revision: int) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        state = "expired" if self.expires_at <= now and self.state == "pending" else self.state
        current = state == "pending" and self.workspace_id == workspace_id and self.revision == revision
        return {
            "review_recorded": current,
            "review_state": state,
            "expires_at": self.expires_at.isoformat() if current else "",
            "automatic_employer_submit_authorized": False,
            "external_actions_performed": False,
            "browser_grant_issued": False,
        }


class PostgresEmployerReviewIntentRepository:
    """Owner and job-scoped, revocable 10-minute review state with no bearer capability."""

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL is required for review state across devices")

    @staticmethod
    def _select() -> str:
        return """SELECT intent_id,user_id,profile_id,employer_job_key_sha256,
                         workspace_id,document_revision,document_sha256,
                         cv_pdf_sha256,state,created_at,expires_at,updated_at
                  FROM smartploy_employer_review_intents"""

    @staticmethod
    def _item(row) -> EmployerReviewIntent:
        return EmployerReviewIntent(
            intent_id=str(row[0]), user_id=str(row[1]), profile_id=str(row[2]),
            employer_job_key_sha256=str(row[3]), workspace_id=str(row[4]),
            revision=int(row[5]), document_sha256=str(row[6]),
            cv_pdf_sha256=str(row[7]), state=str(row[8]),
            created_at=row[9], expires_at=row[10], updated_at=row[11],
        )

    @staticmethod
    def _employer_key(application_url: str) -> str:
        try:
            _assisted_posting_url(application_url)
            return _employer_job_key_sha256(application_url)
        except (HandoffError, EmployerSubmitClaimDenied, TypeError) as exc:
            raise EmployerReviewIntentDenied("Unsupported employer job URL") from exc

    def get(
        self, binding: UserProfileBinding, application_url: str,
    ) -> EmployerReviewIntent | None:
        if binding.status != "active" or not binding.user_id or not binding.profile_id:
            raise EmployerReviewIntentDenied("Verified account required")
        key = self._employer_key(application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + """
                        WHERE user_id=%s AND profile_id=%s
                          AND employer_job_key_sha256=%s
                    """, (binding.user_id, binding.profile_id, key),
                )
                row = cur.fetchone()
        return self._item(row) if row else None

    def prepare(
        self, binding: UserProfileBinding, *,
        workspace_id: str, expected_revision: int,
        expected_application_url: str, expected_job_fingerprint: str,
        expected_document_sha256: str, expected_cv_pdf_sha256: str,
        explicit_user_review: bool, acknowledge_no_automatic_submit: bool,
    ) -> tuple[EmployerReviewIntent, bool]:
        if explicit_user_review is not True or acknowledge_no_automatic_submit is not True:
            raise EmployerReviewIntentDenied("Two explicit final-review acknowledgements are required")
        if (
            type(expected_revision) is not int or expected_revision < 1
            or not isinstance(expected_document_sha256, str)
            or not _SHA.fullmatch(expected_document_sha256)
            or not isinstance(expected_cv_pdf_sha256, str)
            or not _SHA.fullmatch(expected_cv_pdf_sha256)
        ):
            raise EmployerReviewIntentDenied("Exact reviewed CV/PDF digests and revision required")
        employer_key = self._employer_key(expected_application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('lock_timeout','5000ms',true)")
                # Shared preflight locks owner -> workspace -> live job, in the
                # same order as SP15a claims and account-erasure quarantine.
                try:
                    canonical_key, cv_text, letter_text = verified_employer_submit_preflight(
                        cur, binding, workspace_id=workspace_id,
                        expected_revision=expected_revision,
                        expected_application_url=expected_application_url,
                        expected_job_fingerprint=expected_job_fingerprint,
                        assisted_review_only=True,
                    )
                except EmployerSubmitClaimDenied as exc:
                    raise EmployerReviewIntentDenied(str(exc)) from exc
                reviewed = sha256((cv_text + "\0" + letter_text).encode("utf-8")).hexdigest()
                if reviewed != expected_document_sha256:
                    raise EmployerReviewIntentDenied("Reviewed application digest changed")
                cur.execute(
                    """SELECT 1 FROM smartploy_employer_submit_claims
                       WHERE user_id=%s AND profile_id=%s
                         AND (canonical_key=%s OR employer_job_key_sha256=%s)""",
                    (binding.user_id, binding.profile_id, canonical_key, employer_key),
                )
                if cur.fetchone():
                    raise EmployerReviewIntentDenied(
                        "An employer submit attempt already exists and requires reconciliation"
                    )
                new_id = "review-intent-" + uuid4().hex
                cur.execute(
                    """INSERT INTO smartploy_employer_review_intents (
                         intent_id,user_id,profile_id,employer_job_key_sha256,
                         workspace_id,document_revision,document_sha256,cv_pdf_sha256,
                         state,expires_at
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending',
                                 now()+interval '10 minutes')
                       ON CONFLICT (user_id,profile_id,employer_job_key_sha256)
                       DO UPDATE SET
                         intent_id=EXCLUDED.intent_id,workspace_id=EXCLUDED.workspace_id,
                         document_revision=EXCLUDED.document_revision,
                         document_sha256=EXCLUDED.document_sha256,
                         cv_pdf_sha256=EXCLUDED.cv_pdf_sha256,
                         state='pending',created_at=now(),
                         expires_at=now()+interval '10 minutes',updated_at=now()
                       WHERE smartploy_employer_review_intents.expires_at<=now()
                          OR smartploy_employer_review_intents.state='cancelled'
                       RETURNING intent_id""",
                    (
                        new_id,binding.user_id,binding.profile_id,employer_key,
                        workspace_id,expected_revision,reviewed,expected_cv_pdf_sha256,
                    ),
                )
                inserted_or_replaced = cur.fetchone() is not None
                cur.execute(
                    self._select() + """
                        WHERE user_id=%s AND profile_id=%s
                          AND employer_job_key_sha256=%s""",
                    (binding.user_id,binding.profile_id,employer_key),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Review state was not persisted")
                item = self._item(row)
                if not inserted_or_replaced and (
                    item.state != "pending"
                    or item.workspace_id != workspace_id
                    or item.revision != expected_revision
                    or item.document_sha256 != reviewed
                    or item.cv_pdf_sha256 != expected_cv_pdf_sha256
                ):
                    raise EmployerReviewIntentDenied(
                        "A different review is active. Cancel or allow it to expire."
                    )
        return item, inserted_or_replaced

    def cancel(
        self, binding: UserProfileBinding, *, application_url: str,
    ) -> EmployerReviewIntent | None:
        if binding.status != "active" or not binding.user_id or not binding.profile_id:
            raise EmployerReviewIntentDenied("Verified owner required")
        key = self._employer_key(application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE smartploy_employer_review_intents
                       SET state='cancelled',updated_at=now()
                       WHERE user_id=%s AND profile_id=%s
                         AND employer_job_key_sha256=%s
                         AND state='pending'
                       RETURNING intent_id""",
                    (binding.user_id,binding.profile_id,key),
                )
                cur.fetchone()
                cur.execute(
                    self._select() + """
                        WHERE user_id=%s AND profile_id=%s
                          AND employer_job_key_sha256=%s""",
                    (binding.user_id,binding.profile_id,key),
                )
                row = cur.fetchone()
        return self._item(row) if row else None


    def verify_for_companion(
        self, binding: UserProfileBinding, *,
        workspace_id: str, expected_revision: int,
        expected_application_url: str, expected_job_fingerprint: str,
        expected_document_sha256: str, expected_cv_pdf_sha256: str,
    ) -> EmployerReviewIntent:
        """Recheck signed-in review against current employer/job/documents.

        Read-only authority: a positive result permits presentation of an
        existing reviewed contact/CV autofill packet, NEVER a final submit.
        Reuses the *identical* SP15a transactional preflight/lock ordering.
        """
        if (
            type(expected_revision) is not int or expected_revision < 1
            or not isinstance(expected_document_sha256, str)
            or not _SHA.fullmatch(expected_document_sha256)
            or not isinstance(expected_cv_pdf_sha256, str)
            or not _SHA.fullmatch(expected_cv_pdf_sha256)
        ):
            raise EmployerReviewIntentDenied("Invalid exact reviewed packet identity")
        employer_key = self._employer_key(expected_application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('lock_timeout','5000ms',true)")
                try:
                    canonical_key, cv_text, letter_text = verified_employer_submit_preflight(
                        cur, binding, workspace_id=workspace_id,
                        expected_revision=expected_revision,
                        expected_application_url=expected_application_url,
                        expected_job_fingerprint=expected_job_fingerprint,
                        assisted_review_only=True,
                    )
                except EmployerSubmitClaimDenied as exc:
                    raise EmployerReviewIntentDenied(str(exc)) from exc
                latest_doc = sha256((cv_text + "\0" + letter_text).encode("utf-8")).hexdigest()
                if latest_doc != expected_document_sha256:
                    raise EmployerReviewIntentDenied("Reviewed documents changed")
                cur.execute(
                    self._select() + """
                      WHERE user_id=%s AND profile_id=%s
                        AND employer_job_key_sha256=%s FOR UPDATE
                    """,
                    (binding.user_id, binding.profile_id, employer_key),
                )
                row = cur.fetchone()
                if row is None:
                    raise EmployerReviewIntentDenied(
                        "Record a signed-in review on SmartPloy first"
                    )
                item = self._item(row)
                cur.execute("SELECT now()")
                current_db_time = cur.fetchone()[0]
                if (
                    item.state != "pending" or item.expires_at <= current_db_time
                    or item.workspace_id != workspace_id
                    or item.revision != expected_revision
                    or item.document_sha256 != latest_doc
                    or item.cv_pdf_sha256 != expected_cv_pdf_sha256
                ):
                    raise EmployerReviewIntentDenied(
                        "Review cancelled, expired or inconsistent with this application"
                    )
                cur.execute(
                    """SELECT 1 FROM smartploy_employer_submit_claims
                       WHERE user_id=%s AND profile_id=%s
                         AND (canonical_key=%s OR employer_job_key_sha256=%s)""",
                    (binding.user_id, binding.profile_id, canonical_key, employer_key),
                )
                if cur.fetchone():
                    raise EmployerReviewIntentDenied(
                        "A previous employer submission attempt requires reconciliation"
                    )
        return item

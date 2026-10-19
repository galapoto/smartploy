"""SP15f: authenticated Lever partner POSTING-API transport (not page scraping).

Reuses SmartPloy's deterministic CV PDF and two-person employer rights ledger.
A POST is possible ONLY for the exact partner-approved posting, with an
employer-issued API key in server environment and an already consumed durable
one-shot applicant approval/claim. Never retry an ambiguous provider result.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from urllib.parse import urlsplit

import httpx
from psycopg import connect

from .browser_handoff import HandoffError, _posting_url
from .employer_automation_rights import LEVER_API_ACTION, employer_job_key
from .employer_submit_claim_storage import EmployerSubmitClaim
from .identity import UserProfileBinding

_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_KEY_ENV = re.compile(r"^SMARTPLOY_LEVER_PARTNER_KEY_[A-Z0-9_]{3,80}$")
_APPLICATION_ID = re.compile(r"^[A-Za-z0-9_-]{8,160}$")
MAX_PDF = 2 * 1024 * 1024


class LeverPartnerUnavailable(ValueError):
    """No explicitly supported partner posting with reviewed standard form."""


class LeverPartnerUncertain(RuntimeError):
    """An already-reserved application attempt lacks a trustworthy provider ID."""

    def __init__(self, code: str = "unknown_outcome") -> None:
        self.code = code if code in {"timeout", "unknown_outcome"} else "unknown_outcome"
        super().__init__("Partner response not verified; do not retry automatically")


@dataclass(frozen=True)
class PartnerPosting:
    site: str
    posting_id: str
    region: str
    form_review_sha256: str
    api_key_env: str
    consent_policy_reviewed: bool

    @property
    def api_root(self) -> str:
        return "https://api.eu.lever.co" if self.region == "eu" else "https://api.lever.co"

    @property
    def api_path(self) -> str:
        return "/v0/postings/" + self.site + "/" + self.posting_id

    def key(self) -> str:
        key = os.getenv(self.api_key_env, "").strip()
        if not 16 <= len(key) <= 512 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise LeverPartnerUnavailable("Employer-issued API credential unavailable")
        return key


@dataclass(frozen=True)
class PartnerAcknowledgment:
    application_id: str

    def public_status(self) -> dict[str, object]:
        return {
            "provider": "lever", "provider_application_id": self.application_id,
            "provider_application_acknowledged": True,
            "employer_hiring_decision_verified": False,
            "automatic_retry_authorized": False,
        }


class LeverPartnerRegistry:
    """Opt-in exact posting config; no wildcard company, domain or user key."""

    def __init__(self, records: dict[str, PartnerPosting]) -> None:
        self._records = dict(records)

    @classmethod
    def from_env(cls) -> LeverPartnerRegistry:
        raw = os.getenv("SMARTPLOY_LEVER_PARTNER_JOBS_JSON", "").strip()
        if not raw:
            return cls({})
        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("Lever partner settings must be valid JSON") from exc
        if not isinstance(data, dict) or len(data) > 500:
            raise ValueError("Invalid bounded Lever partner posting map")
        out: dict[str, PartnerPosting] = {}
        for k, v in data.items():
            if (
                not isinstance(k, str) or len(k.split("/")) != 2
                or not all(_ID.fullmatch(p) for p in k.split("/"))
                or not isinstance(v, dict)
                or set(v) != {
                    "region","form_review_sha256","api_key_env",
                    "standard_form_only_reviewed","consent_policy_reviewed",
                }
            ):
                raise ValueError("Every partner must define a precise reviewed posting")
            site, posting_id = k.split("/")
            if (
                v["region"] not in {"global", "eu"}
                or not isinstance(v["form_review_sha256"], str)
                or not _SHA.fullmatch(v["form_review_sha256"])
                or not isinstance(v["api_key_env"], str)
                or not _KEY_ENV.fullmatch(v["api_key_env"])
                or v["standard_form_only_reviewed"] is not True
                or v["consent_policy_reviewed"] is not True
            ):
                raise ValueError("Partner posting lacks valid form and consent review")
            normalized = site.casefold() + "/" + posting_id.casefold()
            if normalized in out:
                raise ValueError("Duplicate normalized employer posting")
            out[normalized] = PartnerPosting(
                site=site, posting_id=posting_id, region=v["region"],
                form_review_sha256=v["form_review_sha256"],
                api_key_env=v["api_key_env"], consent_policy_reviewed=True,
            )
        return cls(out)

    def match(self, application_url: str) -> PartnerPosting:
        try:
            _posting_url(application_url)
        except (HandoffError, TypeError) as exc:
            raise LeverPartnerUnavailable("Only exact HTTPS Lever jobs are supported") from exc
        path = urlsplit(application_url)
        if path.query or path.fragment:
            raise LeverPartnerUnavailable("Partner application URLs must be exact and untracked")
        site, posting = path.path.strip("/").split("/")[:2]
        k = site.casefold() + "/" + posting.casefold()
        record = self._records.get(k)
        if (
            record is None
            or record.site != site or record.posting_id != posting
            or (path.hostname == "jobs.eu.lever.co") != (record.region == "eu")
        ):
            raise LeverPartnerUnavailable("This job has no reviewed employer API integration")
        record.key()
        return record

    def public_readiness(self, application_url: str) -> dict[str, object]:
        try:
            self.match(application_url)
            available = True
        except LeverPartnerUnavailable:
            available = False
        return {
            "partner_api_configured": available,
            "provider": "lever" if available else "",
            "no_custom_questions_reviewed": available,
            "partner_submission_authorized": False,
            "employer_action_performed": False,
        }


class LeverPartnerTransport:
    """No arbitrary domains, redirect following, logs, background retries or scraping."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def send(
        self, posting: PartnerPosting, *, application_url: str,
        fields: dict[str, str], pdf: bytes,
    ) -> PartnerAcknowledgment:
        if (
            not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-")
            or not 12 <= len(pdf) <= MAX_PDF
            or not fields.get("full_name", "").strip()
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", fields.get("email", ""))
            or not fields.get("cover_letter", "").strip()
        ):
            raise LeverPartnerUnavailable("Reviewed approved name, email, letter and PDF required")
        if not application_url.startswith(
            ("https://jobs.lever.co/", "https://jobs.eu.lever.co/")
        ):
            raise LeverPartnerUnavailable("Employer URL not approved")
        if (urlsplit(application_url).path.strip("/").split("/")[:2] !=
                [posting.site, posting.posting_id]):
            raise LeverPartnerUnavailable("Posting changed before transfer")
        secret = posting.key()
        host = posting.api_root
        with httpx.Client(
            base_url=host, transport=self._transport, trust_env=False,
            follow_redirects=False, timeout=httpx.Timeout(9.0, connect=3.0),
            headers={"Accept": "application/json", "User-Agent": "SmartPloy-PartnerApply/1"},
        ) as client:
            try:
                # Lever API does NOT expose custom required questions: exact
                # partner form review is mandatory before configuring this job.
                lookup = client.get(posting.api_path, params={"mode": "json"})
                if lookup.status_code != 200:
                    raise LeverPartnerUncertain()
                posting_json = lookup.json()
                if (
                    not isinstance(posting_json, dict)
                    or posting_json.get("id") != posting.posting_id
                    or posting_json.get("applyUrl", "").rstrip("/") != application_url.rstrip("/")
                ):
                    raise LeverPartnerUncertain()
                data = {
                    "name": fields["full_name"],
                    "email": fields["email"],
                    "comments": fields["cover_letter"],
                    "silent": "false",
                }
                if fields.get("phone"):
                    data["phone"] = fields["phone"]
                if fields.get("linkedin"):
                    data["urls[LinkedIn]"] = fields["linkedin"]
                if fields.get("github"):
                    data["urls[GitHub]"] = fields["github"]
                response = client.post(
                    posting.api_path,
                    params={"key": secret},
                    data=data,
                    files={"resume": ("smartploy-reviewed-cv.pdf", pdf, "application/pdf")},
                )
                if response.status_code != 200:
                    raise LeverPartnerUncertain()
                result = response.json()
                if (
                    not isinstance(result, dict) or result.get("ok") is not True
                    or not isinstance(result.get("applicationId"), str)
                    or not _APPLICATION_ID.fullmatch(result["applicationId"])
                ):
                    raise LeverPartnerUncertain()
                return PartnerAcknowledgment(application_id=result["applicationId"])
            except httpx.TimeoutException as exc:
                raise LeverPartnerUncertain("timeout") from None
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                # Do not include request URLs, secrets, candidate data, or
                # raw HTTP exception text in logs/response.
                raise LeverPartnerUncertain() from None


class PostgresPartnerApplicationReceipts:
    """Owner-scoped verified provider ACK, not a recruiter hiring decision."""

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL required for provider acknowledgment")

    def record(
        self, binding: UserProfileBinding, claim: EmployerSubmitClaim,
        acknowledgment: PartnerAcknowledgment,
    ) -> PartnerAcknowledgment:
        if (
            binding.user_id != claim.user_id or binding.profile_id != claim.profile_id
            or claim.state != "reserved_unverified"
            or not _APPLICATION_ID.fullmatch(acknowledgment.application_id)
        ):
            raise LeverPartnerUnavailable("Verified account and claim required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_partner_application_receipts
                       (claim_id,user_id,profile_id,workspace_id,
                        employer_job_key_sha256,provider,provider_application_id)
                       VALUES (%s,%s,%s,%s,%s,'lever',%s)
                       ON CONFLICT DO NOTHING RETURNING claim_id""",
                    (
                        claim.claim_id,binding.user_id,binding.profile_id,
                        claim.workspace_id,claim.employer_job_key_sha256,
                        acknowledgment.application_id,
                    ),
                )
                if cur.fetchone() is None:
                    raise LeverPartnerUnavailable("Provider receipt already recorded or conflicted")
        return acknowledgment

    def get(
        self, binding: UserProfileBinding, application_url: str,
    ) -> PartnerAcknowledgment | None:
        key = employer_job_key(application_url)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT provider_application_id FROM smartploy_partner_application_receipts
                       WHERE user_id=%s AND profile_id=%s AND employer_job_key_sha256=%s""",
                    (binding.user_id,binding.profile_id,key),
                )
                row = cur.fetchone()
        return PartnerAcknowledgment(application_id=str(row[0])) if row else None

"""SP51: exact-posting Ashby employer-PARTNER transport, NOT a public submit API.

This module is deliberately NOT registered in SmartPloy's HTTP API or worker.
The existing Lever-only two-reviewer rights, applicant review and one-shot
PostgreSQL claim currently cannot authorize an Ashby employer submission.
A later integration must extend those gates transactionally BEFORE calling
this transport. Never invoke from search, scraping, source polling or Agent Zero.

Reuse: official Ashby API; current reviewed SmartPloy CV PDF and contact
fingerprints; existing HTTPX and strict job-host URL validator.
No browser automation, login bypass, unsupported questions or retry.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
import re
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .browser_handoff import HandoffError, _assisted_posting_url

_API_ROOT = "https://api.ashbyhq.com"
_KEY_ENV = re.compile(r"^SMARTPLOY_ASHBY_PARTNER_KEY_[A-Z0-9_]{3,80}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PART = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MAX_PDF = 2 * 1024 * 1024
_MAX_FORM_BYTES = 256 * 1024
# Only fields for which SmartPloy already has reviewed applicant facts.
# Unknown questions, legal declarations and survey forms always require
# the original manual-assisted/human-review route.
_FIELDS: dict[str, frozenset[str]] = {
    "_systemfield_name": frozenset({"String"}),
    "_systemfield_email": frozenset({"Email"}),
    "_systemfield_resume": frozenset({"File"}),
    "_systemfield_phone": frozenset({"Phone", "String"}),
    "_systemfield_cover_letter": frozenset({"LongText", "String"}),
}
_REQUIRED = frozenset({
    "_systemfield_name", "_systemfield_email", "_systemfield_resume",
})
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class AshbyPartnerUnavailable(ValueError):
    """No approved exact posting/form/credential or unsupported question."""


class AshbyPartnerUncertain(RuntimeError):
    """Submission may have reached Ashby. NO automatic second POST."""

    def __init__(self, code: str = "unknown_outcome") -> None:
        self.code = code if code in {"timeout", "unknown_outcome"} else "unknown_outcome"
        super().__init__("Ashby provider outcome unverified; do not retry automatically")


def _valid_uuid(value: object) -> bool:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        return False
    try:
        return str(UUID(value)) == value.lower()
    except (TypeError, ValueError, AttributeError):
        return False


def _form_sha(value: dict[str, object]) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _exact_url(url: str) -> tuple[str, str]:
    try:
        _assisted_posting_url(url)
        parsed = urlsplit(url)
        if parsed.hostname != "jobs.ashbyhq.com" or parsed.query or parsed.fragment:
            raise ValueError
        parts = parsed.path.strip("/").split("/")
        if len(parts) not in {2, 3} or (
            len(parts) == 3 and parts[-1] != "application"
        ) or not _PART.fullmatch(parts[0]) or not _PART.fullmatch(parts[1]):
            raise ValueError
        return parts[0], parts[1]
    except (HandoffError, TypeError, ValueError, IndexError) as exc:
        raise AshbyPartnerUnavailable(
            "Exact hosted Ashby HTTPS job posting required"
        ) from exc


@dataclass(frozen=True)
class AshbyPartnerPosting:
    organization: str
    job_slug: str
    posting_id: str
    form_review_sha256: str
    api_key_env: str

    def key(self) -> str:
        value = os.getenv(self.api_key_env, "").strip()
        if (not _KEY_ENV.fullmatch(self.api_key_env)
                or not 16 <= len(value) <= 512
                or any(ord(char) < 33 or ord(char) > 126 for char in value)):
            raise AshbyPartnerUnavailable("Employer-issued Ashby API credential unavailable")
        return value


@dataclass(frozen=True)
class AshbyPartnerAcknowledgment:
    """Two official provider IDs: not a recruiter decision or employment offer."""

    submitted_form_instance_id: str
    application_id: str

    def public_status(self) -> dict[str, object]:
        return {
            "provider": "ashby",
            "provider_application_id": self.application_id,
            "provider_form_submission_id": self.submitted_form_instance_id,
            "provider_application_acknowledged": True,
            "employer_hiring_decision_verified": False,
            "automatic_retry_authorized": False,
        }


class AshbyPartnerRegistry:
    """Employer-issued keys for one exact, pre-reviewed Ashby posting only.

    The posting UUID is NOT inferred from a public URL slug. An operator must
    map the exact hosted URL to the separately approved official UUID after
    an independent posting/form/consent review. Config cannot grant rights.
    """

    def __init__(self, records: dict[str, AshbyPartnerPosting]) -> None:
        self._records = dict(records)

    @classmethod
    def from_env(cls) -> AshbyPartnerRegistry:
        raw = os.getenv("SMARTPLOY_ASHBY_PARTNER_POSTINGS_JSON", "").strip()
        if not raw:
            return cls({})
        try:
            items = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("Ashby partner configuration is not valid JSON") from exc
        if not isinstance(items, dict) or len(items) > 500:
            raise ValueError("Invalid bounded Ashby partner posting map")
        records: dict[str, AshbyPartnerPosting] = {}
        expected = {
            "posting_id", "form_review_sha256", "api_key_env",
            "standard_form_only_reviewed", "consent_policy_reviewed",
            "survey_forms_absent_reviewed",
        }
        for name, cfg in items.items():
            if not isinstance(name, str) or not isinstance(cfg, dict) or set(cfg) != expected:
                raise ValueError("Every Ashby partner needs a reviewed exact posting")
            parts = name.split("/")
            if (len(parts) != 2 or any(not _PART.fullmatch(x) for x in parts)
                    or not _valid_uuid(cfg["posting_id"])
                    or not isinstance(cfg["form_review_sha256"], str)
                    or not _SHA.fullmatch(cfg["form_review_sha256"])
                    or not isinstance(cfg["api_key_env"], str)
                    or not _KEY_ENV.fullmatch(cfg["api_key_env"])
                    or cfg["standard_form_only_reviewed"] is not True
                    or cfg["consent_policy_reviewed"] is not True
                    or cfg["survey_forms_absent_reviewed"] is not True):
                raise ValueError("Ashby partner posting lacks exact safe form approval")
            normalized = name.casefold()
            if normalized in records:
                raise ValueError("Duplicate normalized Ashby employer job")
            records[normalized] = AshbyPartnerPosting(
                organization=parts[0], job_slug=parts[1],
                posting_id=cfg["posting_id"].lower(),
                form_review_sha256=cfg["form_review_sha256"],
                api_key_env=cfg["api_key_env"],
            )
        return cls(records)

    def match(self, application_url: str) -> AshbyPartnerPosting:
        org, slug = _exact_url(application_url)
        posting = self._records.get((org + "/" + slug).casefold())
        if (posting is None or posting.organization != org
                or posting.job_slug != slug):
            raise AshbyPartnerUnavailable("No reviewed Ashby integration for this exact job")
        posting.key()
        return posting

    def public_readiness(self, application_url: str) -> dict[str, object]:
        try:
            self.match(application_url)
            available = True
        except AshbyPartnerUnavailable:
            available = False
        return {
            "partner_api_configured": available,
            "provider": "ashby" if available else "",
            "standard_form_reviewed": available,
            "partner_submission_authorized": False,
            "employer_action_performed": False,
        }


def _approved_form(
    info: object, posting: AshbyPartnerPosting, application_url: str,
) -> dict[str, object]:
    if not isinstance(info, dict) or info.get("success") is not True:
        raise AshbyPartnerUnavailable("Ashby posting could not be verified")
    data = info.get("results")
    if (not isinstance(data, dict)
            or data.get("id") != posting.posting_id
            or data.get("status") != "Published"
            or data.get("isListed") is not True):
        raise AshbyPartnerUnavailable("Ashby posting is not the reviewed live job")
    # Never infer a UUID from text, employer names or a different source link.
    try:
        observed_org, observed_slug = _exact_url(str(data.get("applyLink") or ""))
        intended_org, intended_slug = _exact_url(application_url)
    except AshbyPartnerUnavailable as exc:
        raise AshbyPartnerUnavailable("Ashby employer destination changed") from exc
    if (observed_org, observed_slug) != (intended_org, intended_slug):
        raise AshbyPartnerUnavailable("Ashby employer destination changed")
    if data.get("surveyFormDefinitions") != []:
        raise AshbyPartnerUnavailable("Ashby survey forms need human review")
    form = data.get("applicationFormDefinition")
    if (not isinstance(form, dict)
            or len(json.dumps(form, ensure_ascii=False).encode("utf-8")) > _MAX_FORM_BYTES
            or _form_sha(form) != posting.form_review_sha256):
        raise AshbyPartnerUnavailable("Ashby application form changed after independent review")
    sections = form.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
        raise AshbyPartnerUnavailable("Ashby form has unsupported structure")
    discovered: dict[str, bool] = {}
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("fields"), list):
            raise AshbyPartnerUnavailable("Ashby application fields are incomplete")
        for entry in section["fields"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("field"), dict):
                raise AshbyPartnerUnavailable("Ashby application field is unknown")
            field = entry["field"]
            path, kind = field.get("path"), field.get("type")
            if (not isinstance(path, str) or path in discovered
                    or path not in _FIELDS or kind not in _FIELDS.get(path, ())
                    or type(entry.get("isRequired")) is not bool):
                raise AshbyPartnerUnavailable(
                    "Ashby employer-specific or sensitive questions require manual review"
                )
            discovered[path] = entry["isRequired"]
            if len(discovered) > len(_FIELDS):
                raise AshbyPartnerUnavailable("Ashby form contains unsupported extra fields")
    if not _REQUIRED.issubset(discovered) or any(
        not discovered[name] for name in _REQUIRED
    ):
        raise AshbyPartnerUnavailable("Ashby name/email/resume fields not independently verified")
    if any(
        required for path, required in discovered.items()
        if path not in _REQUIRED
    ):
        raise AshbyPartnerUnavailable("Additional required Ashby fields need human review")
    return form


class AshbyPartnerTransport:
    """INTERNAL transport building block. Not callable from HTTP/UI/worker.

    The follow-up integration MUST require a signed-in, exact owner-bound,
    irrevocably consumed PostgreSQL claim with fresh independent reviewed
    Ashby submission rights BEFORE it may invoke this method. No automatic
    retry even when a submission response is ambiguous.
    """

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def send_after_external_claim(
        self, posting: AshbyPartnerPosting, *,
        application_url: str, fields: dict[str, str], pdf: bytes,
    ) -> AshbyPartnerAcknowledgment:
        org, slug = _exact_url(application_url)
        if (org != posting.organization or slug != posting.job_slug
                or not _valid_uuid(posting.posting_id)
                or not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-")
                or not pdf.rstrip().endswith(b"%%EOF")
                or not 12 <= len(pdf) <= _MAX_PDF
                or not isinstance(fields, dict)
                or not isinstance(fields.get("full_name"), str)
                or not 1 <= len(fields["full_name"].strip()) <= 160
                or not isinstance(fields.get("email"), str)
                or not re.fullmatch(
                    r"[^\s@]+@[^\s@]+\.[^\s@]+", fields["email"]
                )):
            raise AshbyPartnerUnavailable("Reviewed applicant and exact Ashby posting required")
        credential = posting.key()
        with httpx.Client(
            base_url=_API_ROOT, auth=(credential, ""),
            transport=self._transport, trust_env=False,
            follow_redirects=False, timeout=httpx.Timeout(9.0, connect=3.0),
            headers={"Accept": "application/json; version=1",
                     "User-Agent": "SmartPloy-AshbyPartner/1"},
        ) as client:
            # This is a read-only preflight: NO CV or applicant data sent.
            try:
                response = client.post(
                    "/jobPosting.info",
                    json={"jobPostingId": posting.posting_id,
                          "includeUnpublishedJobPostings": False},
                )
                if response.status_code != 200:
                    raise AshbyPartnerUnavailable("Ashby posting verification unavailable")
                info = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise AshbyPartnerUnavailable(
                    "Cannot verify the exact Ashby posting before any applicant transfer"
                ) from exc
            approved_form = _approved_form(info, posting, application_url)
            # No arbitrary answers or consent strings. Never invent the
            # candidate's response to employer legal/survey questions.
            answers = [
                {"path": "_systemfield_name", "value": fields["full_name"].strip()},
                {"path": "_systemfield_email", "value": fields["email"].strip()},
                {"path": "_systemfield_resume", "value": "resume_1"},
            ]
            form_paths = {
                entry["field"]["path"]
                for section in approved_form["sections"]
                for entry in section["fields"]
            }
            phone = fields.get("phone", "")
            letter = fields.get("cover_letter", "")
            if "_systemfield_phone" in form_paths and isinstance(phone, str) and phone.strip():
                answers.append({"path": "_systemfield_phone", "value": phone.strip()[:40]})
            if "_systemfield_cover_letter" in form_paths:
                if not isinstance(letter, str) or len(letter.strip()) < 60:
                    raise AshbyPartnerUnavailable("Exact reviewed cover letter is required")
                answers.append({"path": "_systemfield_cover_letter",
                                "value": letter.strip()[:10000]})
            # One exact POST. A local response does not grant a second POST.
            try:
                submitted = client.post(
                    "/applicationForm.submit",
                    data={
                        "jobPostingId": posting.posting_id,
                        "applicationForm": json.dumps({
                            "fieldSubmissions": answers,
                        }, separators=(",", ":"), ensure_ascii=False),
                        "allowSubmissionForUnpublishedJobPosting": "false",
                        "utmData": "{}",
                    },
                    files={"resume_1": (
                        "smartploy-reviewed-cv.pdf", pdf, "application/pdf",
                    )},
                )
            except httpx.TimeoutException:
                raise AshbyPartnerUncertain("timeout") from None
            except httpx.HTTPError:
                raise AshbyPartnerUncertain() from None
            if submitted.status_code != 200:
                raise AshbyPartnerUncertain()
            try:
                body = submitted.json()
                result = body.get("results") if isinstance(body, dict) else None
                form_instance = result.get("submittedFormInstance") if isinstance(result, dict) else None
                messages = result.get("formMessages") if isinstance(result, dict) else None
                if (not isinstance(body, dict)
                        or body.get("success") is not True
                        or not isinstance(form_instance, dict)
                        or not isinstance(messages, dict)
                        or messages.get("blocked") is not False
                        or not _valid_uuid(form_instance.get("id"))
                        or not isinstance(form_instance.get("formDefinition"), dict)
                        or _form_sha(form_instance["formDefinition"]) !=
                           posting.form_review_sha256):
                    raise AshbyPartnerUncertain()
                values = form_instance.get("submittedValues")
                if (not isinstance(values, dict)
                        or values.get("_systemfield_name") != fields["full_name"].strip()
                        or values.get("_systemfield_email") != fields["email"].strip()):
                    raise AshbyPartnerUncertain()
                form_id = str(form_instance["id"])
            except (ValueError, TypeError, KeyError):
                raise AshbyPartnerUncertain() from None
            # Official read-only lookup resolves the form ID to a genuine
            # application ID. Missing candidatesRead access is UNVERIFIED,
            # never guessed from the submitted-form UUID or retried.
            try:
                verified = client.post(
                    "/application.info",
                    json={"submittedFormInstanceId": form_id},
                )
                if verified.status_code != 200:
                    raise AshbyPartnerUncertain()
                resolved = verified.json()
                app = resolved.get("results") if isinstance(resolved, dict) else None
                if (not isinstance(resolved, dict)
                        or resolved.get("success") is not True
                        or not isinstance(app, dict)
                        or not _valid_uuid(app.get("id"))):
                    raise AshbyPartnerUncertain()
                return AshbyPartnerAcknowledgment(
                    submitted_form_instance_id=form_id,
                    application_id=str(app["id"]),
                )
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                raise AshbyPartnerUncertain() from None

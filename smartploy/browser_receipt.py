"""Private, non-authoritative employer receipt observation validation.

Browser-originated observations are *not* signed employer attestations. Even a
valid observation never increments SmartPloy's independently verified submission
counter and never grants employer submission authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from urllib.parse import urlsplit

from .application_workspace import ApplicationWorkspace

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{3,63}$")
MAX_OBSERVATION_AGE_SECONDS = 1800


class ReceiptError(ValueError):
    pass


@dataclass(frozen=True)
class BrowserReceipt:
    profile_id: str
    workspace_id: str
    document_revision: int
    document_sha256: str
    reference: str
    confirmation_page_url: str
    confirmation_page_sha256: str
    observed_at: str
    digest: str
    status: str = "browser_observed_unverified"

    def to_dict(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "document_revision": self.document_revision,
            "document_sha256": self.document_sha256,
            "reference": self.reference,
            "confirmation_page_url": self.confirmation_page_url,
            "confirmation_page_sha256": self.confirmation_page_sha256,
            "observed_at": self.observed_at,
            "evidence_digest": self.digest,
            "status": self.status,
            "independently_verified_by_employer": False,
            "actually_submitted_count_changed": False,
        }


def _verified_url(value: str, expected: str) -> str:
    if not isinstance(value, str) or not (14 <= len(value) <= 1500):
        raise ReceiptError("A bounded HTTPS employer confirmation URL is required")
    try:
        # Browser URL parsers normalize dot segments, escaped dot segments,
        # backslashes and some whitespace before exposing location.href.
        # Reject those ambiguous raw forms on BOTH sides so a receipt cannot
        # name a different job after parsing or normalization elsewhere.
        for raw in (value, expected):
            if (
                not isinstance(raw, str) or not 14 <= len(raw) <= 1500
                or re.search(r"[\x00-\x20\x7f\\]", raw)
            ):
                raise ReceiptError("Receipt URL contains ambiguous characters")
        parsed = urlsplit(value)
        accepted = urlsplit(expected)
        for address in (parsed, accepted):
            if (
                "%" in address.netloc or not address.netloc.isascii()
                or "%" in address.path or "//" in address.path
                or any(part in {".", ".."} for part in address.path.split("/"))
            ):
                raise ReceiptError("Receipt URL contains an ambiguous job path")
        # Reuse SP43's exact reviewed hosted-provider posting boundary. A browser
        # observation is NOT a provider-issued receipt or submit permission.
        from .browser_handoff import _assisted_posting_url
        _assisted_posting_url(expected)
        if (
            parsed.scheme != "https" or accepted.query or accepted.fragment
            or parsed.username or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ReceiptError("Receipt must remain on an exact HTTPS employer job")
        greenhouse_hosts = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
        greenhouse = (
            accepted.hostname in greenhouse_hosts
            and parsed.hostname in greenhouse_hosts
        )
        if parsed.hostname != accepted.hostname and not greenhouse:
            raise ReceiptError("Receipt must remain on the original employer host")
        if accepted.hostname == "jobs.ashbyhq.com":
            # Exact Ashby job identity must survive confirmation navigation.
            parts = accepted.path.strip("/").split("/")
            posting = "/" + "/".join(parts[:2])
            if len(parts) not in (2, 3) or not (
                parsed.path == posting or
                parsed.path == posting + "/" or
                re.fullmatch(
                    re.escape(posting) + r"/application(?:/[A-Za-z0-9_-]+)*/?",
                    parsed.path,
                )
            ):
                raise ReceiptError("Ashby confirmation belongs to another job")
        elif accepted.hostname in {"jobs.lever.co", "jobs.eu.lever.co"}:
            # SP47: an employer account can contain MANY applications. A
            # sibling job or a tenant-wide thank-you page proves nothing
            # about the selected posting, even when a prior attempt exists.
            posting = "/" + "/".join(accepted.path.strip("/").split("/")[:2])
            if not (
                parsed.path in {
                    posting, posting + "/", posting + "/apply",
                    posting + "/apply/", posting + "/thanks", posting + "/thanks/",
                    posting + "/confirmation", posting + "/confirmation/",
                }
                or re.fullmatch(
                    re.escape(posting) + r"/apply(?:/[A-Za-z0-9_-]+)*/?",
                    parsed.path,
                )
            ):
                raise ReceiptError("Lever confirmation belongs to another job")
        elif greenhouse:
            # SP43 already permits only this official-host transition for
            # reviewed form assistance. Keep the board AND numeric job ID;
            # generic employer thank-you redirects remain manual reporting.
            posting = accepted.path.rstrip("/")
            if parsed.path not in {
                posting, posting + "/", posting + "/confirmation",
                posting + "/confirmation/",
            }:
                raise ReceiptError("Greenhouse confirmation belongs to another job")
        else:
            raise ReceiptError("Unsupported employer confirmation host")
    except (ValueError, IndexError, TypeError) as exc:
        raise ReceiptError("Receipt URL cannot be verified against the original job") from exc
    # Drop query/fragment even if the page included credentials or tracking params.
    return "https://" + str(parsed.hostname) + parsed.path


def validate_browser_receipt(
    workspace: ApplicationWorkspace,
    raw: dict,
    *,
    now: datetime | None = None,
) -> BrowserReceipt:
    if not isinstance(raw, dict) or set(raw) != {
        "schema", "workspace_id", "document_revision", "document_sha256",
        "application_url", "confirmation_page_url", "reference",
        "confirmation_page_sha256", "observed_at", "confirmed_visible",
    }:
        raise ReceiptError("Unsupported browser receipt format")
    if raw["schema"] != "smartploy.browser_receipt.v1":
        raise ReceiptError("Browser receipt schema is not recognized")
    if workspace.status != "draft":
        raise ReceiptError("The existing application is no longer an editable draft")
    if raw["workspace_id"] != workspace.workspace_id or raw["application_url"] != workspace.application_url:
        raise ReceiptError("Browser receipt belongs to a different job or owner draft")
    if type(raw["document_revision"]) is not int or raw["document_revision"] != workspace.revision:
        raise ReceiptError("Browser receipt was created for a different saved revision")
    expected_digest = sha256((workspace.cv_text + "\0" + workspace.cover_letter_text).encode("utf-8")).hexdigest()
    if raw["document_sha256"] != expected_digest or not SHA256.fullmatch(str(raw["document_sha256"])):
        raise ReceiptError("Browser receipt document digest does not match the reviewed CV and letter")
    if raw["confirmed_visible"] is not True:
        raise ReceiptError("A visible reference-bearing employer confirmation is required")
    reference = raw["reference"]
    page_hash = raw["confirmation_page_sha256"]
    if not isinstance(reference, str) or not REFERENCE.fullmatch(reference):
        raise ReceiptError("Employer reference must be a bounded printable identifier")
    if not isinstance(page_hash, str) or not SHA256.fullmatch(page_hash):
        raise ReceiptError("Confirmation page text digest must be SHA-256")
    safe_url = _verified_url(raw["confirmation_page_url"], workspace.application_url)
    when = raw["observed_at"]
    try:
        observed = datetime.fromisoformat(when.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("timezone required")
        observed = observed.astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ReceiptError("Receipt observation time is invalid") from exc
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if observed > current + timedelta(seconds=120) or current - observed > timedelta(seconds=MAX_OBSERVATION_AGE_SECONDS):
        raise ReceiptError("Browser receipt observation is too old or in the future")

    digest = sha256(
        "\0".join((
            workspace.profile_id, workspace.workspace_id, str(workspace.revision),
            expected_digest, safe_url, reference, page_hash,
        )).encode("utf-8")
    ).hexdigest()
    return BrowserReceipt(
        profile_id=workspace.profile_id,
        workspace_id=workspace.workspace_id,
        document_revision=workspace.revision,
        document_sha256=expected_digest,
        reference=reference,
        confirmation_page_url=safe_url,
        confirmation_page_sha256=page_hash,
        observed_at=observed.isoformat(),
        digest=digest,
    )

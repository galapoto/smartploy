"""Human-approved browser application handoff; no server-side employer requests.

A packet contains limited approved contact facts and a reviewed cover letter,
never an uploaded CV, token, profile store, or submit credential. This module
does not issue authority to employer sites or claim submission evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import ipaddress
import re
from urllib.parse import urlsplit
from typing import Mapping

from .application_workspace import ApplicationWorkspace, render_document
from .domain import JobCandidate
from .profile import CandidateProfile

SCHEMA = "smartploy.browser_handoff.v2"
LIFETIME_SECONDS = 15 * 60
# Review markers are intentionally present in both language templates.
# Existing browser handoff AND the server-atomic employer preflight reuse
# this single regex. Finnish markers must NEVER bypass completion checks.
PLACEHOLDERS = re.compile(
    r"\[(?:explain|your name|insert|add|describe|fill in|why|placeholder|"
    r"kerro|lisää|oma nimi|täydennä|kirjoita|esimerkki)\b[^]]*]",
    re.IGNORECASE,
)


class HandoffError(ValueError):
    pass


def _first_approved(profile: CandidateProfile, kind: str) -> tuple[str, bool]:
    matches = sorted({f.value.strip() for f in profile.approved_facts if f.fact_type == kind and f.value.strip()})
    return (matches[0] if len(matches) == 1 else "", len(matches) > 1)


def _approved_contact(profile: CandidateProfile) -> dict[str, str]:
    full_name, multiple_names = _first_approved(profile, "identity")
    email, multiple_emails = _first_approved(profile, "email")
    if not email:
        # A previously approved generic contact fact may contain a single
        # bare address. Arbitrary unparsed CV text never qualifies.
        contact = [f.value for f in profile.approved_facts if f.fact_type == "contact"]
        bare = sorted({v for v in contact if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v)})
        if len(bare) == 1:
            email = bare[0]
        elif len(bare) > 1:
            multiple_emails = True
    phone, _ = _first_approved(profile, "phone")
    location, _ = _first_approved(profile, "location")
    linkedin, _ = _first_approved(profile, "linkedin")
    github, _ = _first_approved(profile, "github")
    if multiple_names:
        full_name = ""
    if multiple_emails:
        email = ""
    parts = full_name.split()
    return {
        "full_name": full_name[:160],
        "first_name": parts[0] if parts else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
        "email": email[:254],
        "phone": phone[:40],
        "location": location[:160],
        "linkedin": linkedin[:350],
        "github": github[:350],
    }


def _posting_url(raw: str) -> str:
    try:
        parsed = urlsplit(raw)
        ip = None
        if parsed.hostname:
            try:
                ip = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                pass
        if (
            parsed.scheme != "https" or parsed.hostname not in {"jobs.lever.co", "jobs.eu.lever.co"}
            or ip is not None or parsed.username or parsed.password
            or parsed.port not in {None, 443}
            or not re.fullmatch(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:/apply/?)?", parsed.path)
            or len(raw) > 1500
        ):
            raise ValueError
    except ValueError as exc:
        raise HandoffError("An exact verified Lever HTTPS job application URL is required") from exc
    return raw


def _assisted_posting_url(raw: str) -> str:
    """Any applicant-reviewed PUBLIC HTTPS job URL can use visible form help.

    This is not a source-approval bypass for automated submission. Known ATS
    platforms still require their exact verified URL shapes. Unknown employers
    must meet a conservative public-host gate; browser filling remains
    one-use, local and user-approved. No server fetch happens here.
    """
    try:
        return _posting_url(raw)
    except HandoffError:
        pass
    try:
        if not isinstance(raw, str) or len(raw) > 1500 or "\\" in raw:
            raise ValueError
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
            raise ValueError
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or not host or (not parsed.path.strip("/") and not parsed.query)
        ):
            raise ValueError
        if host in {"jobs.ashbyhq.com", "ats.talentadore.com",
                    "boards.greenhouse.io", "job-boards.greenhouse.io"}:
            patterns = {
                "jobs.ashbyhq.com": r"/[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_-]{1,160}(?:/application/?)?",
                "ats.talentadore.com": r"/apply/[A-Za-z0-9_-]{1,120}/[A-Za-z0-9_-]{5,30}/?",
                "boards.greenhouse.io": r"/[A-Za-z0-9_-]{1,100}/jobs/[0-9]{1,20}/?",
                "job-boards.greenhouse.io": r"/[A-Za-z0-9_-]{1,100}/jobs/[0-9]{1,20}/?",
            }
            if parsed.query or re.fullmatch(patterns[host], parsed.path) is None:
                raise ValueError
            return raw
        if host in {"jobs.lever.co", "jobs.eu.lever.co"}:
            # Preserve the original strict Lever policy, not a generic fallback.
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("Literal IP addresses cannot be employer job hosts")
        if (
            not re.fullmatch(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}",
                host,
            )
            or host.endswith((".local", ".localhost", ".internal", ".test",
                              ".invalid", ".example", ".onion"))
            or parsed.port not in (None, 443)
            or len(parsed.query) > 800
        ):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise HandoffError(
            "Use an applicant-reviewed public HTTPS job link without credentials, "
            "private-network addresses or unsafe ports"
        ) from exc
    return raw


def review_handoff(
    workspace: ApplicationWorkspace, candidate: JobCandidate | None,
    profile: CandidateProfile,
) -> dict:
    blockers: list[str] = []
    if workspace.profile_id != profile.profile_id:
        raise HandoffError("Application workspace is not owned by this profile")
    if workspace.status != "draft":
        blockers.append("This application was already marked applied")
    private_user_review = bool(
        candidate is not None and candidate.source_current is False
        and candidate.metadata.get("private_saved_job") is True
        and candidate.metadata.get("owner_profile_id") == workspace.profile_id
    )
    if candidate is None or (not candidate.source_current and not private_user_review):
        blockers.append("The employer posting is no longer current")
    elif (
        candidate.canonical_key != workspace.canonical_key
        or candidate.description_fingerprint != workspace.job_fingerprint
        or candidate.job.application_url != workspace.application_url
    ):
        blockers.append("The employer posting has changed; review it before applying")
    try:
        _assisted_posting_url(workspace.application_url)
    except HandoffError:
        blockers.append("A public HTTPS employer application URL is required")
    if not workspace.cv_text.strip():
        blockers.append("A completed CV is required")
    # Finished first-draft prose is NOT applicant review. Both the original
    # guide-style drafts and SP85's real-prose drafts start at revision 1.
    # The owner must deliberately save their inspected documents (CAS write)
    # before browser form handoff or a separately authorized partner action.
    # Never infer review from the absence of placeholders or from approved facts.
    if workspace.revision < 2:
        blockers.append("Save the CV and cover letter after personally reviewing them")
    if PLACEHOLDERS.search(workspace.cover_letter_text):
        blockers.append("Replace the marked cover-letter placeholders with reviewed wording")
    if len(workspace.cover_letter_text.strip()) < 60:
        blockers.append("Review and complete your cover letter")
    approved = _approved_contact(profile)
    if not approved["full_name"]:
        blockers.append("Approve exactly one full-name identity fact in your profile")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", approved["email"]):
        blockers.append("Approve exactly one valid email fact in your profile")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "document_revision": workspace.revision,
        "contact_fields_ready": bool(approved["full_name"] and approved["email"]),
        "employer_submission_performed": False,
        "will_require_manual_review": True,
        "unverified_private_employer": private_user_review,
        "files_attached": False,
    }


APPROVED_FIELD_NAMES = (
    "full_name", "first_name", "last_name", "email", "phone",
    "location", "linkedin", "github", "cover_letter",
)


def approved_fields_sha256(fields: Mapping[str, str]) -> str:
    """Fingerprint the exact approved private fields without exposing them.

    Reused by the browser handoff and first-party extension verification.
    Length-prefix UTF-8 to avoid ambiguous concatenation and Python/JS JSON
    serializer differences. The digest is a fingerprint, NOT an authorization.
    """
    if set(fields) != set(APPROVED_FIELD_NAMES):
        raise HandoffError("The packet must contain the expected approved fields only")
    parts: list[str] = []
    for name in APPROVED_FIELD_NAMES:
        value = fields[name]
        if not isinstance(value, str):
            raise HandoffError("Reviewed field values must be text")
        parts.append(str(len(value.encode("utf-8"))) + ":" + value)
    return sha256(("smartploy.fields.v1\0" + "\0".join(parts)).encode("utf-8")).hexdigest()


def make_browser_packet(
    workspace: ApplicationWorkspace, candidate: JobCandidate | None,
    profile: CandidateProfile, *, now: datetime | None = None,
) -> dict:
    review = review_handoff(workspace, candidate, profile)
    if not review["ready"]:
        raise HandoffError("Application handoff not ready: " + "; ".join(review["blockers"]))
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc)
    contact = _approved_contact(profile)
    # Deterministic PDF rendering binds the handoff to the exact exported CV.
    # The file itself is never placed in the packet, only its size/digest.
    cv_pdf, _, _ = render_document(workspace, kind="cv", file_format="pdf")
    if len(cv_pdf) > 2 * 1024 * 1024:
        raise HandoffError("The reviewed PDF exceeds the companion attachment limit")
    packet = {
        "schema": SCHEMA,
        "issued_at": stamp.isoformat(),
        "expires_at": (stamp + timedelta(seconds=LIFETIME_SECONDS)).isoformat(),
        "application_url": _assisted_posting_url(workspace.application_url),
        "company": workspace.company,
        "role_title": workspace.role_title,
        "workspace_id": workspace.workspace_id,
        "revision": workspace.revision,
        "document_sha256": sha256(
            (workspace.cv_text + "\0" + workspace.cover_letter_text).encode("utf-8")
        ).hexdigest(),
        "cv_pdf_sha256": sha256(cv_pdf).hexdigest(),
        "cv_pdf_size": len(cv_pdf),
        "fields": {
            **contact,
            "cover_letter": workspace.cover_letter_text[:10000],
        },
        "privacy": {
            "approved_contact_only": True,
            "original_cv_included": False,
            "browser_form_fill_allowed_after_user_click": True,
            "employer_submit_allowed_without_new_approval": False,
        },
    }
    # Server-owned exact contact/letter fingerprint for partner submissions.
    # Contains no new private data and is never a browser submit grant.
    packet["approved_fields_sha256"] = approved_fields_sha256(packet["fields"])
    return packet

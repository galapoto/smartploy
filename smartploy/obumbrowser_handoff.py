"""Private SmartPloy -> ObumBrowser navigation boundary, not a session API.

A reviewed job can yield only its exact public employer target. Applicant CV,
letter, contact fields, session cookies and submission authority stay with
SmartPloy. This does not connect to ObumBrowser, allocate a browser, or create
a browser action: its v1 live service is not qualified yet.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .application_workspace import ApplicationWorkspace
from .browser_handoff import HandoffError, _assisted_posting_url, review_handoff
from .domain import JobCandidate
from .profile import CandidateProfile


SCHEMA = "smartploy.obumbrowser_navigation_intent.v1"


def reviewed_navigation_intent(
    workspace: ApplicationWorkspace,
    candidate: JobCandidate | None,
    profile: CandidateProfile,
) -> dict[str, object]:
    """Return an exact URL-only target after the existing applicant review gate.

    This object is an INTERNAL consumer-side intent, not a bearer capability,
    a ready session, a provider-approved job, or a final-submission grant.
    The future ObumBrowser adapter must separately verify owner, scoped OIDC,
    session lease, fresh observation, document revision and user approval.
    """
    readiness = review_handoff(workspace, candidate, profile)
    if not readiness["ready"]:
        raise HandoffError("Browser navigation not ready: " + "; ".join(readiness["blockers"]))

    # Share the exact hosted-ATS identity restrictions already enforced by
    # SmartPloy's working Chrome companion. Query/fragment are disallowed
    # here, so the generic browser never receives candidate tokens in URLs.
    url = _assisted_posting_url(workspace.application_url)
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        raise HandoffError("A clean, exact employer job URL is required for hosted navigation")

    return {
        "schema": SCHEMA,
        "target_url": url,
        "transport": "obumbrowser",
        "scope": "navigation_only",
        "applicant_data_included": False,
        "browser_session_created": False,
        "external_action_authorized": False,
        "document_upload_authorized": False,
        "employer_submit_authorized": False,
    }

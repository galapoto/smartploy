"""Owner-editable, text-faithful master CV generation.

Reuse the same known-good application PDF/DOCX renderers, rather than
introducing a second document generator or forwarding private CVs to AI.
No text is inferred, shortened, translated, approved as evidence or sent.
"""
from __future__ import annotations

from .application_workspace import ApplicationWorkspace, render_document

MAX_EDITOR_TEXT = 30_000


def validate_editor_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("CV text must be a string")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ValueError("CV text contains unsupported control characters")
    clean = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(clean) < 20:
        raise ValueError("Write at least 20 characters before saving your CV")
    if len(clean) > MAX_EDITOR_TEXT:
        raise ValueError("CV text exceeds 30,000 characters; shorten before saving")
    return clean


def render_editor_cv(value: str, *, file_format: str) -> bytes:
    """Faithfully export user-written text to PDF or DOCX, no network or AI."""
    text = validate_editor_text(value)
    if file_format not in {"pdf", "docx"}:
        raise ValueError("Unsupported master CV download format")
    # The existing render_document() only reads cv_text for kind='cv'.
    blank = ApplicationWorkspace(
        workspace_id="master-cv-export",
        profile_id="local-only",
        canonical_key="",
        role_title="",
        company="",
        application_url="",
        cv_text=text,
        cover_letter_text="",
        source_cv_sha256="",
        approved_evidence_ids=(),
        job_fingerprint="",
    )
    data, _, _ = render_document(blank, kind="cv", file_format=file_format)
    return data

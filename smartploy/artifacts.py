"""Immutable SmartPloy application document artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
import hashlib
import re

from .domain import canonical_json, utc_now_iso


MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
ARTIFACT_MEDIA_TYPES = {
    "cv_docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "cv_pdf": ("application/pdf", ".pdf"),
    "cover_letter_docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "cover_letter_pdf": ("application/pdf", ".pdf"),
}
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def artifact_id_for(
    *,
    package_id: str,
    artifact_type: str,
    content_sha256: str,
) -> str:
    material = canonical_json(
        {
            "package_id": str(package_id),
            "artifact_type": str(artifact_type),
            "content_sha256": str(content_sha256),
        }
    )
    return "artifact-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


@dataclass(frozen=True)
class ApplicationArtifact:
    artifact_id: str
    package_id: str
    canonical_key: str
    artifact_type: str
    filename: str
    media_type: str
    content_sha256: str
    size_bytes: int
    content: bytes = field(repr=False)
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ApplicationArtifact":
        artifact_type = str(self.artifact_type or "").strip()
        expected = ARTIFACT_MEDIA_TYPES.get(artifact_type)
        if expected is None:
            raise ValueError("unsupported application artifact type")
        expected_media_type, expected_extension = expected

        package_id = str(self.package_id or "").strip()
        canonical_key = str(self.canonical_key or "").strip()
        if not package_id or not canonical_key:
            raise ValueError("application artifact identity is incomplete")

        filename = str(self.filename or "").strip()
        if not _SAFE_FILENAME.fullmatch(filename):
            raise ValueError("application artifact filename is unsafe")
        if not filename.casefold().endswith(expected_extension):
            raise ValueError("application artifact filename extension does not match type")

        media_type = str(self.media_type or "").strip().casefold()
        if media_type != expected_media_type:
            raise ValueError("application artifact media type does not match type")

        content = bytes(self.content or b"")
        if not content or len(content) > MAX_ARTIFACT_BYTES:
            raise ValueError("application artifact content size is outside allowed bounds")
        content_sha256 = hashlib.sha256(content).hexdigest()
        if str(self.content_sha256 or "") != content_sha256:
            raise ValueError("application artifact SHA-256 does not match content")
        if int(self.size_bytes) != len(content):
            raise ValueError("application artifact size does not match content")

        expected_id = artifact_id_for(
            package_id=package_id,
            artifact_type=artifact_type,
            content_sha256=content_sha256,
        )
        artifact_id = str(self.artifact_id or "").strip() or expected_id
        if artifact_id != expected_id:
            raise ValueError("application artifact ID does not match immutable content identity")

        return replace(
            self,
            artifact_id=artifact_id,
            package_id=package_id,
            canonical_key=canonical_key,
            artifact_type=artifact_type,
            filename=filename,
            media_type=media_type,
            content_sha256=content_sha256,
            size_bytes=len(content),
            content=content,
            created_at=str(self.created_at or utc_now_iso()),
            metadata=dict(self.metadata or {}),
        )

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        item = self.normalized()
        value = {
            "artifact_id": item.artifact_id,
            "package_id": item.package_id,
            "canonical_key": item.canonical_key,
            "artifact_type": item.artifact_type,
            "filename": item.filename,
            "media_type": item.media_type,
            "content_sha256": item.content_sha256,
            "size_bytes": item.size_bytes,
            "created_at": item.created_at,
            "metadata": dict(item.metadata),
            "authority": {
                "may_download": True,
                "may_upload": False,
                "may_submit": False,
                "external_action_authorized": False,
            },
        }
        if include_content:
            value["content"] = item.content
        return value

"""Private user-saved job records, deliberately separate from shared ATS ingestion.

These records are only returned through profile-scoped APIs. They do not imply
an employer's job is live and cannot be submitted or sent to AI automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from psycopg import connect


class PrivateSavedJobError(ValueError):
    """A submitted personal job record did not pass validation."""


@dataclass(frozen=True)
class PrivateSavedJob:
    profile_id: str
    saved_job_id: str
    company: str
    role_title: str
    description: str
    location: str
    application_url: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "saved_job_id": self.saved_job_id,
            "company": self.company,
            "role_title": self.role_title,
            "description": self.description,
            "location": self.location,
            "application_url": self.application_url,
            "created_at": self.created_at,
            "private": True,
            "employer_availability_verified": False,
            "external_actions_authorized": False,
        }


def validate_saved_job(data: dict[str, str]) -> dict[str, str]:
    fields = {
        "company": 160, "role_title": 160, "description": 12000,
        "location": 160, "application_url": 2048,
    }
    cleaned: dict[str, str] = {}
    for key, maximum in fields.items():
        value = data.get(key, "")
        if not isinstance(value, str):
            raise PrivateSavedJobError(f"{key} must be text")
        text = value.strip()
        if len(text) > maximum:
            raise PrivateSavedJobError(f"{key} exceeds its length limit")
        if key in {"company", "role_title", "description"} and not text:
            raise PrivateSavedJobError(f"{key} is required")
        cleaned[key] = text

    url = cleaned["application_url"]
    if url:
        if any(ord(character) < 32 or ord(character) == 127 for character in url):
            raise PrivateSavedJobError("job link contains control characters")
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme.lower() not in {"https", "http"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port is None and parsed.netloc.endswith(":")
            ):
                raise PrivateSavedJobError("job link must be an HTTP(S) URL without credentials")
            # Accessing .port validates malformed port syntax too.
            _ = parsed.port
        except ValueError as exc:
            raise PrivateSavedJobError("job link must be a valid HTTP(S) URL") from exc
    return cleaned


class PrivateSavedJobRepository(Protocol):
    def save(self, profile_id: str, data: dict[str, str]) -> PrivateSavedJob: ...
    def list(self, profile_id: str, *, limit: int = 100) -> list[PrivateSavedJob]: ...
    def delete(self, profile_id: str, saved_job_id: str) -> bool: ...


class MemoryPrivateSavedJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], PrivateSavedJob] = {}

    def save(self, profile_id: str, data: dict[str, str]) -> PrivateSavedJob:
        if not profile_id:
            raise PrivateSavedJobError("profile identity is required")
        cleaned = validate_saved_job(data)
        item = PrivateSavedJob(
            profile_id=profile_id,
            saved_job_id="saved-" + uuid4().hex,
            created_at=datetime.now(timezone.utc).isoformat(),
            **cleaned,
        )
        self._jobs[(profile_id, item.saved_job_id)] = item
        return item

    def list(self, profile_id: str, *, limit: int = 100) -> list[PrivateSavedJob]:
        return sorted(
            (item for (owner, _), item in self._jobs.items() if owner == profile_id),
            key=lambda item: (item.created_at, item.saved_job_id),
            reverse=True,
        )[:limit]

    def delete(self, profile_id: str, saved_job_id: str) -> bool:
        return self._jobs.pop((profile_id, saved_job_id), None) is not None


class PostgresPrivateSavedJobRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @staticmethod
    def _from_row(profile_id: str, row: tuple) -> PrivateSavedJob:
        return PrivateSavedJob(
            profile_id=profile_id,
            saved_job_id=str(row[0]),
            company=row[1],
            role_title=row[2],
            description=row[3],
            location=row[4],
            application_url=row[5],
            created_at=row[6].isoformat(),
        )

    def save(self, profile_id: str, data: dict[str, str]) -> PrivateSavedJob:
        if not profile_id:
            raise PrivateSavedJobError("profile identity is required")
        cleaned = validate_saved_job(data)
        saved_id = "saved-" + uuid4().hex
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_private_saved_jobs
                       (profile_id, saved_job_id, company, role_title,
                        description, location, application_url)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       RETURNING saved_job_id, company, role_title,
                                 description, location, application_url, created_at""",
                    (profile_id, saved_id, cleaned["company"],
                     cleaned["role_title"], cleaned["description"],
                     cleaned["location"], cleaned["application_url"]),
                )
                row = cur.fetchone()
        return self._from_row(profile_id, row)

    def list(self, profile_id: str, *, limit: int = 100) -> list[PrivateSavedJob]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT saved_job_id, company, role_title, description,
                              location, application_url, created_at
                       FROM smartploy_private_saved_jobs
                       WHERE profile_id = %s
                       ORDER BY created_at DESC, saved_job_id DESC LIMIT %s""",
                    (profile_id, limit),
                )
                rows = cur.fetchall()
        return [self._from_row(profile_id, row) for row in rows]

    def delete(self, profile_id: str, saved_job_id: str) -> bool:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """DELETE FROM smartploy_private_saved_jobs
                       WHERE profile_id = %s AND saved_job_id = %s""",
                    (profile_id, saved_job_id),
                )
                changed = cur.rowcount > 0
        return changed

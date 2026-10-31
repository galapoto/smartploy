"""Private CV persistence. Query access is always scoped to a verified profile_id."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re

from .cv_editor import render_editor_cv, validate_editor_text

from psycopg import connect


@dataclass(frozen=True)
class StoredCV:
    profile_id: str
    filename: str
    media_type: str
    content: bytes
    text: str
    updated_at: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def summary(self) -> dict[str, object]:
        return {
            "present": True,
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": len(self.content),
            "sha256": self.digest,
            "text_preview": self.text[:6000],
            "text_extracted": bool(self.text.strip()),
            "updated_at": self.updated_at,
            "created_by_editor": self.filename == "smartploy-master-cv.docx",
        }


class CVRevisionConflict(ValueError):
    """An editor saved against an outdated CV revision; never overwrite silently."""


class CVArchiveNotFound(ValueError):
    """The chosen historical CV is absent or belongs to another profile."""


class MemoryCVRepository:
    def __init__(self) -> None:
        self._items: dict[str, StoredCV] = {}
        self._archive: dict[tuple[str, str], StoredCV] = {}

    def _remember(self, item: StoredCV | None) -> None:
        if item is not None:
            self._archive[(item.profile_id, item.digest)] = item
            entries = [key for key in self._archive if key[0] == item.profile_id]
            for key in entries[:-12]:
                self._archive.pop(key, None)

    def history(self, profile_id: str) -> list[dict[str, object]]:
        current = self.get(profile_id)
        return [
            {**item.summary(), "archived": True}
            for (pid, _), item in reversed(list(self._archive.items()))
            if pid == profile_id and
               (current is None or item.digest != current.digest)
        ][:12]

    def get_archived(self, profile_id: str, digest: str) -> StoredCV | None:
        if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            return None
        return self._archive.get((profile_id, digest))

    def save_editor_text(
        self, profile_id: str, *, expected_sha256: str, text: str,
    ) -> StoredCV:
        if not re.fullmatch(r"(?:[0-9a-f]{64})?", expected_sha256):
            raise ValueError("Invalid expected CV revision")
        cleaned = validate_editor_text(text)
        old = self.get(profile_id)
        if (old.digest if old else "") != expected_sha256:
            raise CVRevisionConflict("CV changed in another tab. Reload before saving.")
        content = render_editor_cv(cleaned, file_format="docx")
        self._remember(old)
        return self.put(profile_id, "smartploy-master-cv.docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        content, cleaned)

    def restore_archived(
        self, profile_id: str, *, digest: str, expected_sha256: str,
    ) -> StoredCV:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid archived CV digest")
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("Exact current CV revision required")
        current = self.get(profile_id)
        if current is None or current.digest != expected_sha256:
            raise CVRevisionConflict("CV changed in another tab. Reload before restoring.")
        previous = self.get_archived(profile_id, digest)
        if previous is None or previous.digest == current.digest:
            raise CVArchiveNotFound("Archived CV version not found")
        self._remember(current)
        # A version cannot simultaneously be the active file and a past file.
        self._archive.pop((profile_id, digest), None)
        restored = StoredCV(
            profile_id=profile_id, filename=previous.filename,
            media_type=previous.media_type, content=previous.content,
            text=previous.text, updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._items[profile_id] = restored
        return restored

    def get(self, profile_id: str) -> StoredCV | None:
        return self._items.get(profile_id)

    def put(self, profile_id: str, filename: str, media_type: str, content: bytes, text: str) -> StoredCV:
        old = self.get(profile_id)
        self._remember(old)
        item = StoredCV(
            profile_id=profile_id, filename=filename, media_type=media_type, content=content,
            text=text, updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._items[profile_id] = item
        return item

    def delete(self, profile_id: str) -> bool:
        removed = self._items.pop(profile_id, None) is not None
        self._archive = {key: item for key, item in self._archive.items() if key[0] != profile_id}
        return removed


class PostgresCVRepository:
    """Current active CV plus bounded, owner-private archived originals/revisions.

    Both upload and editor save serialize on the same per-profile advisory
    transaction lock. The editor additionally enforces expected content digest.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @staticmethod
    def _from_row(profile_id: str, row: tuple) -> StoredCV:
        return StoredCV(
            profile_id=profile_id, filename=str(row[0]), media_type=str(row[1]),
            content=bytes(row[2]), text=str(row[3]),
            updated_at=row[4].isoformat(),
        )

    @staticmethod
    def _lock(cur, profile_id: str) -> None:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ("smartploy.cv." + profile_id,),
        )

    @staticmethod
    def _archive_current(cur, profile_id: str) -> None:
        cur.execute(
            """INSERT INTO smartploy_cv_history (
                 profile_id, sha256, filename, media_type, content, extracted_text,
                 source_updated_at, archived_at)
               SELECT profile_id, sha256, filename, media_type, content,
                      extracted_text, updated_at, now()
               FROM smartploy_cv_files WHERE profile_id=%s
               ON CONFLICT (profile_id, sha256) DO NOTHING""",
            (profile_id,),
        )
        # Keep only 12 previous distinct file versions, never arbitrary copies.
        cur.execute(
            """DELETE FROM smartploy_cv_history
               WHERE profile_id=%s AND sha256 NOT IN (
                 SELECT sha256 FROM smartploy_cv_history
                 WHERE profile_id=%s
                 ORDER BY archived_at DESC, sha256 DESC LIMIT 12
               )""",
            (profile_id, profile_id),
        )

    def get(self, profile_id: str) -> StoredCV | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT filename, media_type, content, extracted_text, updated_at
                       FROM smartploy_cv_files WHERE profile_id=%s""",
                    (profile_id,),
                )
                row = cur.fetchone()
        return self._from_row(profile_id, row) if row else None

    def put(self, profile_id: str, filename: str, media_type: str, content: bytes, text: str) -> StoredCV:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                self._lock(cur, profile_id)
                self._archive_current(cur, profile_id)
                cur.execute(
                    """INSERT INTO smartploy_cv_files
                       (profile_id, filename, media_type, content, extracted_text, sha256, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, now())
                       ON CONFLICT (profile_id) DO UPDATE SET
                         filename=EXCLUDED.filename, media_type=EXCLUDED.media_type,
                         content=EXCLUDED.content, extracted_text=EXCLUDED.extracted_text,
                         sha256=EXCLUDED.sha256, updated_at=now()
                       RETURNING filename, media_type, content, extracted_text, updated_at""",
                    (profile_id, filename, media_type, content, text,
                     hashlib.sha256(content).hexdigest()),
                )
                row = cur.fetchone()
        return self._from_row(profile_id, row)

    def save_editor_text(
        self, profile_id: str, *, expected_sha256: str, text: str,
    ) -> StoredCV:
        if not re.fullmatch(r"(?:[0-9a-f]{64})?", expected_sha256):
            raise ValueError("Invalid expected CV revision")
        cleaned = validate_editor_text(text)
        content = render_editor_cv(cleaned, file_format="docx")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                self._lock(cur, profile_id)
                cur.execute(
                    "SELECT sha256 FROM smartploy_cv_files WHERE profile_id=%s FOR UPDATE",
                    (profile_id,),
                )
                row = cur.fetchone()
                actual = str(row[0]) if row else ""
                if actual != expected_sha256:
                    raise CVRevisionConflict("CV changed in another tab. Reload before saving.")
                self._archive_current(cur, profile_id)
                cur.execute(
                    """INSERT INTO smartploy_cv_files (
                         profile_id, filename, media_type, content, extracted_text,
                         sha256, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, now())
                       ON CONFLICT (profile_id) DO UPDATE SET
                         filename=EXCLUDED.filename, media_type=EXCLUDED.media_type,
                         content=EXCLUDED.content, extracted_text=EXCLUDED.extracted_text,
                         sha256=EXCLUDED.sha256, updated_at=now()
                       RETURNING filename, media_type, content, extracted_text, updated_at""",
                    (profile_id, "smartploy-master-cv.docx",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     content, cleaned, hashlib.sha256(content).hexdigest()),
                )
                updated = cur.fetchone()
        return self._from_row(profile_id, updated)

    def history(self, profile_id: str) -> list[dict[str, object]]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT filename, media_type, octet_length(content), sha256,
                              archived_at
                       FROM smartploy_cv_history
                       WHERE profile_id=%s
                         AND sha256 <> COALESCE((
                             SELECT sha256 FROM smartploy_cv_files WHERE profile_id=%s
                         ), '')
                       ORDER BY archived_at DESC, sha256 DESC LIMIT 12""",
                    (profile_id, profile_id),
                )
                rows = cur.fetchall()
        return [{
            "filename": str(row[0]), "media_type": str(row[1]),
            "size_bytes": int(row[2]), "sha256": str(row[3]),
            "archived_at": row[4].isoformat(), "archived": True,
        } for row in rows]

    def get_archived(self, profile_id: str, digest: str) -> StoredCV | None:
        if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            return None
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT filename, media_type, content, extracted_text,
                              source_updated_at
                       FROM smartploy_cv_history
                       WHERE profile_id=%s AND sha256=%s""",
                    (profile_id, digest),
                )
                row = cur.fetchone()
        return self._from_row(profile_id, row) if row else None

    def restore_archived(
        self, profile_id: str, *, digest: str, expected_sha256: str,
    ) -> StoredCV:
        """Atomically CAS-swap an exact archived file, with no reinterpretation."""
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid archived CV digest")
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("Exact current CV revision required")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                self._lock(cur, profile_id)
                cur.execute(
                    """SELECT sha256 FROM smartploy_cv_files
                       WHERE profile_id=%s FOR UPDATE""",
                    (profile_id,),
                )
                row = cur.fetchone()
                if row is None or str(row[0]) != expected_sha256:
                    raise CVRevisionConflict("CV changed in another tab. Reload before restoring.")
                cur.execute(
                    """SELECT filename, media_type, content, extracted_text
                       FROM smartploy_cv_history
                       WHERE profile_id=%s AND sha256=%s FOR UPDATE""",
                    (profile_id, digest),
                )
                archived = cur.fetchone()
                if archived is None or digest == expected_sha256:
                    raise CVArchiveNotFound("Archived CV version not found")
                if hashlib.sha256(bytes(archived[2])).hexdigest() != digest:
                    raise ValueError("Archived CV integrity could not be verified")
                # Load original bytes before pruning: the selected entry may be
                # the oldest of 12, while archiving the current file adds one.
                self._archive_current(cur, profile_id)
                cur.execute(
                    "DELETE FROM smartploy_cv_history WHERE profile_id=%s AND sha256=%s",
                    (profile_id, digest),
                )
                cur.execute(
                    """UPDATE smartploy_cv_files
                       SET filename=%s, media_type=%s, content=%s,
                           extracted_text=%s, sha256=%s, updated_at=now()
                       WHERE profile_id=%s
                       RETURNING filename,media_type,content,extracted_text,updated_at""",
                    (archived[0], archived[1], archived[2], archived[3], digest, profile_id),
                )
                restored = cur.fetchone()
                if restored is None:
                    raise RuntimeError("Restored CV disappeared during transaction")
        return self._from_row(profile_id, restored)

    def delete(self, profile_id: str) -> bool:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                self._lock(cur, profile_id)
                cur.execute("DELETE FROM smartploy_cv_history WHERE profile_id=%s", (profile_id,))
                cur.execute("DELETE FROM smartploy_cv_files WHERE profile_id=%s", (profile_id,))
                deleted = cur.rowcount > 0
        return deleted

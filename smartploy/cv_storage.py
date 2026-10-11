"""Private CV persistence. Query access is always scoped to a verified profile_id."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

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
        }


class MemoryCVRepository:
    def __init__(self) -> None:
        self._items: dict[str, StoredCV] = {}

    def get(self, profile_id: str) -> StoredCV | None:
        return self._items.get(profile_id)

    def put(self, profile_id: str, filename: str, media_type: str, content: bytes, text: str) -> StoredCV:
        item = StoredCV(
            profile_id=profile_id, filename=filename, media_type=media_type, content=content,
            text=text, updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._items[profile_id] = item
        return item

    def delete(self, profile_id: str) -> bool:
        return self._items.pop(profile_id, None) is not None


class PostgresCVRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @staticmethod
    def _from_row(profile_id: str, row: tuple) -> StoredCV:
        content = row[2]
        return StoredCV(
            profile_id=profile_id, filename=row[0], media_type=row[1],
            content=bytes(content), text=row[3], updated_at=row[4].isoformat(),
        )

    def get(self, profile_id: str) -> StoredCV | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT filename, media_type, content, extracted_text, updated_at
                       FROM smartploy_cv_files WHERE profile_id = %s""",
                    (profile_id,),
                )
                row = cur.fetchone()
        return self._from_row(profile_id, row) if row else None

    def put(self, profile_id: str, filename: str, media_type: str, content: bytes, text: str) -> StoredCV:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_cv_files
                       (profile_id, filename, media_type, content, extracted_text, sha256, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, now())
                       ON CONFLICT (profile_id) DO UPDATE SET
                         filename = EXCLUDED.filename,
                         media_type = EXCLUDED.media_type,
                         content = EXCLUDED.content,
                         extracted_text = EXCLUDED.extracted_text,
                         sha256 = EXCLUDED.sha256,
                         updated_at = now()
                       RETURNING filename, media_type, content, extracted_text, updated_at""",
                    (profile_id, filename, media_type, content, text, hashlib.sha256(content).hexdigest()),
                )
                row = cur.fetchone()
        return self._from_row(profile_id, row)

    def delete(self, profile_id: str) -> bool:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM smartploy_cv_files WHERE profile_id = %s", (profile_id,))
                deleted = cur.rowcount > 0
        return deleted

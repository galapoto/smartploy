"""Tenant-isolated application kit storage with optimistic edit concurrency."""
from __future__ import annotations

from typing import Protocol

from psycopg import connect
from psycopg.types.json import Jsonb

from .application_workspace import (
    ApplicationWorkspace, WorkspaceRevisionConflict, mark_applied, update_documents,
)


class WorkspaceRepository(Protocol):
    def get(self, profile_id: str, workspace_id: str) -> ApplicationWorkspace | None: ...
    def list(self, profile_id: str, limit: int = 100) -> list[ApplicationWorkspace]: ...
    def create_or_get(self, item: ApplicationWorkspace) -> tuple[ApplicationWorkspace, bool]: ...
    def edit(self, profile_id: str, workspace_id: str, *,
             expected_revision: int, cv_text: str, cover_letter_text: str) -> ApplicationWorkspace | None: ...
    def report_applied(self, profile_id: str, workspace_id: str, *,
                       expected_revision: int, reference: str) -> ApplicationWorkspace | None: ...
    def delete(self, profile_id: str, workspace_id: str) -> bool: ...


class MemoryWorkspaceRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ApplicationWorkspace] = {}

    def get(self, profile_id: str, workspace_id: str) -> ApplicationWorkspace | None:
        return self._items.get((profile_id, workspace_id))

    def list(self, profile_id: str, limit: int = 100) -> list[ApplicationWorkspace]:
        return sorted(
            (item for (pid, _), item in self._items.items() if pid == profile_id),
            key=lambda item: item.updated_at, reverse=True,
        )[:max(1, min(limit, 200))]

    def create_or_get(self, item: ApplicationWorkspace) -> tuple[ApplicationWorkspace, bool]:
        key = (item.profile_id, item.workspace_id)
        existing = self._items.get(key)
        if existing:
            return existing, False
        self._items[key] = item
        return item, True

    def edit(self, profile_id: str, workspace_id: str, *,
             expected_revision: int, cv_text: str, cover_letter_text: str) -> ApplicationWorkspace | None:
        current = self.get(profile_id, workspace_id)
        if current is None:
            return None
        if current.revision != expected_revision:
            raise WorkspaceRevisionConflict("This draft changed in another tab; reload before saving")
        updated = update_documents(current, cv_text=cv_text, cover_letter_text=cover_letter_text)
        self._items[(profile_id, workspace_id)] = updated
        return updated

    def report_applied(self, profile_id: str, workspace_id: str, *,
                       expected_revision: int, reference: str) -> ApplicationWorkspace | None:
        current = self.get(profile_id, workspace_id)
        if current is None:
            return None
        if current.status == "self_reported_applied":
            return current
        if current.revision != expected_revision:
            raise WorkspaceRevisionConflict("Draft changed since you opened it; reload before updating")
        updated = mark_applied(current, reference=reference)
        self._items[(profile_id, workspace_id)] = updated
        return updated

    def delete(self, profile_id: str, workspace_id: str) -> bool:
        return self._items.pop((profile_id, workspace_id), None) is not None


class PostgresWorkspaceRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    @staticmethod
    def _select() -> str:
        return """SELECT workspace_id, profile_id, canonical_key, role_title, company,
                         application_url, cv_text, cover_letter_text, source_cv_sha256,
                         approved_evidence_ids, job_fingerprint, revision, status,
                         self_reported_applied_at, self_reported_reference,
                         created_at, updated_at
                  FROM smartploy_application_workspaces"""

    @staticmethod
    def _row(row: tuple) -> ApplicationWorkspace:
        return ApplicationWorkspace(
            workspace_id=row[0], profile_id=row[1], canonical_key=row[2],
            role_title=row[3], company=row[4], application_url=row[5],
            cv_text=row[6], cover_letter_text=row[7], source_cv_sha256=row[8],
            approved_evidence_ids=tuple(row[9] or ()), job_fingerprint=row[10],
            revision=int(row[11]), status=row[12],
            self_reported_applied_at=row[13].isoformat() if row[13] else "",
            self_reported_reference=row[14],
            created_at=row[15].isoformat(), updated_at=row[16].isoformat(),
        )

    def get(self, profile_id: str, workspace_id: str) -> ApplicationWorkspace | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(self._select() + " WHERE profile_id = %s AND workspace_id = %s",
                            (profile_id, workspace_id))
                row = cur.fetchone()
        return self._row(row) if row else None

    def list(self, profile_id: str, limit: int = 100) -> list[ApplicationWorkspace]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._select() + " WHERE profile_id = %s ORDER BY updated_at DESC LIMIT %s",
                    (profile_id, max(1, min(limit, 200))),
                )
                rows = cur.fetchall()
        return [self._row(row) for row in rows]

    def create_or_get(self, item: ApplicationWorkspace) -> tuple[ApplicationWorkspace, bool]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_application_workspaces (
                         workspace_id, profile_id, canonical_key, role_title, company,
                         application_url, cv_text, cover_letter_text, source_cv_sha256,
                         approved_evidence_ids, job_fingerprint, revision, status,
                         created_at, updated_at
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                 %s::timestamptz, %s::timestamptz)
                       ON CONFLICT (profile_id, canonical_key) DO NOTHING
                       RETURNING workspace_id""",
                    (
                        item.workspace_id, item.profile_id, item.canonical_key,
                        item.role_title, item.company, item.application_url,
                        item.cv_text, item.cover_letter_text, item.source_cv_sha256,
                        Jsonb(list(item.approved_evidence_ids)), item.job_fingerprint,
                        item.revision, item.status, item.created_at, item.updated_at,
                    ),
                )
                created = cur.fetchone() is not None
                cur.execute(
                    self._select() + " WHERE profile_id = %s AND canonical_key = %s",
                    (item.profile_id, item.canonical_key),
                )
                row = cur.fetchone()
        if row is None:
            raise RuntimeError("Unable to retrieve application workspace after creation")
        return self._row(row), created

    @staticmethod
    def _lock_claim_free_draft(
        cur, profile_id: str, workspace_id: str, expected_revision: int,
        *, allow_self_reported: bool = False,
    ) -> bool:
        """Share the original locked workspace and SP15a sticky claim boundary.

        Perform the claim lookup AFTER the row lock, in a new statement, to
        prevent a concurrent provider attempt committing between a stale
        READ COMMITTED statement snapshot and a manual edit/report update.
        """
        cur.execute(
            """SELECT revision,status,canonical_key
               FROM smartploy_application_workspaces
               WHERE profile_id=%s AND workspace_id=%s FOR UPDATE""",
            (profile_id,workspace_id),
        )
        row=cur.fetchone()
        if row is None:
            return False
        if allow_self_reported and row[1]=="self_reported_applied":
            return False
        if int(row[0])!=expected_revision or row[1]!="draft":
            raise WorkspaceRevisionConflict(
                "The application is no longer an editable draft at this revision"
            )
        cur.execute(
            """SELECT 1 FROM smartploy_employer_submit_claims
               WHERE profile_id=%s AND (workspace_id=%s OR canonical_key=%s)
               LIMIT 1""",
            (profile_id,workspace_id,str(row[2])),
        )
        if cur.fetchone():
            raise WorkspaceRevisionConflict(
                "An employer submission attempt is reserved. Do not edit or re-report."
            )
        return True

    def edit(self, profile_id: str, workspace_id: str, *,
             expected_revision: int, cv_text: str, cover_letter_text: str) -> ApplicationWorkspace | None:
        # Reuse the original optimistic revision check, now serialized with
        # the existing employer claim row lock. No duplicate lifecycle.
        from .application_workspace import _clean_text, MAX_CV_CHARACTERS, MAX_LETTER_CHARACTERS
        cv = _clean_text(cv_text, limit=MAX_CV_CHARACTERS, label="CV")
        letter = _clean_text(cover_letter_text, limit=MAX_LETTER_CHARACTERS, label="Cover letter")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                editable=self._lock_claim_free_draft(cur,profile_id,workspace_id,expected_revision)
                if editable:
                    cur.execute(
                        """UPDATE smartploy_application_workspaces
                           SET cv_text=%s,cover_letter_text=%s,
                               revision=revision+1,updated_at=now()
                           WHERE profile_id=%s AND workspace_id=%s
                             AND revision=%s AND status='draft'
                           RETURNING workspace_id""",
                        (cv,letter,profile_id,workspace_id,expected_revision),
                    )
                    changed=cur.fetchone() is not None
                else:
                    changed=False
        current=self.get(profile_id,workspace_id)
        if current is None:
            return None
        if changed:
            return current
        raise WorkspaceRevisionConflict("This draft is no longer editable at the expected revision")

    def report_applied(self, profile_id: str, workspace_id: str, *,
                       expected_revision: int, reference: str) -> ApplicationWorkspace | None:
        ref = str(reference or "").strip()
        if len(ref) > 250 or any(ord(char) < 32 for char in ref):
            from .application_workspace import WorkspaceError
            raise WorkspaceError("Application reference must be 250 printable characters or fewer")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                editable=self._lock_claim_free_draft(
                    cur,profile_id,workspace_id,expected_revision,allow_self_reported=True
                )
                if editable:
                    cur.execute(
                        """UPDATE smartploy_application_workspaces
                           SET status='self_reported_applied',self_reported_applied_at=now(),
                               self_reported_reference=%s,revision=revision+1,updated_at=now()
                           WHERE profile_id=%s AND workspace_id=%s
                             AND revision=%s AND status='draft'
                           RETURNING workspace_id""",
                        (ref,profile_id,workspace_id,expected_revision),
                    )
                    changed=cur.fetchone() is not None
                else:
                    changed=False
        current=self.get(profile_id,workspace_id)
        if current is None:
            return None
        if changed or current.status=="self_reported_applied":
            return current
        raise WorkspaceRevisionConflict("Draft changed since you opened it; reload before updating")

    def delete(self, profile_id: str, workspace_id: str) -> bool:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM smartploy_application_workspaces WHERE profile_id = %s AND workspace_id = %s",
                    (profile_id, workspace_id),
                )
                return cur.rowcount > 0

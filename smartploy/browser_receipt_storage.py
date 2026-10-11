"""Owner-scoped, idempotent, browser-observed application receipts."""
from __future__ import annotations

from psycopg import connect

from .browser_receipt import BrowserReceipt


class ReceiptConflict(ValueError):
    pass


class MemoryBrowserReceiptRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], BrowserReceipt] = {}

    def get(self, profile_id: str, workspace_id: str) -> BrowserReceipt | None:
        return self.items.get((profile_id, workspace_id))

    def record(self, item: BrowserReceipt) -> BrowserReceipt:
        key = (item.profile_id, item.workspace_id)
        old = self.items.get(key)
        if old:
            if old.digest != item.digest:
                raise ReceiptConflict("A different employer receipt is already recorded for this draft")
            return old
        self.items[key] = item
        return item


class PostgresBrowserReceiptRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL DSN is required")

    @staticmethod
    def _from_row(row: tuple) -> BrowserReceipt:
        return BrowserReceipt(
            profile_id=row[0], workspace_id=row[1], document_revision=int(row[2]),
            document_sha256=row[3], reference=row[4],
            confirmation_page_url=row[5], confirmation_page_sha256=row[6],
            observed_at=row[7].isoformat(), digest=row[8], status=row[9],
        )

    @staticmethod
    def _select() -> str:
        return """SELECT profile_id, workspace_id, document_revision,
                         document_sha256, reference, confirmation_page_url,
                         confirmation_page_sha256, observed_at, evidence_digest, status
                  FROM smartploy_browser_receipts"""

    def get(self, profile_id: str, workspace_id: str) -> BrowserReceipt | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    self._select() + " WHERE profile_id = %s AND workspace_id = %s",
                    (profile_id, workspace_id),
                )
                row = cursor.fetchone()
        return self._from_row(row) if row else None

    def record(self, item: BrowserReceipt) -> BrowserReceipt:
        with connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO smartploy_browser_receipts
                       (profile_id, workspace_id, document_revision,
                        document_sha256, reference, confirmation_page_url,
                        confirmation_page_sha256, observed_at, evidence_digest, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s, %s)
                       ON CONFLICT (profile_id, workspace_id) DO NOTHING""",
                    (
                        item.profile_id, item.workspace_id, item.document_revision,
                        item.document_sha256, item.reference,
                        item.confirmation_page_url, item.confirmation_page_sha256,
                        item.observed_at, item.digest, item.status,
                    ),
                )
        recorded = self.get(item.profile_id, item.workspace_id)
        if recorded is None:
            raise RuntimeError("Browser receipt record did not persist")
        if recorded.digest != item.digest:
            raise ReceiptConflict("A different employer receipt is already recorded for this draft")
        return recorded

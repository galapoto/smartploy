"""Private, recipient-initiated moderation reports for SmartPloy social DMs.

Reports are actionable only through a separately allowlisted operator inbox.
A report does not notify employers, publish user data, or automatically punish
any account. No duplicate copy of message text is retained in the report row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from threading import Lock
from uuid import uuid4

from psycopg import connect

from .social_network import MemorySocialRepository


_REPORT_ID = re.compile(r"report-[a-f0-9]{32}\Z")
_MESSAGE_ID = re.compile(r"msg-[a-f0-9]{32}\Z")
_REASONS = frozenset(("spam", "harassment", "scam", "impersonation", "other"))
DAILY_REPORT_LIMIT = 20


class ReportError(ValueError):
    """A private report action was invalid."""


class ReportNotFound(ReportError):
    """An item is absent or the current signed-in user cannot access it."""


class ReportRateLimited(ReportError):
    """A sender cannot submit further reports in the current daily window."""


def validate_report(message_id: str, reason: str, note: str) -> tuple[str, str, str]:
    if not isinstance(message_id, str) or not _MESSAGE_ID.fullmatch(message_id):
        raise ReportNotFound("This received message is not available")
    if not isinstance(reason, str) or reason not in _REASONS:
        raise ReportError("Choose a supported reason for this report")
    if not isinstance(note, str):
        raise ReportError("Report note must be text")
    cleaned = note.strip()
    if len(cleaned) > 500 or any(
        ord(char) == 127 or (ord(char) < 32 and char not in "\n\t")
        for char in cleaned
    ):
        raise ReportError("Report note must be at most 500 readable characters")
    return message_id, reason, cleaned


def _iso(value: datetime | str | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


@dataclass
class Report:
    report_id: str
    reporter_id: str
    reported_user_id: str
    message_id: str
    reason: str
    note: str
    state: str
    created_at: str
    reviewed_at: str | None = None
    reviewed_by: str | None = None

    def owner_view(self) -> dict[str, object]:
        return {"report_id": self.report_id, "message_id": self.message_id,
                "reason": self.reason, "state": self.state,
                "created_at": self.created_at}

    def operator_view(self, reporter: str, reported: str, preview: str) -> dict[str, object]:
        return {**self.owner_view(), "note": self.note,
                "reported_handle": reported, "reporter_handle": reporter,
                "message_preview": preview[:240],
                "reviewed_at": self.reviewed_at}


class MemorySocialReportRepository:
    """Offline parity fixture, not a durable production reporting system."""

    def __init__(self, social: MemorySocialRepository) -> None:
        self.social = social
        self._lock = Lock()
        self._reports: dict[str, Report] = {}

    def submit(self, owner: str, message_id: str, reason: str, note: str = "") -> dict[str, object]:
        message_id, reason, note = validate_report(message_id, reason, note)
        with self._lock, self.social._lock:
            message = next((m for m in self.social._messages
                            if m.message_id == message_id and m.recipient_id == owner), None)
            if message is None:
                raise ReportNotFound("This received message is not available")
            duplicate = next(
                (r for r in self._reports.values()
                 if r.reporter_id == owner and r.message_id == message_id), None
            )
            if duplicate is not None:
                return {"report": duplicate.owner_view(), "created": False}
            threshold = datetime.now(timezone.utc) - timedelta(days=1)
            if sum(1 for r in self._reports.values()
                   if r.reporter_id == owner and
                   datetime.fromisoformat(r.created_at) >= threshold) >= DAILY_REPORT_LIMIT:
                raise ReportRateLimited("Daily reporting limit reached; try again later")
            record = Report(
                report_id="report-" + uuid4().hex, reporter_id=owner,
                reported_user_id=message.sender_id, message_id=message_id,
                reason=reason, note=note, state="open",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._reports[record.report_id] = record
            return {"report": record.owner_view(), "created": True}

    def my_reports(self, owner: str, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ReportError("Report limit must be 1–100")
        with self._lock:
            items = [x for x in self._reports.values() if x.reporter_id == owner]
            items.sort(key=lambda x: (x.created_at, x.report_id), reverse=True)
            return {"reports": [x.owner_view() for x in items[:limit]], "private": True}

    def moderator_queue(self, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ReportError("Report limit must be 1–100")
        with self._lock, self.social._lock:
            items = list(self._reports.values())
            items.sort(key=lambda x: (x.state != "open", -datetime.fromisoformat(
                x.created_at).timestamp()))
            result = []
            for record in items[:limit]:
                message = next((m for m in self.social._messages
                                if m.message_id == record.message_id), None)
                if message is None:
                    continue
                reporter = self.social._profiles.get(record.reporter_id)
                reported = self.social._profiles.get(record.reported_user_id)
                result.append(record.operator_view(
                    reporter.handle if reporter else "[private]",
                    reported.handle if reported else "[private]",
                    message.body,
                ))
            return {"reports": result, "operator_only": True}

    def mark_reviewed(self, operator: str, report_id: str) -> dict[str, object]:
        if not isinstance(report_id, str) or not _REPORT_ID.fullmatch(report_id):
            raise ReportNotFound("Report not found")
        with self._lock:
            report = self._reports.get(report_id)
            if report is None:
                raise ReportNotFound("Report not found")
            if report.state == "open":
                report.state = "reviewed"
                report.reviewed_at = datetime.now(timezone.utc).isoformat()
                report.reviewed_by = operator
            return {"report_id": report_id, "state": report.state,
                    "reviewed_at": report.reviewed_at}


class PostgresSocialReportRepository:
    """Transactional, owner-checked report storage and operator-only triage."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @staticmethod
    def _owner_view(row: tuple) -> dict[str, object]:
        return {"report_id": row[0], "message_id": row[1],
                "reason": row[2], "state": row[3],
                "created_at": _iso(row[4])}

    def submit(self, owner: str, message_id: str, reason: str, note: str = "") -> dict[str, object]:
        message_id, reason, note = validate_report(message_id, reason, note)
        with connect(self.dsn) as conn, conn.cursor() as cur:
            # Lock the recipient across API workers before counting reports.
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        ("smartploy-social-report-" + owner,))
            cur.execute(
                """SELECT sender_id FROM smartploy_social_messages
                   WHERE message_id=%s AND recipient_id=%s""",
                (message_id, owner),
            )
            source = cur.fetchone()
            if not source:
                raise ReportNotFound("This received message is not available")
            cur.execute(
                """SELECT report_id,message_id,reason,state,created_at
                   FROM smartploy_social_reports
                   WHERE reporter_id=%s AND message_id=%s""",
                (owner, message_id),
            )
            previous = cur.fetchone()
            if previous:
                return {"report": self._owner_view(previous), "created": False}
            cur.execute(
                """SELECT COUNT(*) FROM smartploy_social_reports
                   WHERE reporter_id=%s
                     AND created_at>now() - interval '24 hours'""",
                (owner,),
            )
            if cur.fetchone()[0] >= DAILY_REPORT_LIMIT:
                raise ReportRateLimited("Daily reporting limit reached; try again later")
            report_id = "report-" + uuid4().hex
            cur.execute(
                """INSERT INTO smartploy_social_reports
                   (report_id,reporter_id,reported_user_id,message_id,reason,note)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   RETURNING report_id,message_id,reason,state,created_at""",
                (report_id, owner, source[0], message_id, reason, note),
            )
            row = cur.fetchone()
            return {"report": self._owner_view(row), "created": True}

    def my_reports(self, owner: str, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ReportError("Report limit must be 1–100")
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT report_id,message_id,reason,state,created_at
                   FROM smartploy_social_reports
                   WHERE reporter_id=%s
                   ORDER BY created_at DESC,report_id DESC LIMIT %s""",
                (owner, limit),
            )
            items = [self._owner_view(row) for row in cur.fetchall()]
        return {"reports": items, "private": True}

    def moderator_queue(self, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ReportError("Report limit must be 1–100")
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT r.report_id,r.message_id,r.reason,r.state,r.created_at,
                          r.note, COALESCE(sender.handle,'[private]'),
                          COALESCE(receiver.handle,'[private]'),
                          LEFT(m.body,240),r.reviewed_at
                   FROM smartploy_social_reports r
                   JOIN smartploy_social_messages m ON m.message_id=r.message_id
                   LEFT JOIN smartploy_social_profiles sender
                     ON sender.user_id=r.reported_user_id
                   LEFT JOIN smartploy_social_profiles receiver
                     ON receiver.user_id=r.reporter_id
                   ORDER BY CASE WHEN r.state='open' THEN 0 ELSE 1 END,
                            r.created_at DESC,r.report_id DESC LIMIT %s""",
                (limit,),
            )
            result = []
            for row in cur.fetchall():
                result.append({
                    **self._owner_view(row),
                    "note": row[5], "reported_handle": row[6],
                    "reporter_handle": row[7], "message_preview": row[8],
                    "reviewed_at": _iso(row[9]),
                })
        return {"reports": result, "operator_only": True}

    def mark_reviewed(self, operator: str, report_id: str) -> dict[str, object]:
        if not isinstance(report_id, str) or not _REPORT_ID.fullmatch(report_id):
            raise ReportNotFound("Report not found")
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE smartploy_social_reports
                   SET state='reviewed',reviewed_at=now(),reviewed_by=%s
                   WHERE report_id=%s AND state='open'
                   RETURNING state,reviewed_at""",
                (operator, report_id),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """SELECT state,reviewed_at FROM smartploy_social_reports
                       WHERE report_id=%s""", (report_id,),
                )
                row = cur.fetchone()
            if row is None:
                raise ReportNotFound("Report not found")
            return {"report_id": report_id, "state": row[0],
                    "reviewed_at": _iso(row[1])}

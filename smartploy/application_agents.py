"""SP22 Agent Zero: durable, owner-scoped application cases and in-app reminders.

This intentionally performs no model inference, email, calls, browser actions,
employer submissions or remote notifications. PostgreSQL is the only durable
backend: no memory fallback is offered as a headless agent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Literal

from psycopg import connect

from .application_followups import (
    MILESTONE_EVENTS, ORDER, SUBMITTED_WORKSPACE_STATUSES, TERMINAL_MILESTONES,
    due_message, followup_draft, next_case_due,
)


class ApplicationAgentConflict(ValueError):
    """The agent changed, stopped, or is not in the requested state."""


AgentAction = Literal["pause", "resume", "close"]
FOLLOW_UP_DELAY = timedelta(days=1)
CREATED_MESSAGE = "This job now has a private application agent. No employer was contacted."
DUE_MESSAGE = "Review your application and check for any employer response."
STATE_MESSAGES = {
    "pause": "Application tracking paused. No further reminders will be scheduled.",
    "resume": "Application tracking resumed. Your next reminder is scheduled.",
    "close": "Application agent closed. It will not wake or contact anyone.",
}
STATE_EVENTS = {"pause": "case_paused", "resume": "case_resumed", "close": "case_closed"}


def _now(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ValueError("Agent time must be timezone-aware")
    return result.astimezone(timezone.utc)


class PostgresApplicationAgentRepository:
    """A logical worker per case, no extra daemon/process per application."""

    _COLUMNS = """
        SELECT a.agent_id, a.workspace_id, w.canonical_key, w.role_title,
               w.company, a.state, a.revision, a.next_due_at, a.last_woke_at,
               a.created_at, a.updated_at, a.closed_at, a.close_reason,
               a.milestone, a.followups_sent, a.last_followup_at, w.status,
               a.observed_workspace_status
        FROM smartploy_application_agents a
        JOIN smartploy_application_workspaces w ON w.workspace_id = a.workspace_id
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise ValueError("PostgreSQL is required for durable application agents")

    @staticmethod
    def _public(row: tuple[Any, ...]) -> dict[str, Any]:
        def iso(value: datetime | None) -> str:
            return value.isoformat() if value is not None else ""

        return {
            "agent_id": row[0],
            "workspace_id": row[1],
            "canonical_key": row[2],
            "role_title": row[3],
            "company": row[4],
            "state": row[5],
            "revision": row[6],
            "next_due_at": iso(row[7]),
            "last_woke_at": iso(row[8]),
            "created_at": iso(row[9]),
            "updated_at": iso(row[10]),
            "closed_at": iso(row[11]),
            "close_reason": row[12],
            "milestone": row[13],
            "followups_sent": row[14],
            "last_followup_at": iso(row[15]),
            "workspace_status": row[16],
            "observed_workspace_status": row[17],
            "milestone_source": "candidate_self_report" if row[13] != "none" else "none",
            "followup_suggestion": (
                followup_draft(row[4], row[3])
                if row[5] == "active" and row[16] in SUBMITTED_WORKSPACE_STATUSES
                and row[13] in {"none", "recruiter_replied"} and row[14] < 2
                else ""
            ),
            "external_actions_authorized": False,
            "employer_contacted": False,
            "notification_channel": "in_app_only",
        }

    @staticmethod
    def _event(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "sequence": row[0],
            "event_type": row[1],
            "message": row[2],
            "occurred_at": row[3].isoformat(),
            "external_actions_performed": 0,
        }

    def create_or_get(
        self, profile_id: str, workspace_id: str, *, now: datetime | None = None
    ) -> tuple[dict[str, Any] | None, bool]:
        owner, workspace = str(profile_id or "").strip(), str(workspace_id or "").strip()
        if not owner or not workspace:
            raise ValueError("An existing owner-bound application workspace is required")
        moment = _now(now)
        identity = "agent-" + sha256(
            (owner + "\0" + workspace).encode("utf-8")
        ).hexdigest()[:32]
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_application_agents
                           (agent_id, workspace_id, profile_id, next_due_at,
                            created_at, updated_at, observed_workspace_status)
                       SELECT %s, w.workspace_id, w.profile_id,
                              CASE WHEN w.status = 'draft' THEN %s
                                   ELSE GREATEST(
                                       %s, COALESCE(
                                           w.self_reported_applied_at, w.updated_at
                                       ) + INTERVAL '7 days')
                              END,
                              %s, %s, w.status
                       FROM smartploy_application_workspaces w
                       WHERE w.workspace_id = %s AND w.profile_id = %s
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests er
                             WHERE er.profile_id = w.profile_id
                         )
                       ON CONFLICT (workspace_id) DO NOTHING
                       RETURNING agent_id""",
                    (identity, moment, moment, moment, moment, workspace, owner),
                )
                created = cur.fetchone() is not None
                if created:
                    cur.execute(
                        """INSERT INTO smartploy_application_agent_events
                           (agent_id, sequence, event_type, message, occurred_at)
                           VALUES (%s, 1, 'case_created', %s, %s)""",
                        (identity, CREATED_MESSAGE, moment),
                    )
                cur.execute(
                    self._COLUMNS + """
                    WHERE a.profile_id = %s AND a.workspace_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM smartploy_account_erasure_requests er
                          WHERE er.profile_id = a.profile_id
                      )""",
                    (owner, workspace),
                )
                found = cur.fetchone()
        return (self._public(found) if found else None), created

    def get(self, profile_id: str, agent_id: str) -> dict[str, Any] | None:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._COLUMNS + """
                    WHERE a.profile_id = %s AND a.agent_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM smartploy_account_erasure_requests er
                          WHERE er.profile_id = a.profile_id
                      )""",
                    (profile_id, agent_id),
                )
                row = cur.fetchone()
        return self._public(row) if row else None

    def get_for_workspace(
        self, profile_id: str, workspace_id: str
    ) -> dict[str, Any] | None:
        """Avoid listing/capping all a user's agents to display one workspace."""
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._COLUMNS + """
                    WHERE a.profile_id=%s AND a.workspace_id=%s
                      AND NOT EXISTS (
                          SELECT 1 FROM smartploy_account_erasure_requests er
                          WHERE er.profile_id=a.profile_id
                      )""",
                    (profile_id, workspace_id),
                )
                row = cur.fetchone()
        return self._public(row) if row else None

    def list(self, profile_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    self._COLUMNS + """
                    WHERE a.profile_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM smartploy_account_erasure_requests er
                          WHERE er.profile_id = a.profile_id
                      )
                    ORDER BY a.updated_at DESC, a.agent_id LIMIT %s""",
                    (profile_id, limit),
                )
                rows = cur.fetchall()
        return [self._public(row) for row in rows]

    def events(
        self, profile_id: str, agent_id: str, *, after_sequence: int = 0
    ) -> list[dict[str, Any]]:
        if not 0 <= after_sequence <= 2147483647:
            raise ValueError("Invalid event cursor")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT e.sequence, e.event_type, e.message, e.occurred_at
                       FROM smartploy_application_agent_events e
                       JOIN smartploy_application_agents a
                         ON a.agent_id = e.agent_id
                       WHERE a.profile_id = %s AND a.agent_id = %s
                         AND e.sequence > %s
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests er
                             WHERE er.profile_id = a.profile_id
                         )
                       ORDER BY e.sequence LIMIT 100""",
                    (profile_id, agent_id, after_sequence),
                )
                rows = cur.fetchall()
        return [self._event(row) for row in rows]

    def transition(
        self, profile_id: str, agent_id: str, *,
        action: AgentAction, expected_revision: int, now: datetime | None = None,
    ) -> dict[str, Any] | None:
        if action not in STATE_EVENTS:
            raise ValueError("Unsupported application-agent action")
        moment = _now(now)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.state, a.revision
                       FROM smartploy_application_agents a
                       WHERE a.agent_id = %s AND a.profile_id = %s
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests er
                             WHERE er.profile_id = a.profile_id
                         )
                       FOR UPDATE""",
                    (agent_id, profile_id),
                )
                previous = cur.fetchone()
                if previous is None:
                    return None
                state, revision = previous
                if revision != expected_revision:
                    raise ApplicationAgentConflict("Agent changed in another tab. Reload.")
                if (
                    state == "closed"
                    or (action == "pause" and state != "active")
                    or (action == "resume" and state != "paused")
                ):
                    raise ApplicationAgentConflict("Agent is no longer in the requested state")
                next_state = {"pause": "paused", "resume": "active", "close": "closed"}[action]
                next_due = moment if action == "resume" else None
                closed_at = moment if action == "close" else None
                reason = "owner_closed" if action == "close" else ""
                cur.execute(
                    """UPDATE smartploy_application_agents
                       SET state = %s, revision = revision + 1,
                           next_due_at = %s, updated_at = %s,
                           closed_at = %s, close_reason = %s
                       WHERE agent_id = %s AND profile_id = %s""",
                    (next_state, next_due, moment, closed_at, reason, agent_id, profile_id),
                )
                cur.execute(
                    """INSERT INTO smartploy_application_agent_events
                       (agent_id, sequence, event_type, message, occurred_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        agent_id, revision + 1, STATE_EVENTS[action],
                        STATE_MESSAGES[action], moment,
                    ),
                )
                cur.execute(
                    self._COLUMNS + " WHERE a.agent_id = %s AND a.profile_id = %s",
                    (agent_id, profile_id),
                )
                row = cur.fetchone()
        return self._public(row) if row else None


    def record_milestone(
        self, profile_id: str, agent_id: str, *,
        milestone: str, expected_revision: int, now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Only the applicant may attest a stage, never a pasted recruiter mail."""
        if milestone not in MILESTONE_EVENTS:
            raise ValueError("Unsupported application milestone")
        moment = _now(now)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.state, a.revision, a.milestone, a.followups_sent,
                              w.status
                       FROM smartploy_application_agents a
                       JOIN smartploy_application_workspaces w
                         ON w.workspace_id = a.workspace_id
                       WHERE a.agent_id = %s AND a.profile_id = %s
                         AND NOT EXISTS (
                           SELECT 1 FROM smartploy_account_erasure_requests er
                           WHERE er.profile_id = a.profile_id
                         )
                       FOR UPDATE OF a, w""",
                    (agent_id, profile_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                state, revision, previous, count, workspace_status = row
                if revision != expected_revision:
                    raise ApplicationAgentConflict("Agent changed in another tab. Reload.")
                if state == "closed":
                    raise ApplicationAgentConflict("Closed agents cannot accept new events.")
                if workspace_status not in SUBMITTED_WORKSPACE_STATUSES:
                    raise ApplicationAgentConflict(
                        "First report your submission in Application Studio."
                    )
                if milestone not in TERMINAL_MILESTONES and (
                    ORDER[milestone] <= ORDER.get(previous, 100)
                ):
                    raise ApplicationAgentConflict(
                        "A repeated or earlier recruiter stage needs a new review."
                    )
                terminal = milestone in TERMINAL_MILESTONES
                next_state = "closed" if terminal else state
                next_due = (
                    None if terminal or state == "paused"
                    else next_case_due(milestone, workspace_status, moment, count)
                )
                cur.execute(
                    """UPDATE smartploy_application_agents
                       SET milestone=%s, state=%s, revision=revision+1,
                           next_due_at=%s, updated_at=%s, closed_at=%s,
                           close_reason=%s
                       WHERE agent_id=%s AND profile_id=%s""",
                    (
                        milestone, next_state, next_due, moment,
                        moment if terminal else None,
                        milestone if terminal else "",
                        agent_id, profile_id,
                    ),
                )
                event_type, message = MILESTONE_EVENTS[milestone]
                cur.execute(
                    """INSERT INTO smartploy_application_agent_events
                       (agent_id,sequence,event_type,message,occurred_at)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (agent_id, revision + 1, event_type, message, moment),
                )
                cur.execute(
                    self._COLUMNS + " WHERE a.agent_id=%s AND a.profile_id=%s",
                    (agent_id, profile_id),
                )
                latest = cur.fetchone()
        return self._public(latest) if latest else None


    def log_candidate_followup(
        self, profile_id: str, agent_id: str, *,
        expected_revision: int, now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Record a user-reported send, not an outgoing communication."""
        moment = _now(now)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.state,a.revision,a.milestone,a.followups_sent,w.status
                       FROM smartploy_application_agents a
                       JOIN smartploy_application_workspaces w
                         ON w.workspace_id=a.workspace_id
                       WHERE a.agent_id=%s AND a.profile_id=%s
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests er
                             WHERE er.profile_id=a.profile_id
                         )
                       FOR UPDATE OF a, w""",
                    (agent_id, profile_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                state, revision, milestone, count, workspace_status = row
                if revision != expected_revision:
                    raise ApplicationAgentConflict("Agent changed in another tab. Reload.")
                if (
                    state != "active"
                    or milestone not in {"none", "recruiter_replied"}
                    or workspace_status not in SUBMITTED_WORKSPACE_STATUSES
                    or count >= 2
                ):
                    raise ApplicationAgentConflict(
                        "This case cannot record another routine follow-up."
                    )
                next_due = next_case_due(
                    milestone, workspace_status, moment, count + 1,
                    last_sent_at=moment,
                )
                cur.execute(
                    """UPDATE smartploy_application_agents
                       SET followups_sent=followups_sent+1,
                           last_followup_at=%s, next_due_at=%s,
                           revision=revision+1, updated_at=%s
                       WHERE agent_id=%s AND profile_id=%s""",
                    (moment, next_due, moment, agent_id, profile_id),
                )
                cur.execute(
                    """INSERT INTO smartploy_application_agent_events
                       (agent_id,sequence,event_type,message,occurred_at)
                       VALUES (%s,%s,'candidate_reported_followup',%s,%s)""",
                    (
                        agent_id, revision + 1,
                        "You reported sending a follow-up. SmartPloy did not send it.",
                        moment,
                    ),
                )
                cur.execute(
                    self._COLUMNS + " WHERE a.agent_id=%s AND a.profile_id=%s",
                    (agent_id, profile_id),
                )
                latest = cur.fetchone()
        return self._public(latest) if latest else None

    def reconcile_workspace_updates(
        self, *, limit: int = 20, now: datetime | None = None,
    ) -> int:
        """Atomically consume original workspace submission events, no sends.

        This is the bridge from the real document/provider status into the
        long-lived logical agent. It cannot infer a provider applicationId;
        the source workspace must already have been updated by the original
        authenticated manual reporting or provider-acknowledged ledger.
        """
        moment = _now(now)
        size = max(1, min(int(limit), 50))
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.agent_id, a.revision, a.milestone,
                              a.followups_sent, a.last_followup_at, a.next_due_at,
                              a.observed_workspace_status, w.status,
                              w.self_reported_applied_at, w.updated_at
                       FROM smartploy_application_agents a
                       JOIN smartploy_application_workspaces w
                         ON w.workspace_id = a.workspace_id
                            AND w.profile_id = a.profile_id
                       WHERE a.state = 'active'
                         AND a.observed_workspace_status <> w.status
                         AND NOT EXISTS (
                           SELECT 1 FROM smartploy_account_erasure_requests er
                           WHERE er.profile_id = a.profile_id
                         )
                       ORDER BY w.updated_at, a.agent_id
                       LIMIT %s FOR UPDATE OF a, w SKIP LOCKED""",
                    (size,),
                )
                changed = cur.fetchall()
                for (
                    agent_id, revision, milestone, followup_count, last_sent_at,
                    previous_due, previously_observed, workspace_status,
                    self_applied_at, workspace_updated,
                ) in changed:
                    if workspace_status == "self_reported_applied":
                        event_type = "application_self_reported"
                        message = (
                            "You reported submitting this application. "
                            "The employer has not independently confirmed it."
                        )
                        submitted_at = self_applied_at or workspace_updated
                    elif workspace_status == "provider_acknowledged":
                        event_type = "application_provider_acknowledged"
                        message = (
                            "The authorized provider acknowledged the submitted "
                            "application. This is not a hiring decision."
                        )
                        submitted_at = workspace_updated
                    else:
                        event_type = "application_draft_review"
                        message = (
                            "This application is marked as a draft. "
                            "Review it before reporting another employer action."
                        )
                        submitted_at = workspace_updated

                    if workspace_status == "draft":
                        next_due = next_case_due(
                            milestone, workspace_status, moment, followup_count,
                            last_sent_at=last_sent_at,
                        )
                    elif (
                        previously_observed == "self_reported_applied"
                        and workspace_status == "provider_acknowledged"
                    ):
                        # A stronger independent provider acknowledgement
                        # does not restart an already-running application
                        # follow-up clock or send another notification.
                        next_due = previous_due
                    elif milestone == "none" and followup_count == 0:
                        # Reuse career-ops applied-first cadence, but anchor it
                        # to the REAL application date, not the older draft
                        # reminder. Never suggest immediate outreach on submit.
                        next_due = next_case_due(
                            milestone, workspace_status, submitted_at, 0,
                        )
                        if next_due is not None:
                            next_due = max(moment, next_due)
                    else:
                        # Preserve existing interview/reply follow-up timing if
                        # provider acknowledgment is received later.
                        next_due = previous_due

                    cur.execute(
                        """UPDATE smartploy_application_agents
                           SET observed_workspace_status=%s,
                               next_due_at=%s,
                               revision=revision+1, updated_at=%s
                           WHERE agent_id=%s AND state='active'""",
                        (workspace_status, next_due, moment, agent_id),
                    )
                    cur.execute(
                        """INSERT INTO smartploy_application_agent_events
                           (agent_id, sequence, event_type, message, occurred_at)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (agent_id, revision + 1, event_type, message, moment),
                    )
        return len(changed)

    def process_due(
        self, *, limit: int = 20, now: datetime | None = None
    ) -> dict[str, int | bool]:
        """Idempotent owner-scoped in-app wakeups; never external notifications.

        SKIP LOCKED and a due-time update in the same transaction avoid
        duplicate reminders across independent worker processes.
        """
        moment = _now(now)
        size = max(1, min(int(limit), 50))
        reconciled = self.reconcile_workspace_updates(limit=size, now=moment)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.agent_id, a.revision, a.milestone,
                              a.followups_sent, w.status
                       FROM smartploy_application_agents a
                       JOIN smartploy_application_workspaces w
                         ON w.workspace_id=a.workspace_id
                       WHERE a.state = 'active' AND a.next_due_at <= %s
                         AND NOT EXISTS (
                             SELECT 1 FROM smartploy_account_erasure_requests er
                             WHERE er.profile_id = a.profile_id
                         )
                       ORDER BY a.next_due_at, a.agent_id
                       LIMIT %s FOR UPDATE OF a SKIP LOCKED""",
                    (moment, size),
                )
                claimed = cur.fetchall()
                for agent_id, revision, milestone, count, workspace_status in claimed:
                    event_type, message = due_message(
                        milestone, workspace_status, count,
                    )
                    next_due = next_case_due(
                        milestone, workspace_status, moment, count,
                    )
                    cur.execute(
                        """UPDATE smartploy_application_agents
                           SET revision = revision + 1,
                               next_due_at = %s, last_woke_at = %s, updated_at = %s
                           WHERE agent_id = %s AND state = 'active'""",
                        (next_due, moment, moment, agent_id),
                    )
                    cur.execute(
                        """INSERT INTO smartploy_application_agent_events
                           (agent_id, sequence, event_type, message, occurred_at)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (agent_id, revision + 1, event_type, message, moment),
                    )
        return {
            "workspace_updates_reconciled": reconciled,
            "woken": len(claimed),
            "in_app_reminders": len(claimed),
            "external_actions_performed": 0,
            "employer_contacts": 0,
        }

"""Opt-in SmartPloy professional connections and private, mutual-follow messaging.

No public directory, CV exposure, email sharing, employer messaging, federation,
end-to-end encryption or automatic outreach. Each operation uses the verified
server identity, never a user-selected sender ID. A user must opt in to a handle,
and two users must follow each other before either can send a message.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from threading import Lock
from uuid import uuid4

from psycopg import connect, errors


HANDLE = re.compile(r"[a-z][a-z0-9_]{2,23}\Z")
RESERVED = frozenset({"admin", "administrator", "support", "smartploy",
                      "system", "moderator", "security", "helpdesk"})
MESSAGE_LIMIT = 2000
RATE_LIMIT = 12


class SocialError(ValueError):
    """A user-controlled social action was invalid or not permitted."""


class SocialConflict(SocialError):
    """Handle already used or incompatible profile state."""


class SocialNotFound(SocialError):
    """Do not disclose hidden, blocked, or nonexistent user identities."""


class SocialRateLimited(SocialError):
    """Rate-limited sender; no message was inserted."""


def clean_handle(value: str) -> str:
    if not isinstance(value, str):
        raise SocialError("A valid handle is required")
    handle = value.strip().casefold()
    if not HANDLE.fullmatch(handle) or handle in RESERVED:
        raise SocialError("Handle must be 3–24 characters: letters, digits, underscore")
    return handle


def clean_name(value: str) -> str:
    if not isinstance(value, str):
        raise SocialError("Display name must be text")
    name = " ".join(value.split())
    if not 2 <= len(name) <= 60 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise SocialError("Display name must be 2–60 printable characters")
    return name


def clean_message(value: str) -> str:
    if not isinstance(value, str):
        raise SocialError("Message must be text")
    body = value.strip()
    if not 1 <= len(body) <= MESSAGE_LIMIT or any(
        (ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in body
    ):
        raise SocialError("Write 1–2000 characters without control characters")
    return body


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SocialPerson:
    user_id: str
    handle: str
    display_name: str
    discoverable: bool = False

    def public(self) -> dict[str, object]:
        return {"handle": self.handle, "display_name": self.display_name,
                "discoverable": self.discoverable}


@dataclass(frozen=True)
class DirectMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    body: str
    created_at: str

    def public(self, viewer: str) -> dict[str, object]:
        return {
            "message_id": self.message_id, "body": self.body,
            "mine": self.sender_id == viewer, "created_at": self.created_at,
        }


class MemorySocialRepository:
    """Deterministic offline/tests backend; not a durable production substitute."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._profiles: dict[str, SocialPerson] = {}
        self._handles: dict[str, str] = {}
        self._follows: set[tuple[str, str]] = set()
        self._blocks: set[tuple[str, str]] = set()
        self._messages: list[DirectMessage] = []

    def me(self, owner: str) -> dict[str, object]:
        with self._lock:
            person = self._profiles.get(owner)
            return {"profile": person.public() if person else None,
                    "opted_in": bool(person and person.discoverable)}

    def save_profile(self, owner: str, handle: str, display_name: str,
                     discoverable: bool) -> dict[str, object]:
        handle, name = clean_handle(handle), clean_name(display_name)
        if not isinstance(discoverable, bool) or not owner:
            raise SocialError("Verified user and an explicit privacy choice required")
        with self._lock:
            claimed = self._handles.get(handle)
            if claimed is not None and claimed != owner:
                raise SocialConflict("This handle is unavailable")
            previous = self._profiles.get(owner)
            if previous is not None and previous.handle != handle:
                self._handles.pop(previous.handle, None)
            self._profiles[owner] = SocialPerson(owner, handle, name, discoverable)
            self._handles[handle] = owner
            if not discoverable:
                # Revocation is not a visual toggle. Former mutual followers
                # must explicitly reconnect after a future opt-in.
                self._follows = {
                    pair for pair in self._follows if owner not in pair
                }
            return {"profile": self._profiles[owner].public(), "opted_in": discoverable}

    def _person(self, owner: str, handle: str) -> SocialPerson:
        identifier = self._handles.get(clean_handle(handle))
        person = self._profiles.get(identifier or "")
        if person is None or not person.discoverable or (
            (owner, person.user_id) in self._blocks or
            (person.user_id, owner) in self._blocks
        ):
            raise SocialNotFound("This member is not available")
        return person

    def lookup(self, owner: str, handle: str) -> dict[str, object]:
        with self._lock:
            person = self._person(owner, handle)
            return {**person.public(),
                    "following": (owner, person.user_id) in self._follows,
                    "follows_you": (person.user_id, owner) in self._follows,
                    "self": person.user_id == owner}

    def follow(self, owner: str, handle: str, value: bool = True) -> dict[str, object]:
        with self._lock:
            own = self._profiles.get(owner)
            if own is None or not own.discoverable:
                raise SocialConflict("Enable your public handle to follow members")
            person = self._person(owner, handle)
            if person.user_id == owner:
                raise SocialError("You cannot follow yourself")
            if value:
                self._follows.add((owner, person.user_id))
            else:
                self._follows.discard((owner, person.user_id))
            return {"following": (owner, person.user_id) in self._follows,
                    "follows_you": (person.user_id, owner) in self._follows,
                    "handle": person.handle}

    def connections(self, owner: str) -> dict[str, object]:
        with self._lock:
            following, followers = [], []
            for src, dst in sorted(self._follows):
                person_id = dst if src == owner else src
                person = self._profiles.get(person_id)
                if person is None or not person.discoverable or (
                    (owner, person_id) in self._blocks or
                    (person_id, owner) in self._blocks
                ):
                    continue
                entry = {**person.public(),
                         "mutual": (dst, src) in self._follows}
                if src == owner:
                    following.append(entry)
                if dst == owner:
                    followers.append(entry)
            blocked = []
            for blocker, target in sorted(self._blocks):
                person = self._profiles.get(target)
                if blocker == owner and person is not None:
                    blocked.append({"handle": person.handle,
                                    "display_name": person.display_name})
            return {"following": following[:100], "followers": followers[:100],
                    "blocked": blocked[:100], "private": True}

    def block(self, owner: str, handle: str, value: bool = True) -> dict[str, object]:
        with self._lock:
            identifier = self._handles.get(clean_handle(handle))
            if not identifier or identifier == owner:
                raise SocialNotFound("This member is not available")
            if value:
                self._blocks.add((owner, identifier))
                self._follows.discard((owner, identifier))
                self._follows.discard((identifier, owner))
            else:
                self._blocks.discard((owner, identifier))
            return {"blocked": value}

    def _can_message(self, owner: str, handle: str) -> SocialPerson:
        target = self._person(owner, handle)
        if target.user_id == owner or not (
            (owner, target.user_id) in self._follows and
            (target.user_id, owner) in self._follows
        ):
            raise SocialNotFound("Mutual following is required for private messaging")
        return target

    def send(self, owner: str, handle: str, body: str) -> dict[str, object]:
        cleaned = clean_message(body)
        with self._lock:
            person = self._can_message(owner, handle)
            cutoff = _now() - timedelta(minutes=1)
            if sum(1 for msg in self._messages
                   if msg.sender_id == owner and
                   datetime.fromisoformat(msg.created_at) >= cutoff) >= RATE_LIMIT:
                raise SocialRateLimited("Too many messages; try again shortly")
            item = DirectMessage("msg-" + uuid4().hex, owner, person.user_id,
                                 cleaned, _now().isoformat())
            self._messages.append(item)
            return item.public(owner)

    def messages(self, owner: str, handle: str, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise SocialError("Message limit must be 1–100")
        with self._lock:
            person = self._can_message(owner, handle)
            msgs = [m for m in self._messages if
                    {m.sender_id, m.recipient_id} == {owner, person.user_id}]
            return {"messages": [msg.public(owner) for msg in msgs[-limit:]],
                    "handle": person.handle, "private": True}


class PostgresSocialRepository:
    """Durable owner-bound social records, using parameterized SQL throughout."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @staticmethod
    def _target(cur, owner: str, handle: str) -> tuple[str, str, str]:
        cur.execute(
            """SELECT p.user_id,p.handle,p.display_name
               FROM smartploy_social_profiles p
               JOIN smartploy_users u ON u.user_id=p.user_id
               WHERE p.handle=%s AND p.discoverable AND u.status='active'
               AND NOT EXISTS (
                   SELECT 1 FROM smartploy_social_blocks b
                   WHERE (b.blocker_id=%s AND b.blocked_id=p.user_id)
                      OR (b.blocker_id=p.user_id AND b.blocked_id=%s)
               )""",
            (clean_handle(handle), owner, owner),
        )
        found = cur.fetchone()
        if not found:
            raise SocialNotFound("This member is not available")
        return found

    @staticmethod
    def _mutual(cur, owner: str, target: str) -> None:
        cur.execute(
            """SELECT EXISTS (
                 SELECT 1 FROM smartploy_social_follows f
                 WHERE f.follower_id=%s AND f.followed_id=%s
               ) AND EXISTS (
                 SELECT 1 FROM smartploy_social_follows f
                 WHERE f.follower_id=%s AND f.followed_id=%s
               )""",
            (owner, target, target, owner),
        )
        if not cur.fetchone()[0]:
            raise SocialNotFound("Mutual following is required for private messaging")

    def me(self, owner: str) -> dict[str, object]:
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT handle,display_name,discoverable "
                "FROM smartploy_social_profiles WHERE user_id=%s",
                (owner,),
            )
            row = cur.fetchone()
        return {"profile": (
            {"handle": row[0], "display_name": row[1], "discoverable": row[2]}
            if row else None),
            "opted_in": bool(row and row[2])}

    def save_profile(self, owner: str, handle: str, display_name: str,
                     discoverable: bool) -> dict[str, object]:
        handle, name = clean_handle(handle), clean_name(display_name)
        if not isinstance(discoverable, bool) or not owner:
            raise SocialError("Verified user and an explicit privacy choice required")
        try:
            with connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_social_profiles
                         (user_id,handle,display_name,discoverable)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (user_id) DO UPDATE SET
                         handle=excluded.handle,display_name=excluded.display_name,
                         discoverable=excluded.discoverable,updated_at=now()
                       RETURNING handle,display_name,discoverable""",
                    (owner, handle, name, discoverable),
                )
                row = cur.fetchone()
                if not discoverable:
                    cur.execute(
                        """DELETE FROM smartploy_social_follows
                           WHERE follower_id=%s OR followed_id=%s""",
                        (owner, owner),
                    )
        except errors.UniqueViolation as exc:
            raise SocialConflict("This handle is unavailable") from exc
        return {"profile": {"handle": row[0], "display_name": row[1],
                            "discoverable": row[2]}, "opted_in": row[2]}

    def lookup(self, owner: str, handle: str) -> dict[str, object]:
        with connect(self.dsn) as conn, conn.cursor() as cur:
            user_id, actual_handle, name = self._target(cur, owner, handle)
            cur.execute(
                """SELECT
                  EXISTS(SELECT 1 FROM smartploy_social_follows
                         WHERE follower_id=%s AND followed_id=%s),
                  EXISTS(SELECT 1 FROM smartploy_social_follows
                         WHERE follower_id=%s AND followed_id=%s)""",
                (owner, user_id, user_id, owner),
            )
            following, follows_you = cur.fetchone()
        return {"handle": actual_handle, "display_name": name,
                "discoverable": True, "following": following,
                "follows_you": follows_you, "self": user_id == owner}

    def follow(self, owner: str, handle: str, value: bool = True) -> dict[str, object]:
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT discoverable FROM smartploy_social_profiles WHERE user_id=%s",
                (owner,),
            )
            own = cur.fetchone()
            if not own or not own[0]:
                raise SocialConflict("Enable your public handle to follow members")
            target, actual_handle, _ = self._target(cur, owner, handle)
            if target == owner:
                raise SocialError("You cannot follow yourself")
            if value:
                cur.execute(
                    """INSERT INTO smartploy_social_follows
                       (follower_id,followed_id) VALUES(%s,%s)
                       ON CONFLICT DO NOTHING""", (owner, target),
                )
            else:
                cur.execute(
                    """DELETE FROM smartploy_social_follows
                       WHERE follower_id=%s AND followed_id=%s""",
                    (owner, target),
                )
            cur.execute(
                """SELECT EXISTS (
                  SELECT 1 FROM smartploy_social_follows
                  WHERE follower_id=%s AND followed_id=%s
                )""", (target, owner),
            )
            follows_you = cur.fetchone()[0]
        return {"following": value, "follows_you": follows_you,
                "handle": actual_handle}

    def connections(self, owner: str) -> dict[str, object]:
        result: dict[str, object] = {"following": [], "followers": [],
                                     "blocked": [], "private": True}
        with connect(self.dsn) as conn, conn.cursor() as cur:
            for direction, field in [("follower_id", "following"),
                                     ("followed_id", "followers")]:
                target_field = "followed_id" if direction == "follower_id" else "follower_id"
                cur.execute(
                    f"""SELECT p.handle,p.display_name,
                         EXISTS(SELECT 1 FROM smartploy_social_follows rev
                           WHERE rev.follower_id=f.{target_field}
                             AND rev.followed_id=f.{direction})
                       FROM smartploy_social_follows f
                       JOIN smartploy_social_profiles p ON p.user_id=f.{target_field}
                       JOIN smartploy_users u ON u.user_id=p.user_id
                       WHERE f.{direction}=%s AND p.discoverable
                         AND u.status='active'
                         AND NOT EXISTS(SELECT 1 FROM smartploy_social_blocks b
                           WHERE (b.blocker_id=%s AND b.blocked_id=p.user_id)
                              OR (b.blocker_id=p.user_id AND b.blocked_id=%s))
                       ORDER BY f.created_at DESC LIMIT 100""",
                    (owner, owner, owner),
                )
                result[field] = [{"handle": r[0], "display_name": r[1],
                                  "discoverable": True, "mutual": r[2]}
                                 for r in cur.fetchall()]
            cur.execute(
                """SELECT p.handle,p.display_name
                   FROM smartploy_social_blocks b
                   JOIN smartploy_social_profiles p ON p.user_id=b.blocked_id
                   WHERE b.blocker_id=%s
                   ORDER BY b.created_at DESC LIMIT 100""",
                (owner,),
            )
            result["blocked"] = [{"handle": r[0], "display_name": r[1]}
                                 for r in cur.fetchall()]
        return result

    def block(self, owner: str, handle: str, value: bool = True) -> dict[str, object]:
        with connect(self.dsn) as conn, conn.cursor() as cur:
            # Block/unblock by the exact known handle; do not enumerate hidden users.
            cur.execute(
                "SELECT user_id FROM smartploy_social_profiles WHERE handle=%s",
                (clean_handle(handle),),
            )
            row = cur.fetchone()
            if not row or row[0] == owner:
                raise SocialNotFound("This member is not available")
            target = row[0]
            if value:
                cur.execute(
                    """INSERT INTO smartploy_social_blocks(blocker_id,blocked_id)
                       VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    (owner, target),
                )
                cur.execute(
                    """DELETE FROM smartploy_social_follows
                       WHERE (follower_id=%s AND followed_id=%s)
                          OR (follower_id=%s AND followed_id=%s)""",
                    (owner, target, target, owner),
                )
            else:
                cur.execute(
                    """DELETE FROM smartploy_social_blocks
                       WHERE blocker_id=%s AND blocked_id=%s""",
                    (owner, target),
                )
        return {"blocked": value}

    def send(self, owner: str, handle: str, body: str) -> dict[str, object]:
        body = clean_message(body)
        with connect(self.dsn) as conn, conn.cursor() as cur:
            # Serialize one sender's rate checks, including across API workers.
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        ("smartploy-social-send-" + owner,))
            target, _, _ = self._target(cur, owner, handle)
            if target == owner:
                raise SocialNotFound("Mutual following is required for private messaging")
            self._mutual(cur, owner, target)
            cur.execute(
                """SELECT COUNT(*) FROM smartploy_social_messages
                   WHERE sender_id=%s
                   AND created_at > now() - interval '1 minute'""",
                (owner,),
            )
            if cur.fetchone()[0] >= RATE_LIMIT:
                raise SocialRateLimited("Too many messages; try again shortly")
            message_id = "msg-" + uuid4().hex
            cur.execute(
                """INSERT INTO smartploy_social_messages
                       (message_id,sender_id,recipient_id,body)
                   VALUES (%s,%s,%s,%s) RETURNING created_at""",
                (message_id, owner, target, body),
            )
            created = cur.fetchone()[0].isoformat()
        return DirectMessage(message_id, owner, target, body, created).public(owner)

    def messages(self, owner: str, handle: str, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise SocialError("Message limit must be 1–100")
        with connect(self.dsn) as conn, conn.cursor() as cur:
            target, actual_handle, _ = self._target(cur, owner, handle)
            if target == owner:
                raise SocialNotFound("Mutual following is required for private messaging")
            self._mutual(cur, owner, target)
            cur.execute(
                """SELECT message_id,sender_id,recipient_id,body,created_at
                   FROM smartploy_social_messages
                   WHERE (sender_id=%s AND recipient_id=%s)
                      OR (sender_id=%s AND recipient_id=%s)
                   ORDER BY created_at DESC,message_id DESC LIMIT %s""",
                (owner, target, target, owner, limit),
            )
            items = [DirectMessage(r[0], r[1], r[2], r[3], r[4].isoformat())
                     for r in cur.fetchall()]
        return {"messages": [x.public(owner) for x in reversed(items)],
                "handle": actual_handle, "private": True}

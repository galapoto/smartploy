"""SP116: owner-private memory for application questions, not employer-send authority.

Reuses the existing SmartPloy profile tenant id and Postgres migration runner.
Only original Chrome-inspected unanswered, non-sensitive text questions may
be observed. The prompt is saved as a pending item immediately, allowing an
applicant to finish the profile later. An answer is NEVER inferred from a CV,
employer form or LLM and is never released without the applicant's separate
affirmative review. Consent/salary/immigration/EEO remain manual only.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import re
import unicodedata

from psycopg import connect

MAX_QUESTIONS_PER_INSPECTION = 12
MAX_PRIVATE_QUESTIONS = 100
MAX_ANSWER = 1500
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
SENSITIVE = re.compile(
    r"(?:\b(?:visa|citizen(?:ship)?|nationality|sponsor(?:ship)?|"
    r"work\s+permit|right\s+to\s+work|work\s+authori[sz]ation|"
    r"salary|compensation|wage|expected\s+pay|pay\s+range|"
    r"eeo|race|ethnic|gender|sex|sexual|religion|politic|union|"
    r"disabilit|health|medical|veteran|military|criminal|felony|"
    r"background\s+check|privacy|consent|gdpr|agree(?:ment)?|"
    r"attest|certif|signature|passport|social\s+security|"
    r"government\s+id|tax\s+id|birth|date\s+of\s+birth|age|"
    r"bank|start\s+date|notice\s+period|"
    r"työlupa|oleskelulupa|kansalaisuus|palkka|henkilötunnus|"
    r"sukupuoli|uskonto|rikosrekisteri|suostumus|allekirjoitus|"
    r"arbetstillstånd|medborgarskap|personnummer|samtycke|"
    r"underskrift|lön|födelsetid|kön)\b|"
    r"(?:visa|sponsor|salary|compensat|wage|workauth|workpermit|"
    r"citizen|nationality|gender|sex|race|ethnic|religion|"
    r"disabil|veteran|passport|birth|consent|privacy|legal|"
    r"attest|signature|criminal|backgroundcheck|immigrat|"
    r"taxid|nationalid|henkilötunnus|kansalaisuu|oleskelulup|"
    r"työlup|palkka|samtycke))",
    re.IGNORECASE,
)
JOB_SPECIFIC = re.compile(
    r"\b(?:why\s+(?:do\s+you\s+)?want\s+to\s+work|"
    r"why\s+(?:this|our)\s+(?:company|job|role)|"
    r"(?:our|this)\s+(?:company|organisation|organization|team|role|position)|"
    r"letter\s+of\s+motivation|cover\s+letter|"
    r"miksi\s+(?:meille|tähän\s+tehtävään))\b",
    re.IGNORECASE,
)
EMAIL_OR_URL = re.compile(r"https?://|\b\S+@\S+\.\S+", re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
QUESTION_KEY_PREFIX = "smartploy.safe_question.v1"


class QuestionMemoryError(ValueError):
    pass


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def safe_question(label: str, identifiers: tuple[str, ...] = ()) -> tuple[str, str]:
    if not isinstance(label, str):
        raise QuestionMemoryError("Invalid employer question")
    clean = " ".join(unicodedata.normalize("NFKC", label).split())
    if (not 3 <= len(clean) <= 150 or CONTROL.search(label)
            or EMAIL_OR_URL.search(label) or SENSITIVE.search(clean)
            or any(SENSITIVE.search(identifier) for identifier in identifiers)):
        raise QuestionMemoryError("A sensitive or invalid question remains manual")
    key = sha256((QUESTION_KEY_PREFIX + "\x00" + _fold(clean)).encode("utf-8")).hexdigest()
    return key, clean


def scope_for_question(label: str) -> str:
    return "manual_only" if JOB_SPECIFIC.search(label) else "exact_question"


def validate_answer(answer: str) -> str:
    if not isinstance(answer, str) or CONTROL.search(answer):
        raise QuestionMemoryError("Invalid reviewed answer")
    cleaned = answer.strip()
    if not 2 <= len(cleaned) <= MAX_ANSWER:
        raise QuestionMemoryError("Reviewed answer must contain 2-1500 characters")
    return cleaned


@dataclass(frozen=True)
class RememberedQuestion:
    question_key: str
    label: str
    answer: str = ""
    approved_for_reuse: bool = False
    reusable_scope: str = "exact_question"
    version: int = 1
    first_seen_at: str = ""
    updated_at: str = ""

    def public(self) -> dict[str, object]:
        return {
            "question_key": self.question_key, "label": self.label,
            "answer": self.answer, "approved_for_reuse": self.approved_for_reuse,
            "reusable_scope": self.reusable_scope, "version": self.version,
            "first_seen_at": self.first_seen_at, "updated_at": self.updated_at,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryApplicationQuestionRepository:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], RememberedQuestion] = {}
        self.modes: dict[str, str] = {}

    def mode(self, profile_id: str) -> str:
        return self.modes.get(profile_id, "guided")

    def set_mode(self, profile_id: str, mode: str) -> str:
        if mode not in {"guided", "cv_only"}:
            raise QuestionMemoryError("Invalid application profile mode")
        self.modes[profile_id] = mode
        return mode

    def list(self, profile_id: str) -> list[RememberedQuestion]:
        return sorted(
            (item for (owner, _), item in self.data.items() if owner == profile_id),
            key=lambda item: (not item.approved_for_reuse, item.label.casefold()),
        )

    def observe(
        self, profile_id: str, labels: list[str],
        identifiers: list[tuple[str, ...]] | None = None,
    ) -> tuple[list[RememberedQuestion], int]:
        seen: list[RememberedQuestion] = []
        skipped = 0
        keys_in_request: set[str] = set()
        for i, label in enumerate(labels):
            try:
                key, clean = safe_question(
                    label, identifiers[i] if identifiers is not None else (),
                )
            except QuestionMemoryError:
                skipped += 1
                continue
            if key in keys_in_request:
                skipped += 1
                continue
            keys_in_request.add(key)
            existing = self.data.get((profile_id, key))
            if existing is None:
                if len(self.list(profile_id)) >= MAX_PRIVATE_QUESTIONS:
                    skipped += 1
                    continue
                existing = RememberedQuestion(
                    question_key=key, label=clean,
                    reusable_scope=scope_for_question(clean),
                    first_seen_at=_utc_now(), updated_at=_utc_now(),
                )
                self.data[(profile_id, key)] = existing
            seen.append(existing)
        return seen, skipped

    def save(
        self, profile_id: str, key: str, answer: str,
        expected_version: int, approve_for_reuse: bool,
    ) -> RememberedQuestion:
        old = self.data.get((profile_id, key))
        if old is None:
            raise QuestionMemoryError("Question not found in this profile")
        if type(expected_version) is not int or old.version != expected_version:
            raise QuestionMemoryError("Question version changed; reload")
        clean = validate_answer(answer)
        if approve_for_reuse and old.reusable_scope != "exact_question":
            raise QuestionMemoryError("Job-specific answers cannot be reused")
        updated = replace(
            old, answer=clean, version=old.version + 1,
            approved_for_reuse=approve_for_reuse, updated_at=_utc_now(),
        )
        self.data[(profile_id, key)] = updated
        return updated

    def delete(self, profile_id: str, key: str) -> bool:
        return self.data.pop((profile_id, key), None) is not None


class PostgresApplicationQuestionRepository:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN required for question memory")
        self.dsn = dsn

    @staticmethod
    def _from_row(row: tuple) -> RememberedQuestion:
        return RememberedQuestion(
            question_key=str(row[0]), label=str(row[1]), answer=str(row[2]),
            approved_for_reuse=bool(row[3]), reusable_scope=str(row[4]),
            version=int(row[5]),
            first_seen_at=row[6].isoformat(), updated_at=row[7].isoformat(),
        )

    _COLUMNS = (
        "question_key,label,answer,approved_for_reuse,"
        "reusable_scope,version,first_seen_at,updated_at"
    )

    def mode(self, profile_id: str) -> str:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT mode FROM smartploy_application_profile_settings "
                    "WHERE profile_id=%s", (profile_id,),
                )
                row = cur.fetchone()
        return str(row[0]) if row else "guided"

    def set_mode(self, profile_id: str, mode: str) -> str:
        if mode not in {"guided", "cv_only"}:
            raise QuestionMemoryError("Invalid application profile mode")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO smartploy_application_profile_settings
                       (profile_id,mode) VALUES (%s,%s)
                       ON CONFLICT(profile_id) DO UPDATE
                         SET mode=EXCLUDED.mode,updated_at=now()""",
                    (profile_id, mode),
                )
        return mode

    def list(self, profile_id: str) -> list[RememberedQuestion]:
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {self._COLUMNS} FROM smartploy_application_profile_questions "
                    "WHERE profile_id=%s ORDER BY approved_for_reuse DESC, label",
                    (profile_id,),
                )
                return [self._from_row(row) for row in cur.fetchall()]

    def observe(
        self, profile_id: str, labels: list[str],
        identifiers: list[tuple[str, ...]] | None = None,
    ) -> tuple[list[RememberedQuestion], int]:
        seen: list[RememberedQuestion] = []
        skipped = 0
        unique: set[str] = set()
        # One connection & transaction for all prompts. No raw employer URLs,
        # cookies, CV or employer PII are written into this table.
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for i, label in enumerate(labels):
                    try:
                        key, clean = safe_question(
                            label, identifiers[i] if identifiers is not None else (),
                        )
                    except QuestionMemoryError:
                        skipped += 1
                        continue
                    if key in unique:
                        skipped += 1
                        continue
                    unique.add(key)
                    # UPDATE only the read timestamp; NEVER silently change
                    # an existing answer/approval. Race-safe bound on profile.
                    cur.execute(
                        f"""INSERT INTO smartploy_application_profile_questions
                          (profile_id,question_key,label,reusable_scope)
                          SELECT %s,%s,%s,%s
                          WHERE (SELECT count(*) FROM smartploy_application_profile_questions
                                 WHERE profile_id=%s) < %s
                            OR EXISTS(SELECT 1 FROM smartploy_application_profile_questions
                                      WHERE profile_id=%s AND question_key=%s)
                          ON CONFLICT(profile_id,question_key) DO UPDATE
                          SET last_seen_at=now()
                          RETURNING {self._COLUMNS}""",
                        (profile_id, key, clean, scope_for_question(clean),
                         profile_id, MAX_PRIVATE_QUESTIONS, profile_id, key),
                    )
                    row = cur.fetchone()
                    if row is None:
                        skipped += 1
                    else:
                        seen.append(self._from_row(row))
        return seen, skipped

    def save(
        self, profile_id: str, key: str, answer: str,
        expected_version: int, approve_for_reuse: bool,
    ) -> RememberedQuestion:
        if not isinstance(key, str) or not HEX64.fullmatch(key):
            raise QuestionMemoryError("Invalid question identity")
        if type(expected_version) is not int or expected_version < 1:
            raise QuestionMemoryError("Invalid question version")
        clean = validate_answer(answer)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE smartploy_application_profile_questions SET
                          answer=%s, approved_for_reuse=%s,
                          version=version+1, updated_at=now()
                        WHERE profile_id=%s AND question_key=%s AND version=%s
                          AND (NOT %s OR reusable_scope='exact_question')
                        RETURNING {self._COLUMNS}""",
                    (clean, approve_for_reuse, profile_id, key,
                     expected_version, approve_for_reuse),
                )
                row = cur.fetchone()
                if row is None:
                    raise QuestionMemoryError(
                        "Question changed, is job-specific or was removed. Reload."
                    )
        return self._from_row(row)

    def delete(self, profile_id: str, key: str) -> bool:
        if not isinstance(key, str) or not HEX64.fullmatch(key):
            raise QuestionMemoryError("Invalid question identity")
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM smartploy_application_profile_questions "
                    "WHERE profile_id=%s AND question_key=%s",
                    (profile_id, key),
                )
                return cur.rowcount > 0

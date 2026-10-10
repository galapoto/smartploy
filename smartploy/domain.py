"""Smartploy-owned deterministic job intelligence domain.

Smartploy owns source policy, source evidence, canonical job records,
deduplication, freshness, filters and application handoff metadata.

No code in this module imports ObumAI. ObumAI is an external reasoning/execution
provider reached only through the integration client in smartploy.obumai.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import hashlib
import json
import re


SAFE_SOURCE_MODES = {"api", "feed", "search", "browser", "manual"}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
}
TRACKING_QUERY_PREFIXES = ("utm_",)
SENIOR_TERMS = ("senior", "lead", "principal", "staff", "head", "director", "manager")
JUNIOR_TERMS = ("junior", "trainee", "graduate", "entry", "assistant", "associate")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())


def normalize_identity_text(value: str) -> str:
    lowered = normalize_space(value).casefold()
    return re.sub(r"[^a-z0-9åäö]+", " ", lowered).strip()


def normalize_work_mode(value: str) -> str:
    text = normalize_identity_text(value)
    if text in {"remote", "fully remote", "remote first", "eta", "etatyo"}:
        return "remote"
    if text in {"hybrid", "partly remote", "remote hybrid", "hybridi"}:
        return "hybrid"
    if text in {"onsite", "on site", "office", "in office", "toimisto"}:
        return "onsite"
    return "review"


def normalize_employer_sector(value: str) -> str:
    text = normalize_identity_text(value)
    if text in {"public", "public sector", "julkinen", "julkinen sektori"}:
        return "public"
    if text in {"private", "private sector", "yksityinen", "yksityinen sektori"}:
        return "private"
    return "unknown"


def canonicalize_url(value: str) -> str:
    """Return stable URL identity while stripping common tracking aliases."""

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return ""

    scheme = parts.scheme.casefold()
    host = parts.hostname.casefold() if parts.hostname else ""
    if not host:
        return ""
    try:
        port = parts.port
    except ValueError:
        return ""

    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    kept: List[Tuple[str, str]] = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        folded = key.casefold()
        if folded in TRACKING_QUERY_KEYS or any(folded.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        kept.append((key, item))
    kept.sort(key=lambda row: (row[0].casefold(), row[1]))
    return urlunsplit((scheme, netloc, path, urlencode(kept, doseq=True), ""))


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip(" -\t") for item in re.split(r"[\n;•]+", value) if item.strip(" -\t")]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def stable_job_id(company: str, role_title: str) -> str:
    material = canonical_json(
        {
            "company": normalize_identity_text(company),
            "role_title": normalize_identity_text(role_title),
        }
    )
    return f"job-{sha256_text(material)[:20]}"


@dataclass(frozen=True)
class JobRecord:
    company: str
    role_title: str
    description: str = ""
    location: str = ""
    work_mode: str = "review"
    deadline: str = ""
    language: str = ""
    requirements: Tuple[str, ...] = ()
    nice_to_have: Tuple[str, ...] = ()
    application_url: str = ""
    required_documents: Tuple[str, ...] = ()
    questions: Tuple[str, ...] = ()
    source: str = ""
    job_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    raw: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "JobRecord":
        company = normalize_space(self.company)
        role_title = normalize_space(self.role_title)
        if not company:
            raise ValueError("company is required")
        if not role_title:
            raise ValueError("role_title is required")
        return JobRecord(
            company=company,
            role_title=role_title,
            description=str(self.description or "").strip(),
            location=normalize_space(self.location),
            work_mode=normalize_work_mode(self.work_mode),
            deadline=str(self.deadline or "").strip(),
            language=normalize_space(self.language),
            requirements=tuple(_listify(self.requirements)),
            nice_to_have=tuple(_listify(self.nice_to_have)),
            application_url=canonicalize_url(self.application_url),
            required_documents=tuple(_listify(self.required_documents)),
            questions=tuple(_listify(self.questions)),
            source=str(self.source or "").strip(),
            job_id=str(self.job_id or "").strip() or stable_job_id(company, role_title),
            created_at=str(self.created_at or utc_now_iso()).strip(),
            raw=dict(self.raw or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self.normalized())
        value["requirements"] = list(value["requirements"])
        value["nice_to_have"] = list(value["nice_to_have"])
        value["required_documents"] = list(value["required_documents"])
        value["questions"] = list(value["questions"])
        return value


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    display_name: str
    source_class: str
    allowed_modes: Tuple[str, ...]
    terms_review_status: str = "approved"
    active: bool = True
    notes: str = ""

    def normalized(self) -> "SourcePolicy":
        source_id = normalize_identity_text(self.source_id).replace(" ", "-")
        if not source_id:
            raise ValueError("source_id is required")
        modes = tuple(sorted({str(item).strip().casefold() for item in self.allowed_modes if str(item).strip()}))
        if not modes or any(item not in SAFE_SOURCE_MODES for item in modes):
            raise ValueError("allowed_modes contains an unsupported acquisition mode")
        status = str(self.terms_review_status or "").strip().casefold()
        if status not in {"approved", "review", "blocked"}:
            raise ValueError("terms_review_status must be approved, review or blocked")
        return SourcePolicy(
            source_id=source_id,
            display_name=normalize_space(self.display_name) or source_id,
            source_class=normalize_identity_text(self.source_class).replace(" ", "_") or "unknown",
            allowed_modes=modes,
            terms_review_status=status,
            active=bool(self.active),
            notes=str(self.notes or "").strip(),
        )

    def allows(self, mode: str) -> bool:
        value = str(mode or "").strip().casefold()
        item = self.normalized()
        return item.active and item.terms_review_status == "approved" and value in item.allowed_modes


@dataclass(frozen=True)
class SourceObservation:
    source_id: str
    source_mode: str
    source_url: str
    raw_text: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=utc_now_iso)
    posted_at: str = ""
    source_external_id: str = ""

    def normalized(self) -> "SourceObservation":
        source_id = normalize_identity_text(self.source_id).replace(" ", "-")
        mode = str(self.source_mode or "").strip().casefold()
        if not source_id:
            raise ValueError("source_id is required")
        if mode not in SAFE_SOURCE_MODES:
            raise ValueError("unsupported source_mode")

        source_url = canonicalize_url(self.source_url)
        if mode != "manual" and not source_url:
            raise ValueError("canonical source_url is required for non-manual observations")
        raw_text = str(self.raw_text or "")
        if not raw_text.strip() and not self.payload:
            raise ValueError("raw source content is required")

        return SourceObservation(
            source_id=source_id,
            source_mode=mode,
            source_url=source_url,
            raw_text=raw_text,
            payload=dict(self.payload or {}),
            observed_at=str(self.observed_at or utc_now_iso()).strip(),
            posted_at=str(self.posted_at or "").strip(),
            source_external_id=str(self.source_external_id or "").strip(),
        )

    @property
    def raw_sha256(self) -> str:
        item = self.normalized()
        return sha256_text(canonical_json({"raw_text": item.raw_text, "payload": item.payload}))

    @property
    def observation_id(self) -> str:
        item = self.normalized()
        material = {
            "source_id": item.source_id,
            "source_mode": item.source_mode,
            "source_url": item.source_url,
            "source_external_id": item.source_external_id,
            "raw_sha256": item.raw_sha256,
            "observed_at": item.observed_at,
        }
        return f"jobobs-{sha256_text(canonical_json(material))[:20]}"


@dataclass(frozen=True)
class JobSearchFilters:
    sectors: Tuple[str, ...] = ()
    languages: Tuple[str, ...] = ()
    locations: Tuple[str, ...] = ()
    work_modes: Tuple[str, ...] = ()
    seniority: Tuple[str, ...] = ()
    minimum_salary_eur: Optional[int] = None
    excluded_employers: Tuple[str, ...] = ()
    excluded_terms: Tuple[str, ...] = ()
    include_unknown: bool = True

    def normalized(self) -> "JobSearchFilters":
        def norm_many(values: Sequence[str]) -> Tuple[str, ...]:
            return tuple(sorted({normalize_identity_text(item) for item in values if normalize_identity_text(item)}))

        modes = tuple(sorted({normalize_work_mode(item) for item in self.work_modes if str(item).strip()}))
        modes = tuple(item for item in modes if item != "review")
        salary = None if self.minimum_salary_eur is None else int(self.minimum_salary_eur)
        if salary is not None and salary < 0:
            raise ValueError("minimum_salary_eur cannot be negative")
        return JobSearchFilters(
            sectors=norm_many(self.sectors),
            languages=norm_many(self.languages),
            locations=norm_many(self.locations),
            work_modes=modes,
            seniority=norm_many(self.seniority),
            minimum_salary_eur=salary,
            excluded_employers=norm_many(self.excluded_employers),
            excluded_terms=norm_many(self.excluded_terms),
            include_unknown=bool(self.include_unknown),
        )


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    status: str
    reasons: Tuple[str, ...] = ()
    review_fields: Tuple[str, ...] = ()


@dataclass(frozen=True)
class JobCandidate:
    job: JobRecord
    canonical_url: str
    canonical_key: str
    description_fingerprint: str
    source_ids: Tuple[str, ...]
    source_observation_ids: Tuple[str, ...]
    source_raw_sha256: Tuple[str, ...]
    first_seen_at: str
    last_seen_at: str
    posted_at: str = ""
    last_verified_at: str = ""
    closed_at: str = ""
    source_current: bool = True
    duplicate_count: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["job"] = self.job.to_dict()
        value["source_ids"] = list(self.source_ids)
        value["source_observation_ids"] = list(self.source_observation_ids)
        value["source_raw_sha256"] = list(self.source_raw_sha256)
        return value

    def to_obumai_handoff(self) -> Dict[str, Any]:
        forwarding_allowed = self.job.raw.get("external_ai_forwarding_allowed") is not False
        reasoning_allowed = self.source_current and forwarding_allowed
        return {
            "contract": "smartploy.obumai.handoff.v1",
            "status": (
                "ready_for_reasoning"
                if reasoning_allowed
                else "blocked_source_forwarding_restricted"
                if self.source_current
                else "blocked_source_not_current"
            ),
            "job": self.job.to_dict(),
            "source_evidence": {
                "canonical_url": self.canonical_url,
                "canonical_key": self.canonical_key,
                "description_fingerprint": self.description_fingerprint,
                "source_ids": list(self.source_ids),
                "source_observation_ids": list(self.source_observation_ids),
                "source_raw_sha256": list(self.source_raw_sha256),
                "first_seen_at": self.first_seen_at,
                "last_seen_at": self.last_seen_at,
                "posted_at": self.posted_at,
                "last_verified_at": self.last_verified_at,
                "source_current": self.source_current,
                "closed_at": self.closed_at,
            },
            "authority": {
                "may_reason": reasoning_allowed,
                "may_prepare_drafts": reasoning_allowed,
                "source_forwarding_restricted": not forwarding_allowed,
                "may_upload": False,
                "may_submit": False,
                "external_action_authorized": False,
            },
        }


@dataclass(frozen=True)
class DiscoveryResult:
    status: str
    reasons: Tuple[str, ...] = ()
    candidate: Optional[JobCandidate] = None
    filter_decision: Optional[FilterDecision] = None

    @property
    def discovered(self) -> bool:
        return self.status == "discovered" and self.candidate is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "filter_decision": asdict(self.filter_decision) if self.filter_decision else None,
        }


def _payload_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _payload_list(payload: Mapping[str, Any], *keys: str) -> Tuple[str, ...]:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return tuple(_listify(value))
    return ()


def description_fingerprint(value: str) -> str:
    normalized = normalize_identity_text(value)
    tokens = [item for item in normalized.split() if len(item) > 2]
    return sha256_text(" ".join(sorted(set(tokens))[:512]))


def infer_seniority(title: str, description: str = "") -> str:
    text = normalize_identity_text(f"{title} {description}")
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in SENIOR_TERMS):
        return "senior"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in JUNIOR_TERMS):
        return "junior"
    return "unspecified"


def canonical_duplicate_key(job: JobRecord) -> str:
    item = job.normalized()
    material = {
        "company": normalize_identity_text(item.company),
        "role_title": normalize_identity_text(item.role_title),
        "location": normalize_identity_text(item.location),
        "description_fingerprint": description_fingerprint(item.description),
    }
    return f"jobkey-{sha256_text(canonical_json(material))[:24]}"


def normalize_observation(observation: SourceObservation, policy: SourcePolicy) -> DiscoveryResult:
    try:
        obs = observation.normalized()
        source_policy = policy.normalized()
    except (TypeError, ValueError) as exc:
        return DiscoveryResult(status="blocked", reasons=(f"invalid_source_observation:{exc}",))

    if obs.source_id != source_policy.source_id:
        return DiscoveryResult(status="blocked", reasons=("source_policy_identity_mismatch",))
    if not source_policy.allows(obs.source_mode):
        return DiscoveryResult(status="blocked", reasons=("source_mode_not_approved",))

    payload = dict(obs.payload)
    company = _payload_text(payload, "company", "employer", "organization")
    title = _payload_text(payload, "role_title", "title", "role")
    description = _payload_text(payload, "description", "job_description") or obs.raw_text
    if not company or not title:
        return DiscoveryResult(status="blocked", reasons=("canonical_job_identity_incomplete",))

    application_url = canonicalize_url(
        _payload_text(payload, "application_url", "apply_url", "url") or obs.source_url
    )
    external_ai_forwarding_allowed = payload.get("external_ai_forwarding_allowed", True)
    if not isinstance(external_ai_forwarding_allowed, bool):
        external_ai_forwarding_allowed = True
    source_details = payload.get("source_details")
    if not isinstance(source_details, dict):
        source_details = {}
    job = JobRecord(
        company=company,
        role_title=title,
        description=description,
        location=_payload_text(payload, "location"),
        work_mode=_payload_text(payload, "work_mode", "mode") or "review",
        deadline=_payload_text(payload, "deadline", "application_deadline"),
        language=_payload_text(payload, "language", "languages"),
        requirements=_payload_list(payload, "requirements", "must_have"),
        nice_to_have=_payload_list(payload, "nice_to_have", "preferred"),
        application_url=application_url,
        required_documents=_payload_list(payload, "required_documents", "documents"),
        questions=_payload_list(payload, "questions", "application_questions"),
        source=source_policy.source_id,
        created_at=obs.observed_at,
        raw={
            "untrusted_source": True,
            "source_class": source_policy.source_class,
            "source_mode": obs.source_mode,
            "source_url": obs.source_url,
            "source_external_id": obs.source_external_id,
            "raw_sha256": obs.raw_sha256,
            "observation_id": obs.observation_id,
            "sector": _payload_text(payload, "sector", "industry"),
            "employer_sector": normalize_employer_sector(
                _payload_text(payload, "employer_sector", "ownership_sector")
            ),
            "source_attribution": _payload_text(payload, "source_attribution"),
            "external_ai_forwarding_allowed": external_ai_forwarding_allowed,
            "source_details": dict(source_details),
            "seniority": _payload_text(payload, "seniority") or infer_seniority(title, description),
            "salary_min_eur": payload.get("salary_min_eur"),
            "salary_max_eur": payload.get("salary_max_eur"),
        },
    ).normalized()

    candidate = JobCandidate(
        job=job,
        canonical_url=canonicalize_url(job.application_url or obs.source_url),
        canonical_key=canonical_duplicate_key(job),
        description_fingerprint=description_fingerprint(job.description),
        source_ids=(source_policy.source_id,),
        source_observation_ids=(obs.observation_id,),
        source_raw_sha256=(obs.raw_sha256,),
        first_seen_at=obs.observed_at,
        last_seen_at=obs.observed_at,
        posted_at=obs.posted_at,
        last_verified_at=obs.observed_at,
        source_current=True,
        metadata={
            "source_class": source_policy.source_class,
            "source_mode": obs.source_mode,
            "terms_review_status": source_policy.terms_review_status,
            "untrusted_source": True,
        },
    )
    return DiscoveryResult(status="discovered", candidate=candidate)


def _candidate_value(candidate: JobCandidate, key: str) -> str:
    return normalize_identity_text(str(candidate.job.raw.get(key) or ""))


def _candidate_salary_min(candidate: JobCandidate) -> Optional[int]:
    value = candidate.job.raw.get("salary_min_eur")
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def apply_filters(candidate: JobCandidate, filters: JobSearchFilters) -> FilterDecision:
    cfg = filters.normalized()
    reasons: List[str] = []
    review: List[str] = []

    company = normalize_identity_text(candidate.job.company)
    combined = normalize_identity_text(f"{candidate.job.role_title} {candidate.job.description}")
    language = normalize_identity_text(candidate.job.language)
    location = normalize_identity_text(candidate.job.location)
    sector = _candidate_value(candidate, "sector")
    seniority = _candidate_value(candidate, "seniority") or infer_seniority(
        candidate.job.role_title, candidate.job.description
    )
    work_mode = normalize_work_mode(candidate.job.work_mode)
    salary_min = _candidate_salary_min(candidate)

    if company in cfg.excluded_employers:
        reasons.append("excluded_employer")
    if any(term and term in combined for term in cfg.excluded_terms):
        reasons.append("excluded_term")

    def require_any(name: str, actual: str, accepted: Tuple[str, ...]) -> None:
        if not accepted:
            return
        if not actual:
            if cfg.include_unknown:
                review.append(name)
            else:
                reasons.append(f"{name}_unknown")
            return
        if not any(item == actual or item in actual for item in accepted):
            reasons.append(f"{name}_mismatch")

    require_any("sector", sector, cfg.sectors)
    require_any("language", language, cfg.languages)
    require_any("location", location, cfg.locations)
    require_any("seniority", seniority, cfg.seniority)

    if cfg.work_modes:
        if work_mode == "review":
            if cfg.include_unknown:
                review.append("work_mode")
            else:
                reasons.append("work_mode_unknown")
        elif work_mode not in cfg.work_modes:
            reasons.append("work_mode_mismatch")

    if cfg.minimum_salary_eur is not None:
        if salary_min is None:
            if cfg.include_unknown:
                review.append("salary")
            else:
                reasons.append("salary_unknown")
        elif salary_min < cfg.minimum_salary_eur:
            reasons.append("salary_below_minimum")

    accepted = not reasons
    return FilterDecision(
        accepted=accepted,
        status="accepted_with_review" if accepted and review else "accepted" if accepted else "filtered",
        reasons=tuple(sorted(set(reasons))),
        review_fields=tuple(sorted(set(review))),
    )


def _earliest(left: str, right: str) -> str:
    values = [item for item in (left, right) if item]
    return min(values) if values else ""


def _latest(left: str, right: str) -> str:
    values = [item for item in (left, right) if item]
    return max(values) if values else ""


def merge_candidates(existing: JobCandidate, incoming: JobCandidate) -> JobCandidate:
    if existing.canonical_key != incoming.canonical_key:
        raise ValueError("cannot merge candidates with different canonical keys")

    source_ids = tuple(sorted(set(existing.source_ids + incoming.source_ids)))
    observation_ids = tuple(sorted(set(existing.source_observation_ids + incoming.source_observation_ids)))
    raw_hashes = tuple(sorted(set(existing.source_raw_sha256 + incoming.source_raw_sha256)))

    existing_weight = len(existing.job.description) + len(existing.job.requirements) * 80
    incoming_weight = len(incoming.job.description) + len(incoming.job.requirements) * 80
    chosen = incoming.job if incoming_weight > existing_weight else existing.job
    chosen = replace(
        chosen,
        job_id=existing.job.job_id,
        created_at=existing.job.created_at,
        source=",".join(source_ids),
    )

    return JobCandidate(
        job=chosen,
        canonical_url=incoming.canonical_url or existing.canonical_url,
        canonical_key=existing.canonical_key,
        description_fingerprint=incoming.description_fingerprint or existing.description_fingerprint,
        source_ids=source_ids,
        source_observation_ids=observation_ids,
        source_raw_sha256=raw_hashes,
        first_seen_at=_earliest(existing.first_seen_at, incoming.first_seen_at),
        last_seen_at=_latest(existing.last_seen_at, incoming.last_seen_at),
        posted_at=_earliest(existing.posted_at, incoming.posted_at),
        last_verified_at=_latest(existing.last_verified_at, incoming.last_verified_at),
        closed_at=incoming.closed_at or existing.closed_at,
        source_current=existing.source_current or incoming.source_current,
        duplicate_count=max(existing.duplicate_count, 1) + 1,
        metadata={**dict(existing.metadata), **dict(incoming.metadata)},
    )


class JobDiscoveryIndex:
    """Deterministic in-memory domain repository for the bootstrap slice.

    Durable PostgreSQL storage is the next persistence slice; callers depend on
    this interface rather than on ObumAI storage.
    """

    def __init__(self) -> None:
        self._items: Dict[str, JobCandidate] = {}

    def ingest(
        self,
        observation: SourceObservation,
        policy: SourcePolicy,
        filters: Optional[JobSearchFilters] = None,
    ) -> DiscoveryResult:
        result = normalize_observation(observation, policy)
        if not result.discovered or result.candidate is None:
            return result

        candidate = result.candidate
        decision = apply_filters(candidate, filters or JobSearchFilters())
        if not decision.accepted:
            return DiscoveryResult(
                status="filtered",
                reasons=decision.reasons,
                candidate=candidate,
                filter_decision=decision,
            )

        existing = self._items.get(candidate.canonical_key)
        if existing is not None:
            candidate = merge_candidates(existing, candidate)
        self._items[candidate.canonical_key] = candidate
        return DiscoveryResult(status="discovered", candidate=candidate, filter_decision=decision)

    def mark_closed(self, canonical_key: str, *, closed_at: Optional[str] = None) -> JobCandidate:
        current = self._items[canonical_key]
        timestamp = closed_at or utc_now_iso()
        updated = replace(
            current,
            source_current=False,
            closed_at=timestamp,
            last_verified_at=timestamp,
        )
        self._items[canonical_key] = updated
        return updated

    def get(self, canonical_key: str) -> Optional[JobCandidate]:
        return self._items.get(canonical_key)

    def values(self) -> List[JobCandidate]:
        return sorted(
            self._items.values(),
            key=lambda item: (item.last_seen_at, item.canonical_key),
            reverse=True,
        )

"""Credential-gated Job Market Finland P67 retrieval adapter.

The adapter implements KEHA Centre's official Jobposting Search API v2 contract.
It never logs or persists the KIPA subscription key. Retrieved posting content is
marked external-AI-forwarding restricted because the published terms prohibit
forwarding retrieval-interface job postings to third parties without separate
permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit
import json
import os

import httpx

from ..domain import SourceObservation, SourcePolicy, canonicalize_url, utc_now_iso


SOURCE_ID = "job-market-finland"
PARSER_VERSION = "job-market-finland-p67-v2"
ORIGINAL_SOURCE_LABEL = "Job Market Finland's customer information system"
TEST_ENDPOINT = "https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings"
PRODUCTION_ENDPOINT = "https://api.ahtp.fi/kipa/p67/v2/jobpostings"
ALLOWED_ENDPOINTS = {
    "test": TEST_ENDPOINT,
    "production": PRODUCTION_ENDPOINT,
}
PROTECTED_HEADERS = {"kipa-subscription-key", "content-type", "accept"}
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_ITEMS = 10000
SUPPORTED_LANGUAGES = {"fi", "sv", "en"}
SUPPORTED_STATUSES = {"PUBLISHED", "ARCHIVED"}


class JobMarketFinlandAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchivedPosting:
    external_id: str
    archived_at: str = ""
    last_modified: str = ""


@dataclass(frozen=True)
class JobMarketFinlandBatch:
    status: str
    observations: tuple[SourceObservation, ...] = ()
    archived: tuple[ArchivedPosting, ...] = ()

    @property
    def item_count(self) -> int:
        return len(self.observations) + len(self.archived)


def _truthy(value: str) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def validate_endpoint(endpoint: str, environment: str) -> str:
    value = str(endpoint or "").strip()
    expected = ALLOWED_ENDPOINTS.get(environment)
    if expected is None:
        raise JobMarketFinlandAPIError("environment must be test or production")
    if value != expected:
        raise JobMarketFinlandAPIError("P67 endpoint must match the official environment endpoint")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise JobMarketFinlandAPIError("invalid P67 endpoint") from exc
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise JobMarketFinlandAPIError("P67 endpoint must use a credential-free HTTPS URL")
    try:
        ip_address(parts.hostname)
    except ValueError:
        pass
    else:
        raise JobMarketFinlandAPIError("IP-literal P67 endpoints are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise JobMarketFinlandAPIError("invalid P67 endpoint port") from exc
    if port not in (None, 443):
        raise JobMarketFinlandAPIError("non-standard P67 endpoint ports are not allowed")
    if parts.path != "/kipa/p67/v2/jobpostings" or parts.query or parts.fragment:
        raise JobMarketFinlandAPIError("unexpected P67 endpoint path/query")
    return value


def _localized(value: Any, preference: tuple[str, ...] = ("fi", "en", "sv")) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in preference:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return [str(value)]
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            localized = _localized(item)
            if localized:
                result.append(localized)
                continue
            for key in ("code", "id", "value", "tunnus"):
                raw = item.get(key)
                if raw not in (None, ""):
                    result.append(str(raw))
                    break
        elif item not in (None, ""):
            result.append(str(item))
    return result


def _record_sections(record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    names = ("metadata", "client", "position", "owner", "location", "application")
    return tuple(item if isinstance((item := record.get(name)), dict) else {} for name in names)


def _published_observation(
    record: dict[str, Any],
    *,
    endpoint: str,
    observed_at: str,
    locale_preference: tuple[str, ...],
) -> SourceObservation:
    metadata, client, position, owner, location, application = _record_sections(record)

    external_id = str(metadata.get("externalId") or "").strip()
    if not external_id:
        raise JobMarketFinlandAPIError("P67 published item is missing metadata.externalId")

    company = _localized(client.get("company"), locale_preference) or _localized(
        owner.get("company"), locale_preference
    )
    title = _localized(position.get("title"), locale_preference)
    if not company or not title:
        raise JobMarketFinlandAPIError("P67 published item is missing employer/title identity")

    description = _localized(position.get("jobDescription"), locale_preference)
    if not description:
        description = _localized(position.get("marketingDescription"), locale_preference)

    application_url = _localized(application.get("url"), locale_preference)
    canonical_application_url = canonicalize_url(application_url)
    source_url = canonical_application_url or endpoint

    workplace_name = _localized(location.get("workplaceName"), locale_preference)
    workplace_post_office = str(location.get("workplacePostOffice") or "").strip()
    workplace_address = str(location.get("workplaceAddress") or "").strip()
    display_location = workplace_post_office or workplace_name or workplace_address

    work_languages = _string_list(position.get("workLanguages"))
    occupations = _string_list(position.get("occupations"))
    skills = _string_list(position.get("skills"))

    published = str(application.get("published") or "").strip()
    expires = str(application.get("expires") or "").strip()
    last_modified = str(metadata.get("lastModified") or "").strip()
    created = str(metadata.get("created") or "").strip()

    payload = {
        "company": company,
        "role_title": title,
        "description": description,
        "location": display_location,
        "work_mode": "review",
        "deadline": expires,
        "language": ", ".join(work_languages),
        "application_url": canonical_application_url,
        "employer_sector": "unknown",
        "source_attribution": ORIGINAL_SOURCE_LABEL,
        "external_ai_forwarding_allowed": False,
        "source_details": {
            "external_id": external_id,
            "created": created,
            "last_modified": last_modified,
            "published": published,
            "expires": expires,
            "employer_type": owner.get("employerType"),
            "business_id": client.get("businessId") or owner.get("businessId"),
            "industry_code": client.get("industryCode") or owner.get("industryCode"),
            "work_time": position.get("workTime"),
            "work_languages": work_languages,
            "occupations": occupations,
            "skills": skills,
            "municipalities": _string_list(location.get("municipalities")),
            "regions": _string_list(location.get("regions")),
            "countries": _string_list(location.get("countries")),
        },
    }

    return SourceObservation(
        source_id=SOURCE_ID,
        source_mode="api",
        source_url=source_url,
        raw_text=" ".join(part for part in (title, company, description) if part),
        payload=payload,
        observed_at=observed_at,
        posted_at=published,
        source_external_id=external_id,
    )


def parse_ndjson(
    content: bytes,
    *,
    status: str,
    endpoint: str,
    observed_at: str | None = None,
    locale_preference: tuple[str, ...] = ("fi", "en", "sv"),
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> JobMarketFinlandBatch:
    mode = str(status or "").strip().upper()
    if mode not in SUPPORTED_STATUSES:
        raise JobMarketFinlandAPIError("unsupported P67 posting status")
    if len(content) > max_bytes:
        raise JobMarketFinlandAPIError("P67 response exceeds configured size limit")

    timestamp = observed_at or utc_now_iso()
    observations: list[SourceObservation] = []
    archived: list[ArchivedPosting] = []
    item_count = 0

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        item_count += 1
        if item_count > max_items:
            raise JobMarketFinlandAPIError("P67 response exceeds configured item limit")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JobMarketFinlandAPIError(f"invalid P67 NDJSON at line {line_number}") from exc
        if not isinstance(record, dict):
            raise JobMarketFinlandAPIError(f"P67 NDJSON line {line_number} is not an object")

        if mode == "PUBLISHED":
            observations.append(
                _published_observation(
                    record,
                    endpoint=endpoint,
                    observed_at=timestamp,
                    locale_preference=locale_preference,
                )
            )
            continue

        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        external_id = str(metadata.get("externalId") or "").strip()
        if not external_id:
            raise JobMarketFinlandAPIError("P67 archived item is missing metadata.externalId")
        archived.append(
            ArchivedPosting(
                external_id=external_id,
                archived_at=str(metadata.get("archived") or "").strip(),
                last_modified=str(metadata.get("lastModified") or "").strip(),
            )
        )

    return JobMarketFinlandBatch(
        status=mode,
        observations=tuple(observations),
        archived=tuple(archived),
    )


def compute_modified_window(
    *,
    last_success_at: str = "",
    now: datetime | None = None,
    initial_lookback_minutes: int = 120,
    overlap_minutes: int = 5,
) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc).replace(microsecond=0)

    start: datetime
    if last_success_at:
        try:
            parsed = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            start = parsed.astimezone(timezone.utc) - timedelta(minutes=max(0, overlap_minutes))
        except ValueError:
            start = current - timedelta(minutes=max(1, initial_lookback_minutes))
    else:
        start = current - timedelta(minutes=max(1, initial_lookback_minutes))

    if start > current:
        start = current - timedelta(minutes=max(1, initial_lookback_minutes))

    def iso(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    return iso(start), iso(current)


@dataclass(frozen=True)
class JobMarketFinlandSettings:
    environment: str
    endpoint: str
    subscription_key: str = field(repr=False)
    extra_headers: dict[str, str] = field(default_factory=dict, repr=False)
    posting_languages: tuple[str, ...] = ("fi", "en", "sv")
    timeout_seconds: float = 20.0
    max_bytes: int = DEFAULT_MAX_BYTES
    max_items: int = DEFAULT_MAX_ITEMS
    initial_lookback_minutes: int = 120
    overlap_minutes: int = 5

    def __post_init__(self) -> None:
        environment = str(self.environment or "").strip().casefold()
        endpoint = validate_endpoint(self.endpoint, environment)
        key = str(self.subscription_key or "").strip()
        if not key:
            raise JobMarketFinlandAPIError("KIPA subscription key is required")

        headers = dict(self.extra_headers or {})
        if any(str(name).casefold() in PROTECTED_HEADERS for name in headers):
            raise JobMarketFinlandAPIError("extra headers cannot override protected P67 headers")

        languages = tuple(dict.fromkeys(str(item).strip().casefold() for item in self.posting_languages))
        if any(item not in SUPPORTED_LANGUAGES for item in languages):
            raise JobMarketFinlandAPIError("posting languages must be fi, sv or en")
        if self.timeout_seconds <= 0 or self.max_bytes <= 0 or self.max_items <= 0:
            raise JobMarketFinlandAPIError("P67 limits must be positive")

        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "subscription_key", key)
        object.__setattr__(self, "extra_headers", headers)
        object.__setattr__(self, "posting_languages", languages)

    @classmethod
    def from_env(cls) -> "JobMarketFinlandSettings | None":
        if not _truthy(os.getenv("JOBMARKET_FINLAND_API_ENABLED", "")):
            return None
        environment = os.getenv("JOBMARKET_FINLAND_ENVIRONMENT", "test").strip().casefold()
        # SP60: a KEHA QA subscription is for isolated testing, not the
        # live SmartPloy job ledger. Reject the test feed at ALL production
        # scheduled/one-shot P67 entry points before any network or DB write.
        # The standalone QA smoke deliberately constructs test settings
        # directly and has no database or scheduler access.
        if (
            environment == "test"
            and os.getenv("SMARTPLOY_ENVIRONMENT", "production").strip().casefold()
            == "production"
        ):
            raise JobMarketFinlandAPIError(
                "KEHA QA credentials cannot be used by a production SmartPloy source"
            )
        endpoint = os.getenv("JOBMARKET_FINLAND_ENDPOINT", "").strip()
        if not endpoint:
            endpoint = ALLOWED_ENDPOINTS.get(environment, "")
        key = os.getenv("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "").strip()
        raw_headers = os.getenv("JOBMARKET_FINLAND_HTTP_HEADERS_JSON", "{}").strip() or "{}"
        try:
            headers = json.loads(raw_headers)
        except json.JSONDecodeError as exc:
            raise ValueError("JOBMARKET_FINLAND_HTTP_HEADERS_JSON must be valid JSON") from exc
        if not isinstance(headers, dict) or not all(
            isinstance(name, str) and isinstance(value, str) for name, value in headers.items()
        ):
            raise ValueError("JOBMARKET_FINLAND_HTTP_HEADERS_JSON must be a string-to-string object")
        languages = tuple(
            item.strip().casefold()
            for item in os.getenv("JOBMARKET_FINLAND_POSTING_LANGUAGES", "fi,en,sv").split(",")
            if item.strip()
        )
        return cls(
            environment=environment,
            endpoint=endpoint,
            subscription_key=key,
            extra_headers=headers,
            posting_languages=languages,
            timeout_seconds=float(os.getenv("JOBMARKET_FINLAND_TIMEOUT_SECONDS", "20")),
            max_bytes=int(os.getenv("JOBMARKET_FINLAND_MAX_BYTES", str(DEFAULT_MAX_BYTES))),
            max_items=int(os.getenv("JOBMARKET_FINLAND_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))),
            initial_lookback_minutes=int(os.getenv("JOBMARKET_FINLAND_INITIAL_LOOKBACK_MINUTES", "120")),
            overlap_minutes=int(os.getenv("JOBMARKET_FINLAND_OVERLAP_MINUTES", "5")),
        )


class JobMarketFinlandAdapter:
    source_id = SOURCE_ID
    parser_version = PARSER_VERSION

    def __init__(
        self,
        settings: JobMarketFinlandSettings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.environment = settings.environment
        self._client = http_client or httpx.Client(
            timeout=settings.timeout_seconds,
            follow_redirects=False,
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def policy(self) -> SourcePolicy:
        return SourcePolicy(
            source_id=self.source_id,
            display_name="Job Market Finland",
            source_class="national_job_market",
            allowed_modes=("api",),
            terms_review_status="approved",
            active=True,
            notes="KEHA credential-gated P67 retrieval API v2.",
        )

    def _headers(self) -> dict[str, str]:
        return {
            **self.settings.extra_headers,
            "KIPA-Subscription-Key": self.settings.subscription_key,
            "Accept": "application/x-ndjson",
            "Content-Type": "application/json",
        }

    def fetch_window(
        self,
        *,
        status: str,
        modified_from: str,
        modified_to: str,
        observed_at: str | None = None,
    ) -> JobMarketFinlandBatch:
        mode = str(status or "").strip().upper()
        if mode not in SUPPORTED_STATUSES:
            raise JobMarketFinlandAPIError("unsupported P67 posting status")
        body: dict[str, Any] = {
            "onlyStatus": mode,
            "modified": {
                "from": str(modified_from or "").strip(),
                "to": str(modified_to or "").strip(),
            },
        }
        if not body["modified"]["from"] or not body["modified"]["to"]:
            raise JobMarketFinlandAPIError("P67 modified interval is required")
        if self.settings.posting_languages:
            body["postingLanguageIn"] = list(self.settings.posting_languages)

        try:
            response = self._client.post(
                self.settings.endpoint,
                headers=self._headers(),
                json=body,
            )
        except httpx.HTTPError as exc:
            raise JobMarketFinlandAPIError(f"P67 request failed: {type(exc).__name__}") from exc
        if 300 <= response.status_code < 400:
            raise JobMarketFinlandAPIError("P67 redirects are not followed")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise JobMarketFinlandAPIError(f"P67 returned HTTP {response.status_code}") from exc

        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) > self.settings.max_bytes:
                    raise JobMarketFinlandAPIError("P67 response exceeds configured size limit")
            except ValueError:
                pass

        return parse_ndjson(
            response.content,
            status=mode,
            endpoint=self.settings.endpoint,
            observed_at=observed_at,
            locale_preference=self.settings.posting_languages or ("fi", "en", "sv"),
            max_bytes=self.settings.max_bytes,
            max_items=self.settings.max_items,
        )

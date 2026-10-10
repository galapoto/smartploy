"""Read-only public employer ATS source adapters.

Smartploy supports explicit operator-configured SmartRecruiters and Lever tenants.
No arbitrary API base URL is accepted. These adapters only read published/public
job postings; application submission endpoints are intentionally out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote
import json
import os
import re

import httpx

from ..domain import SourceObservation, SourcePolicy, canonicalize_url, utc_now_iso


SUPPORTED_PROVIDERS = {"smartrecruiters", "lever"}
SUPPORTED_SECTORS = {"public", "private", "unknown"}
SUPPORTED_LEVER_STACKS = {"global", "eu"}
TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,99}$")
ALLOWED_CONFIG_KEYS = {
    "provider",
    "tenant",
    "label",
    "stack",
    "employer_sector",
    "external_ai_forwarding_allowed",
}
SMARTRECRUITERS_HOST = "api.smartrecruiters.com"
LEVER_HOSTS = {
    "global": "api.lever.co",
    "eu": "api.eu.lever.co",
}
SMARTRECRUITERS_ATTRIBUTION = "SmartRecruiters public Posting API"
LEVER_ATTRIBUTION = "Lever published Postings API"
PARSER_VERSIONS = {
    "smartrecruiters": "smartrecruiters-posting-v1",
    "lever": "lever-postings-v1",
}


class PublicATSError(RuntimeError):
    pass


def _strip_html(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _string(value: Any) -> str:
    return str(value or "").strip()


def _label(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("label", "name", "text", "value", "code", "id"):
            item = value.get(key)
            if item not in (None, ""):
                return str(item).strip()
    return ""


def _list_strings(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return [_label(value)] if _label(value) else []
    result: list[str] = []
    for item in value:
        text = _label(item)
        if text:
            result.append(text)
    return result


@dataclass(frozen=True)
class PublicATSSourceConfig:
    provider: str
    tenant: str
    label: str
    stack: str = ""
    employer_sector: str = "unknown"
    external_ai_forwarding_allowed: bool = False

    def __post_init__(self) -> None:
        provider = _string(self.provider).casefold()
        tenant = _string(self.tenant)
        label = _string(self.label)
        sector = _string(self.employer_sector).casefold() or "unknown"
        stack = _string(self.stack).casefold()

        if provider not in SUPPORTED_PROVIDERS:
            raise PublicATSError("provider must be smartrecruiters or lever")
        if not TENANT_PATTERN.fullmatch(tenant):
            raise PublicATSError(
                "tenant must contain only letters, numbers and hyphens and be at most 100 characters"
            )
        if not label or len(label) > 200 or any(ord(char) < 32 for char in label):
            raise PublicATSError("label is required and must be a short printable value")
        if sector not in SUPPORTED_SECTORS:
            raise PublicATSError("employer_sector must be public, private or unknown")
        if not isinstance(self.external_ai_forwarding_allowed, bool):
            raise PublicATSError("external_ai_forwarding_allowed must be boolean")

        if provider == "lever":
            stack = stack or "global"
            if stack not in SUPPORTED_LEVER_STACKS:
                raise PublicATSError("Lever stack must be global or eu")
        elif stack:
            raise PublicATSError("stack is only supported for Lever")

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "tenant", tenant)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "stack", stack)
        object.__setattr__(self, "employer_sector", sector)

    @property
    def source_id(self) -> str:
        tenant = self.tenant.casefold()
        if self.provider == "lever":
            return f"lever-{self.stack}-{tenant}"
        return f"smartrecruiters-{tenant}"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PublicATSSourceConfig":
        if not isinstance(value, dict):
            raise PublicATSError("ATS source configuration items must be objects")
        unknown = set(value) - ALLOWED_CONFIG_KEYS
        if unknown:
            raise PublicATSError(
                "unsupported ATS source configuration fields: " + ", ".join(sorted(unknown))
            )
        required = ("provider", "tenant", "label")
        if any(key not in value for key in required):
            raise PublicATSError("ATS source configuration requires provider, tenant and label")
        return cls(
            provider=value["provider"],
            tenant=value["tenant"],
            label=value["label"],
            stack=value.get("stack", ""),
            employer_sector=value.get("employer_sector", "unknown"),
            external_ai_forwarding_allowed=value.get(
                "external_ai_forwarding_allowed",
                False,
            ),
        )


@dataclass(frozen=True)
class PublicATSRuntimeSettings:
    timeout_seconds: float = 15.0
    page_size: int = 100
    max_items: int = 10000
    max_response_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise PublicATSError("ATS timeout must be positive")
        if self.page_size <= 0 or self.page_size > 100:
            raise PublicATSError("ATS page_size must be between 1 and 100")
        if self.max_items <= 0 or self.max_response_bytes <= 0:
            raise PublicATSError("ATS item/response limits must be positive")

    @classmethod
    def from_env(cls) -> "PublicATSRuntimeSettings":
        return cls(
            timeout_seconds=float(os.getenv("SMARTPLOY_PUBLIC_ATS_TIMEOUT_SECONDS", "15")),
            page_size=int(os.getenv("SMARTPLOY_PUBLIC_ATS_PAGE_SIZE", "100")),
            max_items=int(os.getenv("SMARTPLOY_PUBLIC_ATS_MAX_ITEMS", "10000")),
            max_response_bytes=int(
                os.getenv("SMARTPLOY_PUBLIC_ATS_MAX_RESPONSE_BYTES", str(10 * 1024 * 1024))
            ),
        )


def _parse_config_payload(payload: Any) -> list[PublicATSSourceConfig]:
    if not isinstance(payload, list):
        raise PublicATSError("ATS source configuration must be a JSON array")
    configs = [PublicATSSourceConfig.from_dict(item) for item in payload]
    source_ids = [item.source_id for item in configs]
    if len(source_ids) != len(set(source_ids)):
        raise PublicATSError("ATS source configuration contains duplicate source identities")
    return configs


def load_public_ats_sources() -> list[PublicATSSourceConfig]:
    inline = os.getenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", "").strip()
    file_path = os.getenv("SMARTPLOY_PUBLIC_ATS_SOURCES_FILE", "").strip()
    if inline and file_path:
        raise PublicATSError(
            "configure either SMARTPLOY_PUBLIC_ATS_SOURCES_JSON or SMARTPLOY_PUBLIC_ATS_SOURCES_FILE"
        )
    if not inline and not file_path:
        return []

    try:
        if inline:
            payload = json.loads(inline)
        else:
            payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicATSError("unable to load ATS source configuration") from exc
    return _parse_config_payload(payload)


class PublicATSAdapter:
    provider = ""
    parser_version = ""

    def __init__(
        self,
        config: PublicATSSourceConfig,
        runtime: PublicATSRuntimeSettings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.runtime = runtime or PublicATSRuntimeSettings()
        self.source_id = config.source_id
        self._client = http_client or httpx.Client(
            timeout=self.runtime.timeout_seconds,
            follow_redirects=False,
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def policy(self) -> SourcePolicy:
        return SourcePolicy(
            source_id=self.source_id,
            display_name=self.config.label,
            source_class="direct_employer_ats",
            allowed_modes=("api",),
            terms_review_status="approved",
            active=True,
            notes=f"Read-only public {self.provider} posting API.",
        )

    def _get_json(
        self,
        url: str,
        *,
        expected_host: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise PublicATSError(f"{self.provider} request failed: {type(exc).__name__}") from exc
        if response.request.url.host != expected_host:
            raise PublicATSError("ATS request host changed unexpectedly")
        if 300 <= response.status_code < 400:
            raise PublicATSError("ATS redirects are not followed")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PublicATSError(
                f"{self.provider} returned HTTP {response.status_code}"
            ) from exc
        if len(response.content) > self.runtime.max_response_bytes:
            raise PublicATSError("ATS response exceeds configured size limit")
        try:
            return response.json()
        except ValueError as exc:
            raise PublicATSError("ATS returned invalid JSON") from exc

    def fetch_all(self, *, observed_at: str | None = None) -> list[SourceObservation]:
        raise NotImplementedError


class SmartRecruitersAdapter(PublicATSAdapter):
    provider = "smartrecruiters"
    parser_version = PARSER_VERSIONS["smartrecruiters"]

    def __init__(
        self,
        config: PublicATSSourceConfig,
        runtime: PublicATSRuntimeSettings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if config.provider != self.provider:
            raise PublicATSError("SmartRecruiters adapter requires smartrecruiters config")
        super().__init__(config, runtime, http_client=http_client)
        self.base = (
            "https://api.smartrecruiters.com/v1/companies/"
            + quote(config.tenant, safe="")
            + "/postings"
        )

    @staticmethod
    def _section(sections: Any, name: str) -> str:
        if not isinstance(sections, dict):
            return ""
        value = sections.get(name)
        if isinstance(value, dict):
            return _strip_html(value.get("text") or value.get("content"))
        return _strip_html(value)

    def _observation(self, detail: dict[str, Any], observed_at: str) -> SourceObservation:
        external_id = _string(detail.get("id"))
        if not external_id:
            raise PublicATSError("SmartRecruiters posting detail is missing id")

        company = detail.get("company") if isinstance(detail.get("company"), dict) else {}
        location = detail.get("location") if isinstance(detail.get("location"), dict) else {}
        job_ad = detail.get("jobAd") if isinstance(detail.get("jobAd"), dict) else {}
        sections = job_ad.get("sections") if isinstance(job_ad.get("sections"), dict) else {}

        title = _string(detail.get("name"))
        employer = _string(company.get("name")) or self.config.label
        if not title:
            raise PublicATSError("SmartRecruiters posting detail is missing name")

        company_description = self._section(sections, "companyDescription")
        job_description = self._section(sections, "jobDescription")
        qualifications = self._section(sections, "qualifications")
        additional = self._section(sections, "additionalInformation")
        description = " ".join(
            item for item in (job_description, qualifications, additional) if item
        )

        location_parts = [
            _string(location.get("city")),
            _string(location.get("region")),
            _string(location.get("country")),
        ]
        display_location = ", ".join(item for item in location_parts if item)
        remote = location.get("remote") is True

        posting_url = canonicalize_url(_string(detail.get("postingUrl")))
        apply_url = canonicalize_url(_string(detail.get("applyUrl"))) or posting_url
        detail_url = self.base + "/" + quote(external_id, safe="")
        source_url = posting_url or detail_url

        industry = _label(detail.get("industry"))
        department = _label(detail.get("department"))
        function = _label(detail.get("function"))
        experience = _label(detail.get("experienceLevel"))
        employment = _label(detail.get("typeOfEmployment"))

        payload = {
            "company": employer,
            "role_title": title,
            "description": description,
            "location": display_location,
            "work_mode": "remote" if remote else "review",
            "application_url": apply_url,
            "sector": industry,
            "employer_sector": self.config.employer_sector,
            "source_attribution": SMARTRECRUITERS_ATTRIBUTION,
            "external_ai_forwarding_allowed": self.config.external_ai_forwarding_allowed,
            "source_details": {
                "provider": self.provider,
                "tenant": self.config.tenant,
                "uuid": _string(detail.get("uuid")),
                "released_date": _string(detail.get("releasedDate")),
                "industry": industry,
                "department": department,
                "function": function,
                "experience_level": experience,
                "type_of_employment": employment,
                "company_description": company_description,
                "qualifications": qualifications,
                "additional_information": additional,
            },
        }
        return SourceObservation(
            source_id=self.source_id,
            source_mode="api",
            source_url=source_url,
            raw_text=" ".join(
                item for item in (title, employer, description, company_description) if item
            ),
            payload=payload,
            observed_at=observed_at,
            posted_at=_string(detail.get("releasedDate")),
            source_external_id=external_id,
        )

    def fetch_all(self, *, observed_at: str | None = None) -> list[SourceObservation]:
        timestamp = observed_at or utc_now_iso()
        offset = 0
        summaries: list[dict[str, Any]] = []

        while True:
            payload = self._get_json(
                self.base,
                expected_host=SMARTRECRUITERS_HOST,
                params={
                    "limit": self.runtime.page_size,
                    "offset": offset,
                    "destination": "PUBLIC",
                },
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
                raise PublicATSError("SmartRecruiters list response has unexpected shape")
            page = payload["content"]
            for item in page:
                if not isinstance(item, dict):
                    raise PublicATSError("SmartRecruiters list contains a non-object posting")
                summaries.append(item)
                if len(summaries) > self.runtime.max_items:
                    raise PublicATSError("SmartRecruiters result exceeds configured item limit")

            total = payload.get("totalFound")
            if isinstance(total, int) and offset + len(page) >= total:
                break
            if len(page) < self.runtime.page_size:
                break
            if not page:
                break
            offset += len(page)

        observations: list[SourceObservation] = []
        for summary in summaries:
            posting_id = _string(summary.get("id"))
            if not posting_id:
                raise PublicATSError("SmartRecruiters list item is missing id")
            detail_url = self.base + "/" + quote(posting_id, safe="")
            detail = self._get_json(detail_url, expected_host=SMARTRECRUITERS_HOST)
            if not isinstance(detail, dict):
                raise PublicATSError("SmartRecruiters detail response is not an object")
            observations.append(self._observation(detail, timestamp))
        return observations


class LeverAdapter(PublicATSAdapter):
    provider = "lever"
    parser_version = PARSER_VERSIONS["lever"]

    def __init__(
        self,
        config: PublicATSSourceConfig,
        runtime: PublicATSRuntimeSettings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if config.provider != self.provider:
            raise PublicATSError("Lever adapter requires lever config")
        super().__init__(config, runtime, http_client=http_client)
        self.host = LEVER_HOSTS[config.stack]
        self.base = "https://" + self.host + "/v0/postings/" + quote(config.tenant, safe="")

    def _observation(self, item: dict[str, Any], observed_at: str) -> SourceObservation:
        external_id = _string(item.get("id"))
        title = _string(item.get("text"))
        if not external_id or not title:
            raise PublicATSError("Lever posting is missing id/title")

        categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
        salary = item.get("salaryRange") if isinstance(item.get("salaryRange"), dict) else {}

        description = " ".join(
            part
            for part in (
                _strip_html(item.get("descriptionPlain") or item.get("description")),
                _strip_html(item.get("additionalPlain") or item.get("additional")),
                _strip_html(item.get("openingPlain") or item.get("opening")),
            )
            if part
        )

        hosted_url = canonicalize_url(_string(item.get("hostedUrl")))
        apply_url = canonicalize_url(_string(item.get("applyUrl"))) or hosted_url
        source_url = hosted_url or self.base + "/" + quote(external_id, safe="")

        workplace = _string(item.get("workplaceType")).casefold()
        work_mode = "review"
        if workplace == "remote":
            work_mode = "remote"
        elif workplace == "hybrid":
            work_mode = "hybrid"
        elif workplace in {"on-site", "onsite", "on site"}:
            work_mode = "onsite"

        salary_currency = _string(salary.get("currency")).upper()
        salary_min_eur = salary.get("min") if salary_currency == "EUR" else None
        salary_max_eur = salary.get("max") if salary_currency == "EUR" else None

        source_details = {
            "provider": self.provider,
            "tenant": self.config.tenant,
            "stack": self.config.stack,
            "commitment": _string(categories.get("commitment")),
            "team": _string(categories.get("team")),
            "department": _string(categories.get("department")),
            "all_locations": _list_strings(categories.get("allLocations")),
            "country": _string(item.get("country")),
            "workplace_type": _string(item.get("workplaceType")),
            "salary_range": dict(salary),
            "lists": item.get("lists") if isinstance(item.get("lists"), list) else [],
        }

        payload = {
            "company": self.config.label,
            "role_title": title,
            "description": description,
            "location": _string(categories.get("location")),
            "work_mode": work_mode,
            "application_url": apply_url,
            "employer_sector": self.config.employer_sector,
            "source_attribution": LEVER_ATTRIBUTION,
            "external_ai_forwarding_allowed": self.config.external_ai_forwarding_allowed,
            "salary_min_eur": salary_min_eur,
            "salary_max_eur": salary_max_eur,
            "source_details": source_details,
        }

        return SourceObservation(
            source_id=self.source_id,
            source_mode="api",
            source_url=source_url,
            raw_text=" ".join(
                part for part in (title, self.config.label, description) if part
            ),
            payload=payload,
            observed_at=observed_at,
            posted_at="",
            source_external_id=external_id,
        )

    def fetch_all(self, *, observed_at: str | None = None) -> list[SourceObservation]:
        timestamp = observed_at or utc_now_iso()
        skip = 0
        observations: list[SourceObservation] = []

        while True:
            payload = self._get_json(
                self.base,
                expected_host=self.host,
                params={
                    "mode": "json",
                    "skip": skip,
                    "limit": self.runtime.page_size,
                },
            )
            if not isinstance(payload, list):
                raise PublicATSError("Lever list response has unexpected shape")
            for item in payload:
                if not isinstance(item, dict):
                    raise PublicATSError("Lever list contains a non-object posting")
                observations.append(self._observation(item, timestamp))
                if len(observations) > self.runtime.max_items:
                    raise PublicATSError("Lever result exceeds configured item limit")
            if len(payload) < self.runtime.page_size:
                break
            if not payload:
                break
            skip += len(payload)

        return observations


def build_public_ats_adapter(
    config: PublicATSSourceConfig,
    runtime: PublicATSRuntimeSettings | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> PublicATSAdapter:
    if config.provider == "smartrecruiters":
        return SmartRecruitersAdapter(config, runtime, http_client=http_client)
    if config.provider == "lever":
        return LeverAdapter(config, runtime, http_client=http_client)
    raise PublicATSError("unsupported ATS provider")

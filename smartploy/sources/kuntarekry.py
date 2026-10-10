"""Authorized Kuntarekry RSS/XML feed adapter.

Kuntarekry currently documents RSS/XML feeds for employers. Smartploy therefore
accepts an explicitly configured authorized feed URL and does not automate login
or scrape protected pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from html import unescape
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit
import json
import os
import re
import xml.etree.ElementTree as ET

import httpx

from ..domain import SourceObservation, SourcePolicy, utc_now_iso


PARSER_VERSION = "kuntarekry-rss-xml-v1"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


class KuntarekryFeedError(RuntimeError):
    pass


def _host_allowed(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    folded = host.casefold().rstrip(".")
    for allowed in allowed_hosts:
        root = allowed.casefold().strip().rstrip(".")
        if root and (folded == root or folded.endswith("." + root)):
            return True
    return False


def validate_feed_url(url: str, allowed_hosts: tuple[str, ...] = ("kuntarekry.fi",)) -> str:
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError as exc:
        raise KuntarekryFeedError("invalid feed URL") from exc
    if parts.scheme.casefold() != "https":
        raise KuntarekryFeedError("Kuntarekry feed URL must use HTTPS")
    if not parts.hostname or parts.username or parts.password:
        raise KuntarekryFeedError("Kuntarekry feed URL host is invalid")
    host = parts.hostname.casefold()
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise KuntarekryFeedError("IP-literal feed URLs are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise KuntarekryFeedError("invalid feed URL port") from exc
    if port not in (None, 443):
        raise KuntarekryFeedError("non-standard feed URL ports are not allowed")
    if not _host_allowed(host, allowed_hosts):
        raise KuntarekryFeedError("feed URL host is not allowlisted")
    return str(url).strip()


def redacted_feed_identity(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _clean_html(value: str) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _first(mapping: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key.casefold(), "")
        if value:
            return value.strip()
    return ""


def _posted_at(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        return text
    return ""


def _item_fields(item: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in list(item):
        key = _local_name(child.tag)
        value = _text(child)
        if key == "link" and not value:
            value = str(child.attrib.get("href") or "").strip()
        if value and key not in values:
            values[key] = value
    return values


def parse_kuntarekry_feed(
    content: bytes,
    *,
    feed_url: str,
    observed_at: str | None = None,
    source_id: str = "kuntarekry",
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[SourceObservation]:
    if len(content) > max_bytes:
        raise KuntarekryFeedError("feed exceeds configured size limit")
    upper = content[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise KuntarekryFeedError("DTD/entity declarations are not accepted")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise KuntarekryFeedError("invalid XML feed") from exc

    channel_title = ""
    for node in root.iter():
        if _local_name(node.tag) == "channel":
            for child in list(node):
                if _local_name(child.tag) == "title":
                    channel_title = _clean_html(_text(child))
                    break
            break

    entries = [
        node
        for node in root.iter()
        if _local_name(node.tag) in {"item", "entry", "job", "vacancy"}
    ]
    timestamp = observed_at or utc_now_iso()
    observations: list[SourceObservation] = []
    fallback_source_url = redacted_feed_identity(feed_url)

    for item in entries:
        fields = _item_fields(item)
        title = _clean_html(_first(fields, "jobtitle", "title", "name"))
        company = _clean_html(
            _first(fields, "employer", "organization", "organizationname", "company") or channel_title
        )
        description = _clean_html(_first(fields, "description", "summary", "content"))
        link = _first(fields, "link", "url", "applicationurl", "applyurl")
        guid = _first(fields, "guid", "id", "jobid", "reference")
        if not title or not company:
            continue
        payload = {
            "company": company,
            "role_title": title,
            "description": description,
            "location": _clean_html(_first(fields, "location", "city", "municipality")),
            "deadline": _first(fields, "deadline", "applicationdeadline", "closingdate"),
            "language": _clean_html(_first(fields, "language", "languages")),
            "sector": _clean_html(_first(fields, "sector", "category")),
            "employer_sector": "public",
            "application_url": link or fallback_source_url,
        }
        observations.append(
            SourceObservation(
                source_id=source_id,
                source_mode="feed",
                source_url=link or fallback_source_url,
                raw_text=" ".join(part for part in (title, company, description) if part),
                payload=payload,
                observed_at=timestamp,
                posted_at=_posted_at(_first(fields, "pubdate", "published", "updated", "date")),
                source_external_id=guid or link or title,
            )
        )
    return observations


@dataclass(frozen=True)
class KuntarekryFeedSettings:
    feed_url: str
    allowed_hosts: tuple[str, ...] = ("kuntarekry.fi",)
    timeout_seconds: float = 15.0
    max_bytes: int = DEFAULT_MAX_BYTES
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "KuntarekryFeedSettings | None":
        feed_url = os.getenv("KUNTAREKRY_FEED_URL", "").strip()
        if not feed_url:
            return None
        hosts = tuple(
            item.strip()
            for item in os.getenv("KUNTAREKRY_ALLOWED_HOSTS", "kuntarekry.fi").split(",")
            if item.strip()
        )
        raw_headers = os.getenv("KUNTAREKRY_HTTP_HEADERS_JSON", "{}").strip() or "{}"
        try:
            headers = json.loads(raw_headers)
        except json.JSONDecodeError as exc:
            raise ValueError("KUNTAREKRY_HTTP_HEADERS_JSON must be valid JSON") from exc
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
        ):
            raise ValueError("KUNTAREKRY_HTTP_HEADERS_JSON must be a string-to-string object")
        return cls(
            feed_url=validate_feed_url(feed_url, hosts),
            allowed_hosts=hosts,
            timeout_seconds=float(os.getenv("KUNTAREKRY_TIMEOUT_SECONDS", "15")),
            max_bytes=int(os.getenv("KUNTAREKRY_MAX_BYTES", str(DEFAULT_MAX_BYTES))),
            headers=headers,
        )


class KuntarekryFeedAdapter:
    source_id = "kuntarekry"
    parser_version = PARSER_VERSION

    def __init__(
        self,
        settings: KuntarekryFeedSettings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        validate_feed_url(settings.feed_url, settings.allowed_hosts)
        self.settings = settings
        self._client = http_client or httpx.Client(
            timeout=settings.timeout_seconds,
            headers=dict(settings.headers),
            follow_redirects=False,
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def policy(self) -> SourcePolicy:
        return SourcePolicy(
            source_id=self.source_id,
            display_name="Kuntarekry",
            source_class="public_sector_jobs",
            allowed_modes=("feed",),
            terms_review_status="approved",
            active=True,
            notes="Authorized/configured Kuntarekry RSS/XML feed; no login automation.",
        )

    def fetch(self, *, observed_at: str | None = None) -> list[SourceObservation]:
        validate_feed_url(self.settings.feed_url, self.settings.allowed_hosts)
        try:
            response = self._client.get(
                self.settings.feed_url,
                headers={"Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.1"},
            )
        except httpx.HTTPError as exc:
            raise KuntarekryFeedError(f"feed request failed: {type(exc).__name__}") from exc
        if 300 <= response.status_code < 400:
            raise KuntarekryFeedError("feed redirects are not followed")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KuntarekryFeedError(f"feed returned HTTP {response.status_code}") from exc
        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) > self.settings.max_bytes:
                    raise KuntarekryFeedError("feed exceeds configured size limit")
            except ValueError:
                pass
        content = response.content
        return parse_kuntarekry_feed(
            content,
            feed_url=self.settings.feed_url,
            observed_at=observed_at,
            source_id=self.source_id,
            max_bytes=self.settings.max_bytes,
        )

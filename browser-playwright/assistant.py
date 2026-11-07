"""SmartPloy SP110: local, review-gated Playwright application form filling.

First-party reuse/adaptation (not a new general browser agent):
* obumai/obumellm@d682da2582ebfa3f013cf37dc542384fe605f303
  obumellm/browser/fill.py: candidate selectors, field matching, safe fill.
  obumellm/browser/live_session.py: visible persistent Chromium context.
* galapoto/smartploy browser-companion/logic.mjs: packet identity, allowlisted
  employer hosts, ordinary-contact field matching and sensitive-field denial.

The browser runs on the applicant's own computer. Only exact approved hosted
Lever/Ashby/Greenhouse/TalentAdore forms are supported. The legacy CLI never
uploads, and the paired SP112 bridge attaches ONLY the exact reviewed
CV PDF after separate user approval. No submit/click, CAPTCHA bypass,
credential collection, hidden browser or background employer actions.
"""
from __future__ import annotations

import getpass
import ipaddress
from hashlib import sha256
import json
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import SplitResult, urlsplit


SCHEMA = "smartploy.browser_handoff.v2"
FIELD_NAMES = (
    "full_name", "first_name", "last_name", "email", "phone",
    "location", "linkedin", "github", "cover_letter",
)
UNSAFE_INPUT_TYPES = {
    "hidden", "file", "password", "submit", "button", "reset", "image",
    "checkbox", "radio", "select", "number", "date",
}
SAFE_INPUT_TYPES = {"text", "email", "tel", "url", "search", "textarea"}
UNSAFE_METADATA = re.compile(
    r"\b(?:visa|sponsorship|sponsor|immigration|work authorization|work permit|"
    r"salary|compensation|wage|expected pay|eeo|race|ethnic|gender|sex|sexual|"
    r"religion|disability|veteran|military|medical|health|criminal|background|"
    r"citizenship|nationality|passport|birth|age|social security|ssn|gdpr|"
    r"privacy|consent|agreement|attest|signature|certification|legal|bank|tax|company|"
    r"employer|organization|organisation|referee|recommender|palkka|työlupa|"
    r"oleskelulupa|kansalaisuus|sukupuoli|uskonto|syntym|henkilötunnus|"
    r"suostumus|tietosuoja|arbetstillstand|medborgarskap|personnummer|samtycke|lön)\b",
    re.IGNORECASE,
)
UNSAFE_COMPACT = re.compile(
    r"(?:visa|sponsor|salary|compensat|wage|workauth|workpermit|citizen|nationality|"
    r"company|employer|organization|organisation|referral|referee|recommender|gender|sex|race|ethnic|religion|disabil|veteran|passport|birth|dateofbirth|"
    r"consent|privacy|agreement|legal|attest|signature|criminal|backgroundcheck|"
    r"immigrat|taxid|nationalid|gdpr|henkilotunnus|sukupuol|kansalaisuu|"
    r"oleskelulup|tyolup|palkka|arbetstillstand|medborgarskap|personnummer|samtycke)",
    re.IGNORECASE,
)
WORKSPACE_ID = re.compile(r"kit-[a-f0-9]{30}\Z")
HEXDIGEST = re.compile(r"[a-f0-9]{64}\Z")
EMPLOYER_TOKEN = r"[A-Za-z0-9_-]+"
LEVER_PATH = re.compile(rf"/{EMPLOYER_TOKEN}/{EMPLOYER_TOKEN}(?:/apply/?)?\Z")
ASHBY_PATH = re.compile(
    rf"/[A-Za-z0-9_-]{{1,100}}/[A-Za-z0-9_-]{{1,160}}(?:/application/?)?\Z"
)
GH_PATH = re.compile(r"/[A-Za-z0-9_-]{1,100}/jobs/[0-9]{1,20}/?\Z")
TALENTADORE_PATH = re.compile(r"/apply/[A-Za-z0-9_-]{1,120}/[A-Za-z0-9_-]{5,30}/?\Z")

READ_FIELDS_JS = """
els => els.map((el, index) => {
  const label = el.labels && el.labels.length ? el.labels[0].textContent.trim() : "";
  const type = el.tagName.toLowerCase() === "textarea" ? "textarea" :
    String(el.getAttribute("type") || "text").toLowerCase();
  return {
    index, tag: el.tagName.toLowerCase(), type,
    id: el.id || "", name: el.getAttribute("name") || "",
    placeholder: el.getAttribute("placeholder") || "",
    label: label || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "",
    autocomplete: el.getAttribute("autocomplete") || "",
    accept: el.getAttribute("accept") || "", multiple: Boolean(el.multiple),
    required: Boolean(el.required), disabled: Boolean(el.disabled),
    readonly: Boolean(el.readOnly), hasValue: Boolean(String(el.value || "").trim()),
    visible: Boolean(el.getClientRects().length),
    inForm: Boolean(el.closest("form")),
    maxLength: el.maxLength || -1
  };
})
"""


class PacketError(ValueError):
    """Refuse unsupported/stale packets, changed forms and unsafe actions."""


PUBLIC_DOMAIN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\Z"
)
RESERVED_SUFFIXES = (
    ".local", ".localhost", ".internal", ".test",
    ".invalid", ".example", ".onion",
)


def _url_parts(raw: str) -> SplitResult:
    """One reviewed PUBLIC HTTPS employer URL; never an internal resource."""
    if not isinstance(raw, str) or len(raw) > 1500 or not raw.startswith("https://"):
        raise PacketError("A reviewed public HTTPS employer URL is required")
    if "\\" in raw or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        raise PacketError("Employer URL has forbidden characters")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or not host or not PUBLIC_DOMAIN.fullmatch(host)
            or host.endswith(RESERVED_SUFFIXES)
            or (not parsed.path.strip("/") and not parsed.query)
            or len(parsed.query) > 800
        ):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
    except ValueError as exc:
        raise PacketError("Employer URL is not a public, reviewable HTTPS job link") from exc
    return parsed


def _same_generic_job_path(approved: SplitResult, current: SplitResult) -> bool:
    """Port first-party SmartPloy exact-reviewed-job path policy."""
    if current.query != approved.query:
        return False
    source = approved.path.rstrip("/") or "/"
    live = current.path.rstrip("/") or "/"
    if live == source:
        return True
    if source == "/":
        return False
    if any(live == source + suffix or live.startswith(source + suffix + "/")
           for suffix in ("/apply", "/application")):
        return True
    return source.endswith(("/apply", "/application")) and live.startswith(source + "/")


def same_reviewed_form(posting_url: str, current_url: str) -> bool:
    """Exact hosted ATS job, or one manually selected public employer origin.

    Generic sites use the SAME public hostname, never any redirected third
    party. The applicant sees the full Chromium URL and must inspect fields
    before the explicit one-use fill; no final submit right follows.
    """
    try:
        p, c = _url_parts(posting_url), _url_parts(current_url)
    except PacketError:
        return False
    if p.hostname in {"jobs.lever.co", "jobs.eu.lever.co"}:
        if c.hostname != p.hostname or p.query or c.query or not LEVER_PATH.fullmatch(p.path):
            return False
        base = re.sub(r"/apply/?$", "", p.path).rstrip("/")
        return c.path.rstrip("/") == base + "/apply"
    if p.hostname == "jobs.ashbyhq.com":
        if c.hostname != p.hostname or p.query or c.query or not ASHBY_PATH.fullmatch(p.path):
            return False
        base = re.sub(r"/application/?$", "", p.path).rstrip("/")
        return c.path.rstrip("/") == base + "/application"
    if p.hostname == "ats.talentadore.com":
        return (
            c.hostname == "ats.talentadore.com"
            and not p.query and not c.query
            and TALENTADORE_PATH.fullmatch(p.path) is not None
            and c.path.rstrip("/") == p.path.rstrip("/")
        )
    if p.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        return (
            c.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}
            and not p.query and not c.query
            and GH_PATH.fullmatch(p.path) is not None
            and c.path.rstrip("/") == p.path.rstrip("/")
        )
    # Unlisted employer site: user must recognize the visible job/form;
    # hostname boundary is strict, so no silent cross-provider redirects.
    return c.hostname == p.hostname and _same_generic_job_path(p, c)



def reviewed_initial_form_url(posting_url: str) -> str:
    """Open the exact Lever/Ashby form instead of a dead-end job landing page.

    The applicant already approved this saved job in SmartPloy. A direct
    GET in visible Chromium is allowed only for the documented same-job
    hosted ATS form; generic employers, Greenhouse and TalentAdore keep
    their original URL. No website buttons, login, upload or submit happen.
    """
    parsed = _url_parts(posting_url)
    providers = {
        "jobs.lever.co": (LEVER_PATH, "apply"),
        "jobs.eu.lever.co": (LEVER_PATH, "apply"),
        "jobs.ashbyhq.com": (ASHBY_PATH, "application"),
    }
    provider = providers.get(parsed.hostname)
    if provider is None or parsed.query:
        return posting_url
    pattern, final_segment = provider
    if not pattern.fullmatch(parsed.path):
        return posting_url
    base_path = re.sub(rf"/{final_segment}/?$", "", parsed.path).rstrip("/")
    form_url = (
        f"{parsed.scheme}://{parsed.netloc}{base_path}/{final_segment}"
    )
    # The original exact-job validator is authoritative. No arbitrary
    # same-host path guesses, third-party redirect or tracking parameters.
    if not same_reviewed_form(posting_url, form_url):
        raise PacketError("The saved employer job has no safe direct form URL")
    return form_url


def _approved_fields_sha256(fields: dict[str, str]) -> str:
    """Copy SmartPloy's original length-prefixed, canonical fields fingerprint."""
    parts = [str(len(fields[key].encode("utf-8"))) + ":" + fields[key]
             for key in FIELD_NAMES]
    return sha256(("smartploy.fields.v1\0" + "\0".join(parts)).encode("utf-8")).hexdigest()


def _parse_time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone missing")
        return stamp.astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError) as exc:
        raise PacketError("Invalid application packet expiry") from exc


def validate_packet(raw: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Fail closed on packet shape/owner-bound revision/time and supported hosts.

    A packet is private content, not an employer-submission credential. It must
    originate from a personally reviewed and saved SmartPloy workspace.
    """
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise PacketError("Use the current SmartPloy reviewed autofill packet")
    if (
        not isinstance(raw.get("workspace_id"), str)
        or not WORKSPACE_ID.fullmatch(raw["workspace_id"])
        or type(raw.get("revision")) is not int or raw["revision"] < 2
        or not isinstance(raw.get("document_sha256"), str)
        or not HEXDIGEST.fullmatch(raw["document_sha256"])
        or not isinstance(raw.get("cv_pdf_sha256"), str)
        or not HEXDIGEST.fullmatch(raw["cv_pdf_sha256"])
        or type(raw.get("cv_pdf_size")) is not int
        or not 12 <= raw["cv_pdf_size"] <= 2 * 1024 * 1024
    ):
        raise PacketError("The reviewed application revision or PDF identity is invalid")
    issued, expires = _parse_time(raw.get("issued_at")), _parse_time(raw.get("expires_at"))
    clock = now or datetime.now(timezone.utc)
    if (
        issued > clock + timedelta(minutes=2) or expires <= clock
        or expires <= issued or expires - issued > timedelta(minutes=15)
    ):
        raise PacketError("The application packet has expired. Copy a new one.")
    url = raw.get("application_url")
    if not isinstance(url, str) or not any(
        same_reviewed_form(url, url.rstrip("/") + suffix)
        for suffix in ("/apply", "/application", "")
    ):
        # Greenhouse form URL is its original exact job URL.
        raise PacketError("Use the reviewed exact public HTTPS employer job URL")
    f = raw.get("fields")
    if not isinstance(f, dict) or set(f) != set(FIELD_NAMES) or any(
        not isinstance(f[name], str) for name in FIELD_NAMES
    ):
        raise PacketError("The packet must contain approved text fields only")
    if (
        raw.get("approved_fields_sha256") != _approved_fields_sha256(f)
        or not f["full_name"].strip()
        or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", f["email"]) is None
        or any(len(f[k]) > maximum for k, maximum in {
            "full_name": 160, "first_name": 160, "last_name": 160,
            "email": 254, "phone": 40, "location": 160, "linkedin": 350,
            "github": 350, "cover_letter": 10000,
        }.items())
        or raw.get("privacy") != {
            "approved_contact_only": True,
            "original_cv_included": False,
            "browser_form_fill_allowed_after_user_click": True,
            "employer_submit_allowed_without_new_approval": False,
        }
    ):
        raise PacketError("The packet does not meet reviewed contact/privacy rules")
    return raw


def _tidy(value: Any) -> str:
    """Normalize human labels without mistaking required markers for words."""
    # Real Lever form labels may contain Unicode required stars (✱).
    # Only the *label-to-safe-field* matcher uses this normalized text;
    # protected/sensitive metadata rejection still runs first.
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE).strip()



def _unsafe_metadata(row: dict[str, Any]) -> bool:
    values = [row.get(key, "") for key in (
        "label", "name", "id", "placeholder", "autocomplete",
    )]
    material = " ".join(str(v) for v in values)
    material = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", material)
    material = unicodedata.normalize("NFKC", material).lower()
    material = re.sub(r"[^\w]+", " ", material, flags=re.UNICODE)
    compact = unicodedata.normalize("NFKD", "".join(
        str(row.get(k) or "") for k in ("name", "id", "placeholder")
    ))
    compact = "".join(ch for ch in compact if not unicodedata.combining(ch))
    return bool(UNSAFE_METADATA.search(material) or UNSAFE_COMPACT.search(compact))


def _identify_field(row: dict[str, Any]) -> str | None:
    """Port of SmartPloy companion identifyField; fail closed on sensitive hints."""
    kind = _tidy(row.get("type"))
    if (
        _unsafe_metadata(row) or not row.get("inForm") or not row.get("visible")
        or row.get("disabled") or row.get("readonly") or row.get("hasValue")
        or kind not in SAFE_INPUT_TYPES
    ):
        return None
    auto = _tidy(row.get("autocomplete"))
    known_autos = {
        "given name": "first_name", "family name": "last_name",
        "email": "email", "tel": "phone", "name": "full_name",
        "address level2": "location",
    }
    if auto in known_autos:
        return known_autos[auto]
    label = _tidy(row.get("label") or row.get("placeholder"))
    attr = _tidy(row.get("name") or row.get("id"))
    if re.search(r"(company|employer|organization|organisation|referral|referee)", label+" "+attr):
        return None
    aliases = {
        "first_name": {"first name", "given name", "etunimi", "fornamn", "firstname"},
        "last_name": {"last name", "surname", "family name", "sukunimi", "efternamn", "lastname"},
        "email": {"email", "e mail", "email address", "sähköposti", "sähköpostiosoite", "e post"},
        "phone": {"phone", "phone number", "telephone", "mobile", "puhelin", "puhelinnumero", "telefon"},
        "linkedin": {"linkedin", "linkedin url", "linkedin profile", "linkedin profile url"},
        "github": {"github", "github url", "github profile", "github profile url"},
        "full_name": {"full name", "your name", "applicant name", "koko nimi", "nimi", "namn"},
        "location": {"current location", "location", "city", "sijainti", "paikkakunta", "ort"},
        "cover_letter": {"cover letter", "cover letter text", "motivation", "motivation letter",
                         "motivation message", "saatekirje", "personligt brev"},
        "additional_information": {"additional information", "additional comments", "lisätiedot"},
    }
    for key, names in aliases.items():
        if label in names or attr in names:
            return key
    return None


def plan_fields(rows: list[dict[str, Any]], packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Plan only visible, blank, uniquely identified ordinary application inputs."""
    if not isinstance(rows, list) or len(rows) > 250:
        raise PacketError("Employer form is too large or cannot be inspected safely")
    recognized = [_identify_field(row) for row in rows]
    dedicated_letter = "cover_letter" in recognized
    # 2026-11-06 real Lever Chromium OFFLINE fill: its Current location
    # text control cleared the value after a seemingly successful fill.
    # Lever city entries require applicant selection/validation; never
    # report those controls as completed ordinary text inputs.
    is_lever = urlsplit(str(packet.get("application_url", ""))).hostname in {
        "jobs.lever.co", "jobs.eu.lever.co",
    }
    candidates = []
    for row, key in zip(rows, recognized):
        if is_lever and key == "location":
            continue  # Manual location picker, not a verified text field.
        if key == "additional_information":
            key = None if dedicated_letter else "cover_letter"
        if not key:
            continue
        value = packet["fields"][key]
        if not value.strip() or row.get("maxLength", -1) not in (None, -1):
            maximum = row["maxLength"]
            if maximum is None or (maximum >= 0 and len(value) > maximum):
                continue
        if not value.strip():
            continue
        if not any(row.get(k) for k in ("id", "name")):
            # Plain labels alone are not a stable identity if React rerenders.
            continue
        candidates.append({"index": row["index"], "key": key, "row": row})
    # Duplicate fields and duplicate field identities are ambiguous; skip all.
    key_counts = {key: sum(1 for x in candidates if x["key"] == key)
                  for key in {x["key"] for x in candidates}}
    identity_counts = {
        (x["row"].get("id"), x["row"].get("name")):
        sum(1 for y in candidates if (
            y["row"].get("id"), y["row"].get("name")
        ) == (x["row"].get("id"), x["row"].get("name")))
        for x in candidates
    }
    return [x for x in candidates if key_counts[x["key"]] == 1 and
            identity_counts[(x["row"].get("id"), x["row"].get("name"))] == 1]


# Port the existing companion/upload.mjs chooseResumeField + validatePdf
# into the already reused Python Playwright executor. Never infer an upload
# grant from a matching name alone; there must be exactly one stable, visible
# and PDF-compatible resume input on the exact reviewed ATS form.
_CV_HINT = re.compile(
    r"(?:^|\s)(?:cv|resume|curriculum vitae|ansioluettelo|meritforteckning)(?:\s|$)"
)
_NOT_CV = re.compile(
    r"(?:^|\s)(?:cover letter|passport|photo|image|identity document|"
    r"transcript|certificate)(?:\s|$)"
)
_PDF_ACCEPT = frozenset({".pdf", "application/pdf", "application/*", "*/*"})


def choose_cv_attachment(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Adapted from SmartPloy Chrome companion chooseResumeField."""
    if not isinstance(rows, list) or len(rows) > 250:
        raise PacketError("Employer form is too large for reviewed attachment")
    candidates = []
    for row in rows:
        if row.get("type") != "file" or row.get("tag") != "input":
            continue
        original = " ".join(str(row.get(k) or "") for k in ("label", "name", "id"))
        normalized = unicodedata.normalize("NFKD", re.sub(
            r"([a-z])([A-Z])", r"\1 \2", original
        )).lower()
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        normalized = re.sub(r"[^\w]+", " ", normalized).strip()
        if not _CV_HINT.search(normalized):
            continue
        if (_NOT_CV.search(normalized) or not row.get("visible")
                or not row.get("inForm") or row.get("disabled")
                or row.get("readonly") or row.get("multiple")
                or row.get("hasValue")):
            return None  # Ambiguous/unsafe CV control: applicant must attach manually.
        accept = str(row.get("accept") or "").strip().lower()
        if accept and not any(part.strip() in _PDF_ACCEPT for part in accept.split(",")):
            return None
        if not (row.get("id") or row.get("name")):
            return None
        if type(row.get("index")) is not int or not 0 <= row["index"] < len(rows):
            return None
        candidates.append(row)
    if len(candidates) != 1:
        return None
    chosen = candidates[0]
    for other in rows:
        if (other is not chosen and other.get("type") == "file" and
                other.get("id") == chosen.get("id") and
                other.get("name") == chosen.get("name")):
            return None
    return chosen


def validate_reviewed_cv_pdf(data: bytes, packet: dict[str, Any]) -> None:
    """Reuse the exact original CV SHA and PDF rules, without disk writes."""
    validate_packet(packet)
    if (not isinstance(data, bytes) or len(data) != packet["cv_pdf_size"]
            or not 12 <= len(data) <= 2 * 1024 * 1024
            or not data.startswith(b"%PDF-")
            or b"%%EOF" not in data[-2048:]):
        raise PacketError("The local CV is not the exact reviewed PDF")
    if sha256(data).hexdigest() != packet["cv_pdf_sha256"]:
        raise PacketError("The CV PDF does not match the saved reviewed revision")


def attach_reviewed_cv_pdf(
    page: Any, packet: dict[str, Any], expected_rows: list[dict[str, Any]],
    reviewed_file_field: dict[str, Any], pdf: bytes, expected_url: str,
) -> dict[str, Any]:
    """One local FileList selection; employer may upload on input/change.

    Caller must reserve the one-use attachment attempt before invoking this.
    NEVER clicks Submit or claims an employer server accepted the upload.
    """
    validate_reviewed_cv_pdf(pdf, packet)
    if page.url != expected_url or not same_reviewed_form(
        packet["application_url"], page.url
    ):
        raise PacketError("The exact employer job changed before CV attachment")
    rows = inspect_page(page)
    identity = ("tag", "type", "id", "name", "label", "autocomplete", "accept", "multiple")
    if len(rows) != len(expected_rows) or any(
        any(old.get(key) != new.get(key) for key in identity)
        for old, new in zip(expected_rows, rows)
    ):
        raise PacketError("Employer form fields changed; attach the CV manually")
    current = choose_cv_attachment(rows)
    if (current is None
            or any(current.get(k) != reviewed_file_field.get(k)
                   for k in ("index", *identity))
            or current["type"] != "file"):
        raise PacketError("The reviewed résumé upload input is unavailable")
    for selector in _candidate_selectors(current):
        element = page.locator(selector)
        if element.count() != 1:
            continue
        # Verify the same input one final time, after all candidate queries.
        observed = element.first.evaluate(READ_FIELDS_JS.replace(
            "els => els.map((el, index) => {",
            "el => [el].map((el, index) => {",
        ))
        if len(observed) != 1 or any(
            observed[0].get(k) != current.get(k) for k in identity
        ) or (observed[0].get("hasValue") or not observed[0].get("visible")
              or not observed[0].get("inForm")):
            raise PacketError("Employer résumé field changed during review")
        # This actual Playwright call reuses ObumAI's live Chromium context,
        # and follows the existing Chrome companion's exact CV-PDF policy.
        # Does not store the CV to disk or submit the employer form.
        element.first.set_input_files({
            "name": "smartploy-reviewed-cv.pdf",
            "mimeType": "application/pdf",
            "buffer": pdf,
        }, timeout=5000)
        return {
            "attached_locally": True,
            "employer_upload_confirmed": False,
            "submitted": False,
        }
    raise PacketError("No unique CV input; attach the reviewed PDF manually")


def inspect_page(page: Any) -> list[dict[str, Any]]:
    return list(page.locator("input, textarea").evaluate_all(READ_FIELDS_JS))


def _candidate_selectors(field: dict[str, Any]) -> list[str]:
    """Adapted from ObumAI browser/fill.py: source selectors, never broad guesses."""
    selectors: list[str] = []
    tag = field["tag"]
    def css_quote(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
    if field.get("id"):
        selectors.append(f'{tag}[id="{css_quote(field["id"])}"]')
    if field.get("name"):
        selectors.append(f'{tag}[name="{css_quote(field["name"])}"]')
    return selectors


def _field_matches(locator: Any, field: dict[str, Any]) -> tuple[bool, str]:
    """Adapted from ObumAI: exactly one element, plus original DOM identity."""
    try:
        if locator.count() != 1:
            return False, "selector must match exactly one field"
        current = locator.first.evaluate(READ_FIELDS_JS.replace(
            "els => els.map((el, index) => {",
            "el => [el].map((el, index) => {",
        ))
        if len(current) != 1:
            return False, "element inspection failed"
        actual = current[0]
        for key in ("tag", "type", "id", "name", "label", "autocomplete", "accept", "multiple"):
            if actual.get(key) != field.get(key):
                return False, "employer field identity changed"
        if (
            not actual.get("visible") or not actual.get("inForm")
            or actual.get("disabled") or actual.get("readonly") or actual.get("hasValue")
            or _unsafe_metadata(actual) or actual["type"] not in SAFE_INPUT_TYPES
        ):
            return False, "target changed or is not an empty, safe text field"
        return True, "same reviewed empty field"
    except Exception:
        return False, "element could not be verified"


def _fill_one(page: Any, field: dict[str, Any], value: str) -> bool:
    """Adapted from ObumAI _fill_one: use Playwright.locator.fill, never click."""
    for selector in _candidate_selectors(field):
        locator = page.locator(selector)
        ok, _ = _field_matches(locator, field)
        if not ok:
            continue
        try:
            locator.first.fill(value, timeout=5000)
            # SP144: A successful Playwright fill call does NOT prove the
            # applicant's value survived a reactive employer form. Some
            # inputs clear or replace it in an async input/change handler.
            # Observe once after the UI settles; never retry a write.
            page.wait_for_timeout(150)
            if locator.count() != 1:
                return False
            inspected = locator.first.evaluate(READ_FIELDS_JS.replace(
                "els => els.map((el, index) => {",
                "el => [el].map((el, index) => {",
            ))
            if len(inspected) != 1:
                return False
            actual = inspected[0]
            identity = ("tag", "type", "id", "name", "label",
                        "autocomplete", "accept", "multiple")
            if (any(actual.get(k) != field.get(k) for k in identity)
                    or not actual.get("visible") or not actual.get("inForm")
                    or actual.get("disabled") or actual.get("readonly")
                    or _unsafe_metadata(actual)):
                return False
            return locator.first.input_value(timeout=2000) == value
        except Exception:
            return False  # No alternate retry after an uncertain form input.
    return False


def fill_reviewed_page(page: Any, packet: dict[str, Any], plan: list[dict[str, Any]],
                       expected_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Guard every write against URL/DOM changes. No submission/upload path."""
    validate_packet(packet)
    initial_url = page.url
    if not same_reviewed_form(packet["application_url"], initial_url):
        raise PacketError("Open the exact approved employer application form")
    completed = 0
    for item in plan:
        validate_packet(packet)
        if page.url != initial_url:
            break
        fresh = inspect_page(page)
        if len(fresh) != len(expected_rows) or any(
            any(fresh[i].get(k) != expected_rows[i].get(k)
                for k in ("tag", "type", "id", "name", "label", "autocomplete", "accept", "multiple"))
            for i in range(len(fresh))
        ):
            break  # Dynamic/replaced form requires a new applicant review.
        if _fill_one(page, item["row"], packet["fields"][item["key"]]):
            completed += 1
        else:
            break
    return {"filled": completed, "planned": len(plan),
            "stopped_on_change": completed != len(plan),
            "submitted": False, "uploaded": False}


# SP113: the browser observer itself is COPIED AT BUILD from the already
# tested MV3 Chrome companion popup.mjs `inspectReceipt` function.
# The helper runs that single pure read-only function in visible Chromium.
# Browser text, cookies and uploaded files are NEVER sent to SmartPloy here.
RECEIPT_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{3,63}\Z")


# SP114 uses EXACT existing browser-companion/logic.mjs +
# questions.mjs + page-questions.mjs, compiled from source into the ZIP.
# This Python adapter never guesses employer-specific answers or fills legal,
# salary, visa, EEO, consent or other protected application questions.
def inspect_reviewed_questions(
    page: Any, packet: dict[str, Any], original_script: str,
) -> dict[str, Any]:
    validate_packet(packet)
    if not same_reviewed_form(packet["application_url"], page.url):
        raise PacketError("Open only the exact employer application form")
    if not isinstance(original_script, str) or not 1000 <= len(original_script) <= 100_000:
        raise PacketError("The original Chrome question rules are unavailable")
    original_url = page.url
    try:
        result = page.evaluate(
            original_script,
            {"operation": "inspect", "inspectedUrl": original_url},
        )
    except Exception as exc:
        raise PacketError("Employer question inspection failed; complete manually") from exc
    if page.url != original_url or not same_reviewed_form(packet["application_url"], page.url):
        raise PacketError("The employer application changed during inspection")
    if not isinstance(result, dict) or result.get("status") != "inspected":
        raise PacketError("The employer questions cannot be safely inspected")
    questions, human = result.get("questions"), result.get("humanOnly")
    if not isinstance(questions, list) or not isinstance(human, list) or len(questions) > 12:
        raise PacketError("Employer questions exceed safe reviewed limits")
    for question in questions:
        if (
            not isinstance(question, dict)
            or set(question) != ({
                "index", "label", "type", "expected_id", "expected_name",
                "expected_placeholder", "expected_max_length", "max_answer_length",
            } | ({"options"} if question.get("type") == "select" else set()))
            or type(question["index"]) is not int or not 0 <= question["index"] < 250
            or question["type"] not in ("text", "textarea", "select")
            or not isinstance(question["label"], str) or not 1 <= len(question["label"]) <= 150
            or type(question["max_answer_length"]) is not int
            or not 2 <= question["max_answer_length"] <= 1500
            or not all(
                isinstance(question[key], str) and len(question[key]) <= 150
                for key in ("expected_id", "expected_name", "expected_placeholder")
            )
            or type(question["expected_max_length"]) is not int
            or (question.get("type") == "select" and (
                not isinstance(question.get("options"), list)
                or not 1 <= len(question["options"]) <= 24
                or any(
                    not isinstance(option, dict)
                    or set(option) != {"value", "label"}
                    or not isinstance(option["value"], str)
                    or not 1 <= len(option["value"]) <= 150
                    or not isinstance(option["label"], str)
                    or not 1 <= len(option["label"]) <= 150
                    for option in question["options"]
                )
                or len({o["value"] for o in question["options"]}) != len(question["options"])
            ))
        ):
            raise PacketError("Unsafe employer question plan returned")
    if any(not isinstance(label, str) or not 1 <= len(label) <= 150 for label in human):
        raise PacketError("Invalid manual employer question labels")
    if len(human) > 250:
        raise PacketError("Too many manual employer fields")
    return {"questions": questions, "human_only": human, "inspected_url": original_url}


def fill_reviewed_questions(
    page: Any, packet: dict[str, Any], original_script: str,
    reviewed_plan: dict[str, Any], answers: list[str],
) -> dict[str, Any]:
    validate_packet(packet)
    if (not isinstance(reviewed_plan, dict)
            or not isinstance(reviewed_plan.get("questions"), list)
            or not isinstance(reviewed_plan.get("inspected_url"), str)
            or not same_reviewed_form(packet["application_url"], page.url)
            or page.url != reviewed_plan["inspected_url"]
            or not isinstance(answers, list)
            or len(answers) != len(reviewed_plan["questions"])
            or len(answers) > 12):
        raise PacketError("Employer form or reviewed answers changed")
    if any(
        not isinstance(answer, str) or len(answer) > 1500 or
        any(ord(ch) < 32 and ch not in "\t\n\r" for ch in answer)
        for answer in answers
    ):
        raise PacketError("An employer answer is invalid")
    try:
        # The ORIGINAL Chrome companion validateReviewedAnswers and
        # fillReviewedAnswers enforce sensitive-field exclusion, exact
        # DOM identity, honest user-typed answers and single-page scope.
        result = page.evaluate(
            original_script,
            {
                "operation": "fill",
                "inspectedUrl": reviewed_plan["inspected_url"],
                "approvedUrl": packet["application_url"],
                "reviewedQuestions": reviewed_plan["questions"],
                "values": answers,
            },
        )
    except Exception as exc:
        raise PacketError(
            "Employer question fill outcome is uncertain; inspect manually"
        ) from exc
    if not isinstance(result, dict):
        raise PacketError("Employer question fill result is uncertain")
    status, filled = result.get("status"), result.get("filled")
    if (
        status not in ("filled_for_review", "partial_needs_review", "blocked")
        or type(filled) is not int or not 0 <= filled <= len(reviewed_plan["questions"])
    ):
        raise PacketError("Employer question fill returned an invalid result")
    return {
        "status": status,
        "filled": filled,
        "planned": len(reviewed_plan["questions"]),
        "submitted": False,
        "uploaded": False,
        # Do not echo question values, field IDs, profile data or the form.
    }


def observe_reviewed_receipt(
    page: Any, packet: dict[str, Any], receipt_script: str,
) -> dict[str, Any]:
    """Use existing Chrome receipt observer in ObumAI's visible Playwright page.

    Detection is only a BROWSER observation. This does not prove that a
    provider issued a receipt, update any application state, or submit.
    """
    validate_packet(packet)
    if (
        not isinstance(receipt_script, str) or
        len(receipt_script) < 1500 or len(receipt_script) > 100_000 or
        "inspectReceipt(expectedApplicationUrl)" not in receipt_script
    ):
        raise PacketError("Reviewed receipt inspector is unavailable")
    current_url = page.url
    try:
        outcome = page.evaluate(receipt_script, packet["application_url"])
    except Exception as exc:
        raise PacketError("Could not read the visible employer confirmation") from exc
    if not isinstance(outcome, dict):
        raise PacketError("Invalid employer confirmation observation")
    if not outcome.get("confirmed"):
        return {
            "confirmed": False,
            "explanation": "No sufficient reference-bearing employer confirmation was found. "
                           "Review the visible browser personally; do not retry submission.",
        }
    reference = outcome.get("reference")
    page_url = outcome.get("confirmation_page_url")
    digest = outcome.get("confirmation_page_sha256")
    if (
        not isinstance(reference, str) or not RECEIPT_REFERENCE.fullmatch(reference)
        or not isinstance(page_url, str) or not 14 <= len(page_url) <= 1500
        or not isinstance(digest, str) or not HEXDIGEST.fullmatch(digest)
    ):
        raise PacketError("Receipt lacks a bounded reference and page digest")
    # Never return query/fragment contents or employer page text to the
    # SmartPloy UI. The original JS already compares the exact ATS posting
    # identity and hashes a stable, reference-bearing page without Submit.
    try:
        current = urlsplit(current_url)
        safe = current.scheme + "://" + current.netloc + current.path
    except ValueError as exc:
        raise PacketError("Employer confirmation URL is invalid") from exc
    if page.url != current_url or page_url != safe:
        raise PacketError("Employer confirmation changed during observation")
    validate_packet(packet)
    return {
        "confirmed": True, "reference": reference,
        "confirmation_page_url": page_url,
        "confirmation_page_sha256": digest,
        "explanation": "Browser-visible reference observed; employer server not independently verified.",
    }


def start_visible_browser(playwright: Any, profile_dir: str) -> Any:
    """Reuse ObumAI live_session.py's persistent visible Chromium start."""
    return playwright.chromium.launch_persistent_context(
        user_data_dir=profile_dir, headless=False,
        viewport={"width": 1440, "height": 950},
        accept_downloads=False,
    )


def run_local() -> int:
    """Run entirely on the applicant's desktop in a temporary browser profile."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Interactive applicant terminal required; never pipe private packets into logs.")
        return 2
    try:
        packet = validate_packet(json.loads(getpass.getpass(
            "Paste your short-lived SmartPloy autofill packet (input hidden): "
        )))
        print("SmartPloy reviewed Playwright assistant. It will NEVER submit or upload files.")
        print("The employer page may transmit entered data immediately on field changes.")
        print("Install using: pip install playwright==1.55.0 && python -m playwright install chromium")
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

        # Reuses ObumAI's launch_persistent_context, scoped to a throwaway
        # private directory so credentials/cookies are not shared across jobs.
        with tempfile.TemporaryDirectory(prefix="smartploy-local-browser-") as profile:
            with sync_playwright() as playwright:
                context = start_visible_browser(playwright, profile)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(packet["application_url"], wait_until="domcontentloaded",
                              timeout=45000)
                    input("Navigate to this job's exact application form in the visible browser. "
                          "Complete login/MFA manually, then press Enter to inspect: ")
                    matches = [p for p in context.pages if
                               same_reviewed_form(packet["application_url"], p.url)]
                    if len(matches) != 1:
                        raise PacketError("No single exact supported employer application form is open")
                    page = matches[0]
                    if "captcha" in page.locator("body").inner_text(timeout=5000).lower():
                        raise PacketError("Security challenge detected; complete the form manually")
                    rows = inspect_page(page)
                    plan = plan_fields(rows, packet)
                    print(f"Found {len(rows)} controls; {len(plan)} safe, empty reviewed fields.")
                    for item in plan:
                        print(f"  - {item['key']}: {str(item['row'].get('label') or '')[:70]}")
                    print("Never enter passwords, identity, salary, immigration or legal answers here.")
                    if not plan:
                        print("No safe fields to fill. Complete this job manually.")
                        return 0
                    if input("Type FILL REVIEWED FIELDS to enter these values: ").strip() != (
                        "FILL REVIEWED FIELDS"
                    ):
                        print("Cancelled. No fields were filled.")
                        return 0
                    result = fill_reviewed_page(page, packet, plan, rows)
                    print(f"Filled {result['filled']} of {result['planned']} reviewed fields.")
                    if result["stopped_on_change"]:
                        print("Form changed or field became uncertain. Review remaining fields manually.")
                    print("No PDF uploaded and NO application submitted. "
                          "Inspect all values and complete the employer's form personally.")
                    input("Finish your work in this visible browser, then press Enter to close: ")
                    return 0
                finally:
                    context.close()
    except (PacketError, ValueError, json.JSONDecodeError) as exc:
        print("Assisted fill stopped: " + str(exc))
        return 2
    except (ImportError, OSError) as exc:
        print("Playwright/Chromium is unavailable. Follow INSTALL.txt: " + type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_local())

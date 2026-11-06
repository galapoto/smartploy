"""SP110 negative/recovery tests for the local ObumAI-derived Playwright helper.

No employer network or private applicant data. The same helper file is
allowlisted into the applicant download; tests do not import ObumAI runtime.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
from pathlib import Path
import re
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "browser-playwright/assistant.py"
PACKAGER = ROOT / "web/scripts/package_playwright_assistant.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assistant = load_module(SOURCE, "smartploy_sp110_local_assistant")


def packet(url="https://jobs.lever.co/example/position", now=None):
    now = now or datetime.now(timezone.utc)
    value = {
        "schema": "smartploy.browser_handoff.v2",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
        "application_url": url,
        "company": "FICTIONAL",
        "role_title": "Synthetic",
        "workspace_id": "kit-" + "a" * 30,
        "revision": 2, "document_sha256": "b" * 64,
        "cv_pdf_sha256": "c" * 64, "cv_pdf_size": 200,
        "fields": {
            "full_name": "Applicant Example", "first_name": "Applicant",
            "last_name": "Example", "email": "person@example.invalid",
            "phone": "", "location": "", "linkedin": "", "github": "",
            "cover_letter": "Synthetic, reviewed, factual cover letter.",
        },
        "privacy": {
            "approved_contact_only": True, "original_cv_included": False,
            "browser_form_fill_allowed_after_user_click": True,
            "employer_submit_allowed_without_new_approval": False,
        },
        "approved_fields_sha256": "d" * 64,
    }
    value["approved_fields_sha256"] = assistant._approved_fields_sha256(value["fields"])
    return value


def field(index, label, name, **overrides):
    row = {
        "index": index, "tag": "input", "type": "text",
        "id": name, "name": name, "placeholder": "", "label": label,
        "autocomplete": "", "required": False, "disabled": False,
        "readonly": False, "hasValue": False, "visible": True, "inForm": True,
        "maxLength": -1,
    }
    row.update(overrides)
    return row


def test_sp141_lever_location_picker_manual_after_real_offline_fill_proof():
    """Real Lever's city value was cleared despite a successful .fill().

    Do not transmit a false completion claim; preserve safe fields and keep
    ordinary static location fields on other employers independently usable.
    """
    p = packet("https://jobs.lever.co/example/position")
    p["fields"]["location"] = "Helsinki"
    rows = [
        field(0, "Full name✱", "name"),
        field(1, "Email✱", "email", type="email"),
        field(2, "Current location✱", "location", required=True),
    ]
    assert [x["key"] for x in assistant.plan_fields(rows, p)] == [
        "full_name", "email",
    ]
    p["application_url"] = "https://careers.example.org/jobs/reporter"
    assert [x["key"] for x in assistant.plan_fields(rows, p)] == [
        "full_name", "email", "location",
    ]


def test_sp140_real_lever_unicode_required_markers_map_only_safe_fields():
    """Based on 6 Nov read-only Chromium inspection of a live Lever form.

    No employer network, real applicant values, upload or submission occurs.
    The original strict mapper must recognize required-star labels while
    excluding legal/salary/company inputs even with misleading autocomplete.
    """
    candidate = packet()
    candidate["fields"]["phone"] = "+358401234567"
    candidate["fields"]["linkedin"] = "https://www.linkedin.com/in/example"
    controls = [
        field(0, "Full name✱", "name", required=True),
        field(1, "Email✱", "email", type="email", required=True),
        field(2, "Phone ✱", "phone", type="tel", required=True),
        field(3, "LinkedIn URL✱", "links[linkedin]", type="url", required=True),
        field(4, "Visa sponsorship✱", "sponsor", autocomplete="name"),
        field(5, "Salary expectation✱", "salary", autocomplete="name"),
        field(6, "Company name✱", "company", autocomplete="name"),
    ]
    plan = assistant.plan_fields(controls, candidate)
    assert [item["key"] for item in plan] == [
        "full_name", "email", "phone", "linkedin",
    ]
    assert [item["index"] for item in plan] == [0, 1, 2, 3]


@pytest.mark.parametrize(("source", "active", "expected"), [
    ("https://careers.example.org/jobs/junior-analyst",
     "https://careers.example.org/jobs/junior-analyst/apply", True),
    ("https://careers.example.org/jobs/junior-analyst",
     "https://careers.example.org/jobs/other", True),
    ("https://careers.example.org/jobs/junior-analyst",
     "https://sub.careers.example.org/jobs/junior-analyst/apply", False),
    ("https://careers.example.org/jobs/junior-analyst",
     "https://careers.example.invalid/jobs/junior-analyst", False),
    ("https://careers.example.org/jobs/junior-analyst",
     "https://127.0.0.1/private", False),
    ("https://careers.example.org/jobs/junior-analyst",
     "https://careers.example.org:8443/private", False),
    ("https://jobs.lever.co/a/role", "https://jobs.lever.co/a/role/apply", True),
    ("https://jobs.eu.lever.co/a/role/apply", "https://jobs.eu.lever.co/a/role/apply/", True),
    ("https://jobs.ashbyhq.com/a/role", "https://jobs.ashbyhq.com/a/role/application", True),
    ("https://boards.greenhouse.io/a/jobs/123", "https://job-boards.greenhouse.io/a/jobs/123", True),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com/apply/junior-analyst/m6rpoy", True),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com/apply/junior-analyst/m6rpoy/", True),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com/apply/junior-analyst/another", False),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com/apply/other-job/m6rpoy", False),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com/apply/junior-analyst/m6rpoy?source=duunitori", False),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com.evil.invalid/apply/junior-analyst/m6rpoy", False),
    ("https://ats.talentadore.com/apply/junior-analyst/m6rpoy", "https://ats.talentadore.com/apply/junior-analyst/m6rpoy/submit", False),
    ("https://jobs.lever.co/a/role", "https://jobs.lever.co/a/other/apply", False),
    ("https://jobs.lever.co/a/role", "https://evil.invalid/a/role/apply", False),
    ("https://jobs.lever.co/a/role", "https://jobs.eu.lever.co/a/role/apply", False),
    ("https://jobs.ashbyhq.com/a/role", "https://jobs.ashbyhq.com/b/role/application", False),
    ("https://jobs.ashbyhq.com/a/role", "https://jobs.ashbyhq.com/a/role/application?x=1", False),
    ("https://boards.greenhouse.io/a/jobs/123", "https://boards.greenhouse.io/a/jobs/124", False),
    ("https://boards.greenhouse.io/a/jobs/123", "https://boards.greenhouse.io/a/jobs/123#hash", False),
    ("https://jobs.lever.co/a/role", "https://jobs.lever.co/a/role", False),
    ("https://jobs.lever.co/a/role", "http://jobs.lever.co/a/role/apply", False),
    ("https://jobs.lever.co/a/role", "https://jobs.lever.co:8443/a/role/apply", False),
    ("https://jobs.lever.co/a/role", "https://user:secret@jobs.lever.co/a/role/apply", False),
])
def test_sp110_exact_reviewed_employer_form_url(source, active, expected):
    assert assistant.same_reviewed_form(source, active) is expected


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema="old"), lambda p: p.update(revision=1),
    lambda p: p.update(revision=True), lambda p: p.update(workspace_id="kit-invalid"),
    lambda p: p.update(cv_pdf_size=10), lambda p: p.update(document_sha256="123"),
    lambda p: p.update(application_url="https://localhost/jobs/123"),
    lambda p: p.update(application_url="http://jobs.lever.co/a/b"),
    lambda p: p.update(application_url="https://jobs.lever.co/a/b?track=yes"),
    lambda p: p["fields"].update(email="not-an-email"),
    lambda p: p["fields"].update(location="TAMPERED"),
    lambda p: p["fields"].update(password="secret"),
    lambda p: p["privacy"].update(employer_submit_allowed_without_new_approval=True),
    lambda p: p["privacy"].update(browser_form_fill_allowed_after_user_click=False),
    lambda p: p.update(expires_at="2020-10-01T00:00:00Z"),
    lambda p: p.update(issued_at="2099-11-01T00:00:00Z"),
])
def test_sp110_invalid_packet_denied_before_launch(mutation):
    value = packet()
    mutation(value)
    with pytest.raises(assistant.PacketError):
        assistant.validate_packet(value)


def test_sp110_valid_packet_matches_existing_production_browser_handoff_privacy():
    value = packet()
    assert assistant.validate_packet(value) is value
    assert assistant.validate_packet(packet("https://jobs.ashbyhq.com/a/id"))
    assert assistant.validate_packet(packet("https://boards.greenhouse.io/a/jobs/123"))
    assert assistant.validate_packet(packet("https://ats.talentadore.com/apply/junior-analyst/m6rpoy"))
    assert assistant.validate_packet(packet("https://careers.example.org/jobs/junior-analyst"))


def test_sp110_expiry_and_clock_boundaries():
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    value = packet(now=now)
    assert assistant.validate_packet(value, now=now + timedelta(minutes=14))
    with pytest.raises(assistant.PacketError):
        assistant.validate_packet(value, now=now + timedelta(minutes=15))
    value["expires_at"] = (now + timedelta(minutes=16)).isoformat()
    with pytest.raises(assistant.PacketError):
        assistant.validate_packet(value, now=now)


def test_sp110_field_plan_port_reuses_companion_safety_and_avoids_duplicates():
    rows = [
        field(0, "Full Name", "full_name"),
        field(1, "Email", "email", type="email", autocomplete="email"),
        field(2, "Email", "duplicate_email", type="email", autocomplete="email"),
        field(3, "Salary", "salary", type="text", autocomplete="email"),
        field(4, "Sähköposti", "applicant_email", type="hidden"),
        field(5, "Cover letter", "cover_letter", tag="textarea", type="textarea"),
        field(6, "Visa status", "visa_status", autocomplete="name"),
        field(7, "First Name", "first_name", hasValue=True),
        field(8, "Phone", "phone", visible=False),
        field(9, "Full Name", "full_name_2", disabled=True),
        field(10, "Gender", "gender", type="radio"),
        field(11, "Password", "pass", type="password"),
        field(12, "Additional Information", "other_info"),
    ]
    result = assistant.plan_fields(rows, packet())
    assert {(item["index"], item["key"]) for item in result} == {
        (0, "full_name"), (5, "cover_letter"),
    }


def test_sp110_no_label_or_unstable_identity_cannot_be_filled():
    p = packet()
    rows = [
        field(0, "Full Name", "", id=""),  # no stable form identity
        field(1, "First Name", "first", inForm=False),
        field(2, "Last Name", "last", maxLength=2),
        field(3, "Salary", "ordinary_contact", autocomplete="name"),
        field(4, "GDPR Consent", "email", type="email"),
    ]
    assert assistant.plan_fields(rows, p) == []


def test_sp110_ordinary_single_fields_fi_en_and_no_multiple_emails():
    p = packet()
    rows = [
        field(0, "Koko nimi", "candidate"),
        field(1, "Sähköpostiosoite", "candidate_mail", type="email"),
        field(2, "Saatekirje", "letter", tag="textarea", type="textarea"),
    ]
    assert [(x["index"], x["key"]) for x in assistant.plan_fields(rows, p)] == [
        (0, "full_name"), (1, "email"), (2, "cover_letter"),
    ]


class FakeLocator:
    """Minimal Playwright contract. Any submit/click/upload call would fail."""
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def count(self):
        return len(self._matches())

    def _matches(self):
        match = re.fullmatch(r'(input|textarea)\[(id|name)="([^"]+)"\]', self.selector)
        if not match:
            return []
        tag, attr, value = match.groups()
        return [row for row in self.page.rows if row["tag"] == tag and row[attr] == value]

    def evaluate_all(self, _source):
        assert self.selector == "input, textarea"
        return deepcopy(self.page.rows)

    def evaluate(self, _source):
        return deepcopy(self._matches())

    def fill(self, value, timeout):
        assert timeout == 5000
        (row,) = self._matches()
        assert not row["hasValue"]
        row["hasValue"] = True
        self.page.filled.append((row["name"], value))
        if self.page.on_fill:
            self.page.on_fill(self.page)


class FakePage:
    def __init__(self, rows, on_fill=None):
        self.url = "https://jobs.lever.co/example/position/apply"
        self.rows = rows
        self.filled = []
        self.on_fill = on_fill

    def locator(self, selector):
        return FakeLocator(self, selector)


def test_sp110_real_fill_function_reuses_obumai_without_submit_or_upload():
    p = packet()
    rows = [
        field(0, "Full Name", "fullname"),
        field(1, "Email", "mail", type="email"),
        field(2, "Gender", "gender", type="text"),
    ]
    page = FakePage(deepcopy(rows))
    plan = assistant.plan_fields(rows, p)
    result = assistant.fill_reviewed_page(page, p, plan, rows)
    assert result == {
        "filled": 2, "planned": 2, "stopped_on_change": False,
        "submitted": False, "uploaded": False,
    }
    assert page.filled == [
        ("fullname", "Applicant Example"), ("mail", "person@example.invalid"),
    ]
    assert not page.rows[2]["hasValue"]


@pytest.mark.parametrize("after_first", [
    lambda page: setattr(page, "url", "https://evil.invalid/steal"),
    lambda page: page.rows.append(field(2, "Unexpected", "newField")),
    lambda page: page.rows[1].update(label="Social Security Number"),
])
def test_sp110_changed_url_dom_or_metadata_stops_after_first_value(after_first):
    p = packet()
    rows = [field(0, "Full Name", "full"), field(1, "Email", "mail", type="email")]
    page = FakePage(deepcopy(rows), on_fill=after_first)
    plan = assistant.plan_fields(rows, p)
    result = assistant.fill_reviewed_page(page, p, plan, rows)
    assert result["filled"] == 1
    assert result["stopped_on_change"] is True
    assert page.filled == [("full", "Applicant Example")]


def test_sp110_stale_account_packet_cannot_fill():
    p = packet()
    p["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(assistant.PacketError):
        assistant.fill_reviewed_page(FakePage([]), p, [], [])


def test_sp110_archive_deterministic_allowlisted_and_checksum(tmp_path):
    packager = load_module(PACKAGER, "smartploy_sp110_packager")
    path1 = tmp_path / "one" / "smartploy-playwright-assistant.zip"
    path2 = tmp_path / "two" / "smartploy-playwright-assistant.zip"
    digest1 = packager.make_zip(path1)
    digest2 = packager.make_zip(path2)
    assert digest1 == digest2 == sha256(path1.read_bytes()).hexdigest()
    assert path1.read_bytes() == path2.read_bytes()
    assert path1.with_name(path1.name+".sha256").read_text() == (
        digest1 + "  " + path1.name + "\n"
    )
    with zipfile.ZipFile(path1) as archive:
        assert archive.namelist() == sorted((*packager.FILES, "SHA256SUMS.txt", "questions-review.js", "receipt-inspector.js"))
        assert archive.testzip() is None
        assert archive.read("assistant.py") == SOURCE.read_bytes()
        assert archive.read("bridge.py") == (ROOT / "browser-playwright/bridge.py").read_bytes()
        original = (ROOT / "browser-companion/popup.mjs").read_text()
        start = original.index("async function inspectReceipt(")
        end = original.index("\n/* Ashby has NO", start)
        original_inspector = original[start:end].strip()
        compiled = archive.read("receipt-inspector.js").decode("utf-8")
        assert original_inspector in compiled
        assert compiled == packager.reviewed_receipt_script().decode("utf-8")
        assert "return await inspectReceipt(expectedApplicationUrl)" in compiled
        assert "chrome.tabs" not in compiled
        assert "chrome.scripting.executeScript" not in compiled
        original_question = (ROOT / "browser-companion/questions.mjs").read_text()
        original_logic = (ROOT / "browser-companion/logic.mjs").read_text()
        original_fill = (ROOT / "browser-companion/page-questions.mjs").read_text()
        compiled_questions = archive.read("questions-review.js").decode("utf-8")
        assert compiled_questions == packager.reviewed_questions_script().decode("utf-8")
        assert original_question.replace(
            'import { identifyField } from "./logic.mjs";', ''
        ).replace("export ", "").strip() in compiled_questions
        assert original_logic.replace("export ", "").strip() in compiled_questions
        assert original_fill.replace("export ", "").strip() in compiled_questions
        assert "chrome.tabs" not in compiled_questions
        assert "chrome.scripting" not in compiled_questions


        assert b"pip install playwright==1.55.0" in archive.read("INSTALL.txt")
        assert not any("/" in name or ".." in name for name in archive.namelist())


def test_sp110_web_build_has_required_zip_origin_and_not_spa_fallback():
    package = (ROOT/"web/package.json").read_text()
    assert "scripts/package_playwright_assistant.py" in package
    docker = (ROOT/"web/Dockerfile").read_text()
    assert "COPY browser-playwright/ /workspace/browser-playwright/" in docker
    caddy = (ROOT/"deploy/personal/web.Caddyfile").read_text()
    assert "@playwright_assistant path /smartploy-playwright-assistant.zip " in caddy
    assert caddy.index("handle @playwright_assistant") < caddy.index("try_files {path} /index.html")
    studio = (ROOT/"web/src/ApplicationStudio.tsx").read_text()
    assert 'href="/smartploy-playwright-assistant.zip"' in studio
    assert "Playwright · local form assistant" in studio

"""SP110 real Python Playwright + Chromium synthetic employer form acceptance.

This fixture intercepts the entire employer request. No external employer,
credentials, CV, file upload or submit action is ever sent.
Run in browser CI after installing pinned Python Playwright + Chromium.
"""
from __future__ import annotations

from hashlib import sha256

import pytest
from test_playwright_assistant import assistant, packet

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


SAFE_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<form id="application">
  <label for="full">Full Name</label><input id="full" name="full_name" type="text">
  <label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email">
  <label for="salary">Salary</label><input id="salary" name="salary" type="text" autocomplete="email">
  <label for="letter">Cover Letter</label><textarea id="letter" name="cover_letter"></textarea>
  <label for="consent">GDPR Consent</label><input id="consent" type="checkbox">
  <input id="password" type="password" name="password">
  <button type="submit">Submit application</button>
</form>
<script>window.submissionCount=0;document.querySelector("form").addEventListener(
  "submit", e => { e.preventDefault(); window.submissionCount++; }
);</script>
</body></html>"""


def test_sp110_real_chromium_approved_fill_does_not_submit_upload_or_fill_sensitive():
    target = "https://jobs.lever.co/example/position/apply"
    p = packet("https://jobs.lever.co/example/position")
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=SAFE_HTML,
            ))
            page.goto(target, wait_until="domcontentloaded")
            assert assistant.same_reviewed_form(p["application_url"], page.url)
            rows = assistant.inspect_page(page)
            plan = assistant.plan_fields(rows, p)
            assert [item["key"] for item in plan] == ["full_name", "email", "cover_letter"]
            result = assistant.fill_reviewed_page(page, p, plan, rows)
            assert result == {"filled": 3, "planned": 3, "stopped_on_change": False,
                              "submitted": False, "uploaded": False}
            assert page.locator("#full").input_value() == "Applicant Example"
            assert page.locator("#email").input_value() == "person@example.invalid"
            assert page.locator("#letter").input_value() == p["fields"]["cover_letter"]
            assert page.locator("#salary").input_value() == ""
            assert page.locator("#password").input_value() == ""
            assert page.evaluate("window.submissionCount") == 0
        finally:
            browser.close()


def test_sp110_real_chromium_dynamic_form_change_stops_before_next_field():
    target = "https://jobs.lever.co/example/position/apply"
    p = packet("https://jobs.lever.co/example/position")
    html = SAFE_HTML.replace(
        "</body>",
        """<script>
        document.getElementById("full").addEventListener("input", () => {
          if (!document.querySelector("#injected")) {
            const input=document.createElement("input");
            input.id="injected";input.name="new_required";input.required=true;
            document.querySelector("form").append(input);
          }
        });
        </script></body>""",
    )
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=html,
            ))
            page.goto(target, wait_until="domcontentloaded")
            rows = assistant.inspect_page(page)
            plan = assistant.plan_fields(rows, p)
            assert len(plan) == 3
            result = assistant.fill_reviewed_page(page, p, plan, rows)
            assert result["filled"] == 1
            assert result["stopped_on_change"] is True
            assert page.locator("#email").input_value() == ""
            assert page.evaluate("window.submissionCount") == 0
        finally:
            browser.close()


def test_sp144_real_chromium_reactive_clear_is_not_counted_as_filled():
    """A synthetic employer input can erase text AFTER .fill() returns.

    A successful Playwright call is not proof of a completed application.
    No employer request, private CV, upload or submit is performed.
    """
    target = "https://jobs.lever.co/example/position/apply"
    p = packet("https://jobs.lever.co/example/position")
    html = """<!doctype html><html><body>
      <form id="application">
        <label for="person">Full name</label>
        <input id="person" name="full_name" type="text">
        <label for="contact">Email</label>
        <input id="contact" name="email" type="email">
        <button type="submit">Submit</button>
      </form>
      <script>
        window.submits = 0;
        document.querySelector("form").addEventListener("submit", e => {
          e.preventDefault(); window.submits++;
        });
        document.querySelector("#person").addEventListener("input", () => {
          setTimeout(() => {document.querySelector("#person").value = "";}, 20);
        });
      </script></body></html>"""
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=html,
            ))
            page.goto(target, wait_until="domcontentloaded")
            rows = assistant.inspect_page(page)
            plan = assistant.plan_fields(rows, p)
            assert [item["key"] for item in plan] == ["full_name", "email"]
            result = assistant.fill_reviewed_page(page, p, plan, rows)
            assert result == {
                "filled": 0, "planned": 2, "stopped_on_change": True,
                "submitted": False, "uploaded": False,
            }
            assert page.locator("#person").input_value() == ""
            assert page.locator("#contact").input_value() == ""
            assert page.evaluate("window.submits") == 0
        finally:
            browser.close()



SP112_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"
SP112_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<form id="job-application">
  <label for="full">Full Name</label><input id="full" name="full_name">
  <label for="resume">Résumé</label>
  <input type="file" id="resume" name="resume" accept="application/pdf">
  <label for="cover-file">Cover Letter</label>
  <input type="file" id="cover-file" name="cover_letter_file" accept="application/pdf">
  <button type="submit">Submit</button>
</form>
<script>
window.uploadEvents=0;window.submissions=0;
document.querySelector("#resume").addEventListener("change",()=>window.uploadEvents++);
document.querySelector("form").addEventListener("submit",e=>{
  e.preventDefault();window.submissions++;
});
</script></body></html>"""


def _reviewed_pdf_packet():
    p = packet("https://jobs.lever.co/example/position")
    p["cv_pdf_sha256"] = sha256(SP112_PDF).hexdigest()
    p["cv_pdf_size"] = len(SP112_PDF)
    return p


def test_sp112_real_chromium_attaches_only_exact_reviewed_pdf_without_submit():
    target = "https://jobs.lever.co/example/position/apply"
    p = _reviewed_pdf_packet()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            external_requests = []
            def respond(route):
                if route.request.url != target:
                    external_requests.append(route.request.url)
                    route.abort()
                else:
                    route.fulfill(status=200, content_type="text/html", body=SP112_HTML)
            page.route("**/*", respond)
            page.goto(target)
            rows = assistant.inspect_page(page)
            selected = assistant.choose_cv_attachment(rows)
            assert selected is not None
            assert selected["id"] == "resume"
            result = assistant.attach_reviewed_cv_pdf(
                page, p, rows, selected, SP112_PDF, target,
            )
            assert result == {
                "attached_locally": True,
                "employer_upload_confirmed": False,
                "submitted": False,
            }
            cv = page.locator("#resume").evaluate(
                "el => ({name:el.files[0]?.name,size:el.files[0]?.size})"
            )
            other = page.locator("#cover-file").evaluate("el => el.files.length")
            assert cv == {"name": "smartploy-reviewed-cv.pdf", "size": len(SP112_PDF)}
            assert other == 0
            assert page.evaluate("window.uploadEvents") == 1
            assert page.evaluate("window.submissions") == 0
            assert external_requests == []
        finally:
            browser.close()


def test_sp112_real_chromium_blocks_file_input_drift_and_bad_pdf():
    target = "https://jobs.lever.co/example/position/apply"
    p = _reviewed_pdf_packet()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=SP112_HTML,
            ))
            page.goto(target)
            original = assistant.inspect_page(page)
            chosen = assistant.choose_cv_attachment(original)
            assert chosen is not None
            with pytest.raises(assistant.PacketError):
                assistant.attach_reviewed_cv_pdf(
                    page, p, original, chosen, SP112_PDF + b"extra", target,
                )
            with pytest.raises(assistant.PacketError):
                assistant.attach_reviewed_cv_pdf(
                    page, p, original, chosen, b"%PDF-spoof\n%%EOF\n", target,
                )
            page.locator("#resume").evaluate(
                'el => {el.name="passport_upload";}',
            )
            with pytest.raises(assistant.PacketError):
                assistant.attach_reviewed_cv_pdf(
                    page, p, original, chosen, SP112_PDF, target,
                )
            assert page.locator("#resume").evaluate("el => el.files.length") == 0
            assert page.evaluate("window.submissions") == 0
        finally:
            browser.close()


def test_sp112_resume_selector_rejects_hidden_duplicate_and_nonpdf_fields():
    rows = [
        {"index": 0, "tag": "input", "type": "file",
         "id": "resume", "name": "resume", "label": "Resume",
         "accept": "image/jpeg", "visible": True, "inForm": True,
         "disabled": False, "readonly": False,
         "hasValue": False, "multiple": False},
    ]
    assert assistant.choose_cv_attachment(rows) is None
    rows[0]["accept"] = ".pdf"
    rows[0]["multiple"] = True
    assert assistant.choose_cv_attachment(rows) is None
    rows[0]["multiple"] = False
    rows[0]["visible"] = False
    assert assistant.choose_cv_attachment(rows) is None
    rows[0]["visible"] = True
    assert assistant.choose_cv_attachment(rows) == rows[0]
    rows.append({**rows[0], "index": 1, "id": "other", "name": "other"})
    assert assistant.choose_cv_attachment(rows) is None
    rows[1]["label"] = "Cover Letter"
    assert assistant.choose_cv_attachment(rows) == rows[0]


def test_sp129_real_chromium_reactive_cv_clear_is_not_reported_as_attached():
    """A provider may clear FileList during input/change; no invented success."""
    target = "https://jobs.lever.co/example/position/apply"
    p = _reviewed_pdf_packet()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=SP112_HTML,
            ))
            page.goto(target)
            # Simulated employer-side reactive reset; never touch Submit.
            page.locator("#resume").evaluate("""el => el.addEventListener(
                'change', () => { setTimeout(() => { el.value = ''; }, 0); }
            )""")
            rows = assistant.inspect_page(page)
            chosen = assistant.choose_cv_attachment(rows)
            assert chosen is not None
            with pytest.raises(assistant.PacketError, match="did not retain"):
                assistant.attach_reviewed_cv_pdf(
                    page, p, rows, chosen, SP112_PDF, target,
                )
            assert page.locator("#resume").evaluate("el => el.files.length") == 0
            assert page.evaluate("window.submissions") == 0
        finally:
            browser.close()

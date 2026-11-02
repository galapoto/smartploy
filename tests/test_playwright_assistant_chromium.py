"""SP110 real Python Playwright + Chromium synthetic employer form acceptance.

This fixture intercepts the entire employer request. No external employer,
credentials, CV, file upload or submit action is ever sent.
Run in browser CI after installing pinned Python Playwright + Chromium.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from test_playwright_assistant import assistant, packet


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

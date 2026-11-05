"""SP110 real Python Playwright + Chromium synthetic employer form acceptance.

This fixture intercepts the entire employer request. No external employer,
credentials, CV, file upload or submit action is ever sent.
Run in browser CI after installing pinned Python Playwright + Chromium.
"""
from __future__ import annotations

from hashlib import sha256

import pytest
from test_playwright_assistant import PACKAGER, assistant, load_module, packet

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


SP113_CONFIRMATION = """<!doctype html><html><body><main>
  <h1>Thank you for your application</h1>
  <p>Confirmation ID: SYNTHETIC-REF-1234</p>
</main></body></html>"""


def test_sp113_original_chrome_receipt_observer_in_real_playwright_chromium():
    # The source is extracted, not rewritten, from the actual Chrome companion.
    script = load_module(PACKAGER, "sp113_chrome_receipt").reviewed_receipt_script().decode()
    current = "https://jobs.lever.co/example/position/thanks?private=discard#token"
    p = packet("https://jobs.lever.co/example/position")
    external = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            def fulfill(route):
                if route.request.url != current.split("#", 1)[0]:
                    external.append(route.request.url)
                    route.abort()
                else:
                    route.fulfill(status=200, content_type="text/html",
                                  body=SP113_CONFIRMATION)
            page.route("**/*", fulfill)
            page.goto(current)
            observed = assistant.observe_reviewed_receipt(page, p, script)
            assert observed["confirmed"] is True
            assert observed["reference"] == "SYNTHETIC-REF-1234"
            assert observed["confirmation_page_url"] == (
                "https://jobs.lever.co/example/position/thanks"
            )
            assert len(observed["confirmation_page_sha256"]) == 64
            assert "discard" not in str(observed)
            assert "token" not in str(observed)
            assert external == []
        finally:
            browser.close()


@pytest.mark.parametrize("hosted_page,html", [
    ("https://jobs.lever.co/example/another-job/thanks", SP113_CONFIRMATION),
    ("https://jobs.lever.co/example/position/thanks",
     SP113_CONFIRMATION.replace("</body>",
         "<button>Submit application</button></body>")),
    ("https://jobs.lever.co/example/position/thanks",
     "<!doctype html><body><p>Thank you for your application.</p></body>"),
])
def test_sp113_chrome_receipt_observer_rejects_unrelated_or_incomplete_proof(
    hosted_page, html,
):
    script = load_module(PACKAGER, "sp113_chrome_receipt_negative").reviewed_receipt_script().decode()
    p = packet("https://jobs.lever.co/example/position")
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=html
            ))
            page.goto(hosted_page)
            observed = assistant.observe_reviewed_receipt(page, p, script)
            assert observed["confirmed"] is False
            assert "reference" not in observed
            assert "confirmation_page_sha256" not in observed
        finally:
            browser.close()


def test_sp113_observer_compiled_from_unmodified_original_chrome_source():
    from pathlib import Path
    owner = Path(__file__).resolve().parents[1] / "browser-companion/popup.mjs"
    original = owner.read_text(encoding="utf-8")
    begin = original.index("async function inspectReceipt(")
    end = original.index("\n/* Ashby has NO", begin)
    compiled = load_module(PACKAGER, "sp113_chrome_receipt_parity").reviewed_receipt_script().decode()
    assert original[begin:end].strip() in compiled
    assert "chrome.runtime" not in compiled
    assert "chrome.tabs" not in compiled
    assert compiled.count("async function inspectReceipt(") == 1


SP114_FORM = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<form id="application">
  <label for="name">Full Name</label>
  <input id="name" name="full_name" type="text" value="Applicant Example" required>
  <label for="project">Describe a project you led</label>
  <textarea id="project" name="project_example" required></textarea>
  <label for="tools">Which data tools have you used?</label>
  <input id="tools" name="tools_experience" type="text" required maxlength="150">
  <label for="visa">Do you need visa sponsorship?</label>
  <input id="visa" name="visaStatus" type="text" required>
  <label for="salary">Salary expectation</label>
  <input id="salary" name="salaryExpectation" type="text" required>
  <label for="consent">I agree to privacy terms</label>
  <input id="consent" name="GDPRConsent" type="checkbox" required>
  <button id="submit" type="submit">Submit application</button>
</form>
<script>
window.inputEvents = 0; window.submits = 0;
document.querySelector("form").addEventListener("input",() => window.inputEvents++);
document.querySelector("form").addEventListener("submit",e=>{
  e.preventDefault(); window.submits++;
});
</script></body></html>"""


def test_sp114_real_chromium_original_question_planner_human_first_and_one_fill():
    p = packet("https://jobs.lever.co/example/position")
    target = p["application_url"] + "/apply"
    script = load_module(
        PACKAGER, "sp114_chrome_question_policy"
    ).reviewed_questions_script().decode()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            traffic = []
            def route_request(route):
                if route.request.method != "GET" or route.request.url != target:
                    traffic.append(route.request.url)
                    route.abort()
                else:
                    route.fulfill(
                        status=200, content_type="text/html", body=SP114_FORM,
                    )
            page.route("**/*", route_request)
            page.goto(target)
            reviewed = assistant.inspect_reviewed_questions(page, p, script)
            labels = [item["label"] for item in reviewed["questions"]]
            assert labels == [
                "Describe a project you led",
                "Which data tools have you used?",
            ]
            assert "Do you need visa sponsorship?" in reviewed["human_only"]
            assert "Salary expectation" in reviewed["human_only"]
            assert "I agree to privacy terms" in reviewed["human_only"]
            assert all(item["max_answer_length"] <= 1500 for item in reviewed["questions"])
            result = assistant.fill_reviewed_questions(
                page, p, script, reviewed,
                ["Led a verified monitoring dashboard project.",
                 "Used Python, SQL and Power BI on a verified task."],
            )
            assert result == {
                "status": "filled_for_review",
                "filled": 2, "planned": 2,
                "submitted": False, "uploaded": False,
            }
            assert page.locator("#project").input_value().startswith("Led a")
            assert page.locator("#tools").input_value().startswith("Used Python")
            assert page.locator("#visa").input_value() == ""
            assert page.locator("#salary").input_value() == ""
            assert page.locator("#consent").is_checked() is False
            assert page.evaluate("window.inputEvents") == 2
            assert page.evaluate("window.submits") == 0
            assert traffic == []
        finally:
            browser.close()


def test_sp114_chromium_blocks_changed_question_identity_without_any_fill():
    p = packet("https://jobs.lever.co/example/position")
    url = p["application_url"] + "/apply"
    script = load_module(PACKAGER, "sp114_questions_drift").reviewed_questions_script().decode()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=SP114_FORM,
            ))
            page.goto(url)
            reviewed = assistant.inspect_reviewed_questions(page, p, script)
            page.locator("#project").evaluate('el => {el.name = "salaryExpected";}')
            verdict = assistant.fill_reviewed_questions(
                page, p, script, reviewed,
                ["A truthful verified project", "A truthful verified toolset"],
            )
            assert verdict["status"] == "blocked"
            assert verdict["filled"] == 0
            assert page.locator("#project").input_value() == ""
            assert page.locator("#tools").input_value() == ""
            assert page.evaluate("window.submits") == 0
        finally:
            browser.close()


def test_sp114_chromium_denies_question_fill_after_other_employer_job():
    p = packet("https://jobs.lever.co/example/position")
    script = load_module(PACKAGER, "sp114_questions_wrong_job").reviewed_questions_script().decode()
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=SP114_FORM,
            ))
            page.goto("https://jobs.lever.co/example/another-job/apply")
            with pytest.raises(assistant.PacketError):
                assistant.inspect_reviewed_questions(page, p, script)
            assert page.locator("#project").input_value() == ""
            assert page.evaluate("window.submits") == 0
        finally:
            browser.close()

# SP118: This page is synthetic, intercepted inside local Chromium; no real
# HOK-Elanto job site, applicant identity or employer submission is contacted.
SP118_TALENTADORE_URL = "https://ats.talentadore.com/apply/junior-analyst/m6rpoy"
SP118_TALENTADORE_HTML = """<!doctype html><html lang="fi"><head>
<meta charset="utf-8"><title>Junior Analyst | HOK-Elanto — synthetic form</title>
</head><body><h1>Junior Analyst · HOK-Elanto (synthetic test)</h1>
<form id="application-form">
<label for="given">Etunimi</label><input id="given" name="first_name" autocomplete="given-name" required>
<label for="family">Sukunimi</label><input id="family" name="last_name" autocomplete="family-name" required>
<label for="email">Sähköposti</label><input id="email" name="email" type="email" autocomplete="email" required>
<label for="letter">Saatekirje</label><textarea id="letter" name="cover_letter"></textarea>
<label for="resume">Ansioluettelo (PDF)</label>
<input id="resume" name="cv" type="file" accept="application/pdf" required>
<label for="wage">Palkkatoive</label><input id="wage" name="salaryExpectation" type="text">
<label for="visa">Työlupa</label><input id="visa" name="visaStatus" type="text">
<label for="gdpr">Tietosuojaseloste</label><input id="gdpr" name="gdprConsent" type="checkbox" required>
<button type="submit">Lähetä hakemus</button></form>
<script>
window.submits=0;window.fileChanges=0;
document.querySelector("form").addEventListener("submit",event=>{
  event.preventDefault();window.submits++;
});
document.querySelector("#resume").addEventListener("change",()=>window.fileChanges++);
</script></body></html>"""


def test_sp118_talentadore_reviewed_chromium_autofill_and_exact_cv_no_submit():
    """Applicant-controlled demo on the EXACT public job URL but synthetic DOM."""
    p = packet(SP118_TALENTADORE_URL)
    p["cv_pdf_sha256"] = sha256(SP112_PDF).hexdigest()
    p["cv_pdf_size"] = len(SP112_PDF)
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            external = []
            def route_synthetic(route):
                if route.request.url != SP118_TALENTADORE_URL:
                    external.append(route.request.url)
                    route.abort()
                else:
                    route.fulfill(status=200, content_type="text/html",
                                  body=SP118_TALENTADORE_HTML)
            page.route("**/*", route_synthetic)
            page.goto(SP118_TALENTADORE_URL, wait_until="domcontentloaded")
            assert assistant.same_reviewed_form(p["application_url"], page.url)
            rows = assistant.inspect_page(page)
            plan = assistant.plan_fields(rows, p)
            assert [item["key"] for item in plan] == [
                "first_name", "last_name", "email", "cover_letter",
            ]
            outcome = assistant.fill_reviewed_page(page, p, plan, rows)
            assert outcome == {
                "filled": 4, "planned": 4,
                "stopped_on_change": False, "submitted": False, "uploaded": False,
            }
            assert page.locator("#given").input_value() == "Applicant"
            assert page.locator("#family").input_value() == "Example"
            assert page.locator("#email").input_value() == "person@example.invalid"
            assert page.locator("#letter").input_value() == p["fields"]["cover_letter"]
            # Salary, work authorization and legal consent NEVER guessed.
            assert page.locator("#wage").input_value() == ""
            assert page.locator("#visa").input_value() == ""
            assert page.locator("#gdpr").is_checked() is False
            assert page.evaluate("window.submits") == 0
            file_field = assistant.choose_cv_attachment(rows)
            assert file_field is not None and file_field["name"] == "cv"
            result = assistant.attach_reviewed_cv_pdf(
                page, p, rows, file_field, SP112_PDF, SP118_TALENTADORE_URL,
            )
            assert result == {
                "attached_locally": True, "employer_upload_confirmed": False,
                "submitted": False,
            }
            assert page.evaluate("window.fileChanges") == 1
            assert page.evaluate("window.submits") == 0
            assert external == []
            # Public CI artifact contains ONLY fictional applicant and fake ATS
            # fixture, not the user's private CV/profile or real employer HTML.
            from pathlib import Path
            screenshot = Path(__file__).resolve().parents[1] / "web" / "browser-evidence" / "sp118-talentadore-synthetic.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
        finally:
            browser.close()


def test_sp118_talentadore_dynamic_question_change_stops_autofill_without_submit():
    p = packet(SP118_TALENTADORE_URL)
    html = SP118_TALENTADORE_HTML.replace(
        "</body>",
        """<script>document.querySelector("#given").addEventListener("input",()=>{
          const item=document.createElement("input");
          item.id="conditional";item.name="conditional_question";
          document.querySelector("form").append(item);
        });</script></body>""",
    )
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=html,
            ))
            page.goto(SP118_TALENTADORE_URL)
            rows = assistant.inspect_page(page)
            planned = assistant.plan_fields(rows, p)
            result = assistant.fill_reviewed_page(page, p, planned, rows)
            assert result["filled"] == 1
            assert result["stopped_on_change"] is True
            assert page.locator("#family").input_value() == ""
            assert page.evaluate("window.submits") == 0
        finally:
            browser.close()


def test_sp120_real_chromium_generic_employer_form_fills_reviewed_fields_only():
    """Actual Playwright/Chromium DOM with every network response synthetic."""
    p = packet("https://careers.example.org/jobs/junior-analyst")
    form_url = "https://careers.example.org/jobs/junior-analyst/apply"
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=SAFE_HTML,
            ))
            page.goto(form_url, wait_until="domcontentloaded")
            assert assistant.same_reviewed_form(p["application_url"], page.url)
            rows = assistant.inspect_page(page)
            plan = assistant.plan_fields(rows, p)
            assert [item["key"] for item in plan] == ["full_name", "email", "cover_letter"]
            result = assistant.fill_reviewed_page(page, p, plan, rows)
            assert result["filled"] == 3
            assert result["submitted"] is False
            assert result["uploaded"] is False
            assert page.locator("#full").input_value() == "Applicant Example"
            assert page.locator("#email").input_value() == "person@example.invalid"
            assert page.locator("#salary").input_value() == ""
            assert page.locator("#consent").is_checked() is False
            assert page.evaluate("window.submissionCount") == 0
            # Even with identical field IDs, a cross-origin redirect cannot fill.
            page.goto("https://other-career.example.org/job", wait_until="domcontentloaded")
            assert assistant.same_reviewed_form(p["application_url"], page.url) is False
            with pytest.raises(assistant.PacketError):
                assistant.fill_reviewed_page(page, p, plan, rows)
        finally:
            browser.close()

"""SP111 local Playwright pairing security and offline HTTP contract.

No real browser, employer network, credentials or user data is used here.
The Python Chromium acceptance in test_playwright_assistant_chromium.py
separately tests the actual ObumAI-derived DOM filling executor.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from http.client import HTTPConnection
from http.server import HTTPServer
import importlib.util
import json
from pathlib import Path
import sys
from threading import Thread

import pytest

from test_playwright_assistant import FakePage, assistant, field, packet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "browser-playwright"))
SPEC = importlib.util.spec_from_file_location(
    "smartploy_sp111_bridge", ROOT / "browser-playwright/bridge.py"
)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

SAFE_ORIGIN = "https://smartploy.komplyint.fi"
PAIR_CODE = "this-is-a-synthetic-pairing-code-not-a-secret"


class FakeActor:
    instances = []

    def __init__(self, value):
        self.packet = value
        self.page = FakePage([
            field(0, "Full Name", "full"),
            field(1, "Email", "mail", type="email", autocomplete="email"),
            field(2, "Salary", "salary", autocomplete="email"),
            field(3, "Cover Letter", "letter", tag="textarea", type="textarea"),
            field(4, "Visa Status", "visa", autocomplete="name"),
            field(5, "Password", "password", type="password"),
            field(6, "Résumé", "resume_file", type="file", accept="application/pdf"),
        ])
        self.closed = False
        self.attachments = []
        self.receipt_finding = {"confirmed": False}
        self.reviewed_answers = []
        self.instances.append(self)

    def inspect(self, p):
        assert p is self.packet
        rows = deepcopy(self.page.rows)
        return self.page, rows, assistant.plan_fields(rows, p)

    def fill(self, page, p, plan, rows):
        assert page is self.page
        return assistant.fill_reviewed_page(page, p, plan, rows)

    def attach(self, page, p, rows, file_field, raw_pdf, expected_url):
        assistant.validate_reviewed_cv_pdf(raw_pdf, p)
        assert file_field["type"] == "file"
        assert page.url == expected_url
        self.attachments.append((file_field["name"], sha256(raw_pdf).hexdigest()))
        return {"attached_locally": True, "employer_upload_confirmed": False,
                "submitted": False}

    def questions(self, p):
        assert p is self.packet
        return self.page, {
            "questions": [
                {
                    "index": 7, "label": "Describe a project you led",
                    "type": "textarea", "expected_id": "project",
                    "expected_name": "project_example",
                    "expected_placeholder": "", "expected_max_length": -1,
                    "max_answer_length": 1500,
                },
            ],
            "human_only": [
                "Visa sponsorship", "Salary expectation", "GDPR consent",
            ],
            "inspected_url": self.page.url,
        }

    def fill_questions(self, page, p, plan, answers):
        assert page is self.page and p is self.packet
        assert plan["questions"][0]["label"] == "Describe a project you led"
        assert len(answers) == 1 and answers[0].strip()
        self.reviewed_answers.append(answers[0])
        return {
            "status": "filled_for_review",
            "filled": 1, "planned": 1, "submitted": False, "uploaded": False,
        }

    def observe(self, p):
        assert p is self.packet
        return self.receipt_finding

    def close(self):
        self.closed = True


def state():
    FakeActor.instances.clear()
    return bridge.BridgeState(pairing_code=PAIR_CODE, actor_factory=FakeActor)


def test_sp111_pairing_and_single_reviewed_fill_no_submit_or_upload():
    current = state()
    with pytest.raises(bridge.BridgeError) as denied:
        current.inspect()
    assert denied.value.status == 409
    with pytest.raises(bridge.BridgeError):
        current.prepare("wrong", packet())
    assert not FakeActor.instances
    opened = current.prepare(PAIR_CODE, packet())
    assert opened["stage"] == "opened"
    assert opened["submitted"] is False and opened["uploaded"] is False
    assert "fields" not in opened and "cv_text" not in opened
    assert len(opened["token"]) >= 40
    assert current.pairing_code == ""
    current.authenticate("Bearer " + opened["token"])
    with pytest.raises(bridge.BridgeError):
        current.authenticate("Bearer " + "x" * 43)
    with pytest.raises(bridge.BridgeError):
        current.prepare(PAIR_CODE, packet())
    view = current.inspect()
    assert view["stage"] == "inspected"
    assert [x["key"] for x in view["approved_fields"]] == [
        "full_name", "email", "cover_letter"
    ]
    assert all("value" not in item for item in view["approved_fields"])
    with pytest.raises(bridge.BridgeError):
        current.fill("incorrect", "FILL REVIEWED FIELDS")
    with pytest.raises(bridge.BridgeError):
        current.fill(view["plan_id"], "SUBMIT")
    assert FakeActor.instances[0].page.filled == []
    done = current.fill(view["plan_id"], "FILL REVIEWED FIELDS")
    assert done == {
        "ok": True, "stage": "filled", "filled": 3, "planned": 3,
        "stopped_on_change": False, "submitted": False, "uploaded": False,
    }
    assert FakeActor.instances[0].page.filled == [
        ("full", "Applicant Example"),
        ("mail", "person@example.invalid"),
        ("letter", "Synthetic, reviewed, factual cover letter."),
    ]
    with pytest.raises(bridge.BridgeError) as reused:
        current.fill(view["plan_id"], "FILL REVIEWED FIELDS")
    assert reused.value.status == 409
    stopped = current.stop()
    assert stopped["stage"] == "stopped"
    assert FakeActor.instances[0].closed is True
    with pytest.raises(bridge.BridgeError):
        current.authenticate("Bearer " + opened["token"])
    with pytest.raises(bridge.BridgeError):
        current.prepare(PAIR_CODE, packet())


def test_sp111_stale_or_forged_packet_and_code_lockout():
    current = state()
    bad = packet()
    bad["fields"]["email"] = "attacker@example.invalid"  # original hash mismatches
    with pytest.raises(bridge.BridgeError) as blocked:
        current.prepare(PAIR_CODE, bad)
    assert blocked.value.status == 422
    assert not FakeActor.instances

    current = state()
    for _ in range(bridge.MAX_BAD_CODES):
        with pytest.raises(bridge.BridgeError):
            current.prepare("wrong-code", packet())
    with pytest.raises(bridge.BridgeError) as locked:
        current.prepare(PAIR_CODE, packet())
    assert locked.value.status == 403
    assert not FakeActor.instances


def test_sp111_expired_packet_rechecked_before_inspection_and_fill():
    current = state()
    _opened = current.prepare(PAIR_CODE, packet())
    current.packet["expires_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(bridge.BridgeError) as expired:
        current.inspect()
    assert expired.value.status == 410
    current.stop()


def test_sp111_dynamic_employer_form_blocks_further_actions_without_retry():
    current = state()
    current.prepare(PAIR_CODE, packet())
    view = current.inspect()
    actor = FakeActor.instances[-1]

    def mutate_form(page):
        page.rows.append(field(99, "Unexpected new requirement", "newField"))

    actor.page.on_fill = mutate_form
    result = current.fill(view["plan_id"], "FILL REVIEWED FIELDS")
    assert result["filled"] == 1
    assert result["stopped_on_change"] is True
    with pytest.raises(bridge.BridgeError):
        current.fill(view["plan_id"], "FILL REVIEWED FIELDS")
    current.stop()


@contextmanager
def fake_local_http_server(current):
    server = HTTPServer(("127.0.0.1", 0), bridge.make_handler(current))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        current.stop()


def http_request(port, path, payload=None, *, method="POST",
                 origin=SAFE_ORIGIN, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(payload or {}).encode("utf-8")
    request_headers = {"Origin": origin, "Content-Type": "application/json"}
    request_headers.update(headers or {})
    conn.request(method, path, body=data if method == "POST" else None,
                 headers=request_headers)
    result = conn.getresponse()
    body = result.read()
    answer = {}
    if body:
        answer = json.loads(body)
    meta = dict(result.getheaders())
    status = result.status
    conn.close()
    return status, meta, answer


def test_sp111_http_rejects_untrusted_origin_wrong_host_and_missing_token():
    current = state()
    with fake_local_http_server(current) as port:
        code = {"pairing_code": PAIR_CODE, "packet": packet()}
        status, headers, _ = http_request(port, "/v1/prepare", code,
                                          origin="https://evil.invalid")
        assert status == 403
        assert "Access-Control-Allow-Origin" not in headers
        status, headers, _ = http_request(port, "/v1/prepare", code,
                                          headers={"Host": "evil.invalid"})
        assert status == 403
        assert "Access-Control-Allow-Origin" not in headers
        status, _, _ = http_request(port, "/v1/inspect")
        assert status == 403
        assert not FakeActor.instances


def test_sp111_http_pair_inspect_fill_stop_and_no_credential_leakage():
    current = state()
    with fake_local_http_server(current) as port:
        body = {"pairing_code": PAIR_CODE, "packet": packet()}
        status, headers, opened = http_request(port, "/v1/prepare", body)
        assert status == 200
        assert headers["Access-Control-Allow-Origin"] == SAFE_ORIGIN
        assert headers["Cache-Control"] == "no-store"
        assert "pairing_code" not in opened
        assert "fields" not in opened
        token = opened["token"]
        auth = {"Authorization": "Bearer " + token}
        status, _, plan = http_request(port, "/v1/inspect", headers=auth)
        assert status == 200
        assert len(plan["approved_fields"]) == 3
        status, _, done = http_request(port, "/v1/fill", {
            "plan_id": plan["plan_id"], "confirmation": "FILL REVIEWED FIELDS",
        }, headers=auth)
        assert status == 200
        assert done["filled"] == 3
        assert done["submitted"] is False
        status, _, _ = http_request(port, "/v1/fill", {
            "plan_id": plan["plan_id"], "confirmation": "FILL REVIEWED FIELDS",
        }, headers=auth)
        assert status == 409
        status, _, stopped = http_request(port, "/v1/stop", headers=auth)
        assert status == 200
        assert stopped["stage"] == "stopped"
        status, _, _ = http_request(port, "/v1/inspect", headers=auth)
        assert status == 403
        assert FakeActor.instances[0].closed is True


def test_sp111_cors_preflight_private_network_only_on_exact_approved_origin():
    current = state()
    with fake_local_http_server(current) as port:
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("OPTIONS", "/v1/prepare", headers={
            "Origin": SAFE_ORIGIN, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
            "Access-Control-Request-Headers": "content-type",
        })
        response = conn.getresponse()
        response.read()
        assert response.status == 204
        assert response.getheader("Access-Control-Allow-Origin") == SAFE_ORIGIN
        assert response.getheader("Access-Control-Allow-Private-Network") == "true"
        assert "Authorization" in response.getheader("Access-Control-Allow-Headers")
        conn.close()

        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("OPTIONS", "/v1/prepare", headers={
            "Origin": "https://evil.invalid",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
        })
        response = conn.getresponse()
        response.read()
        assert response.status == 403
        assert response.getheader("Access-Control-Allow-Origin") is None
        assert response.getheader("Access-Control-Allow-Private-Network") is None
        conn.close()


def test_sp111_readonly_endpoint_and_unknown_methods_never_leak_data():
    current = state()
    with fake_local_http_server(current) as port:
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/v1/prepare", headers={"Origin": SAFE_ORIGIN})
        result = conn.getresponse()
        data = result.read().decode()
        assert result.status == 405
        assert PAIR_CODE not in data
        conn.close()
        status, _, _ = http_request(port, "/v1/submit")
        assert status == 404


def test_sp111_production_csp_permits_exact_loopback_bridge_only():
    caddy = (ROOT / "deploy/personal/web.Caddyfile").read_text(encoding="utf-8")
    assert "connect-src 'self' http://127.0.0.1:48741;" in caddy
    assert "connect-src *" not in caddy
    assert "http://localhost:*" not in caddy
    assert "http://192.168." not in caddy


# SP112: reuse real v2 packet CV digest, not arbitrary user file bytes.
FAKE_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


def reviewed_pdf_packet():
    p = packet()
    p["cv_pdf_sha256"] = sha256(FAKE_PDF).hexdigest()
    p["cv_pdf_size"] = len(FAKE_PDF)
    return p


def test_sp112_exact_pdf_local_attachment_once_and_never_submitted():
    current = state()
    current.prepare(PAIR_CODE, reviewed_pdf_packet())
    inspected = current.inspect()
    attachment = inspected["cv_attachment"]
    assert attachment["available"] is True
    assert attachment["label"] == "Résumé"
    with pytest.raises(bridge.BridgeError) as wrong:
        current.attach("invalid-id", "ATTACH REVIEWED CV", FAKE_PDF)
    assert wrong.value.status == 403
    with pytest.raises(bridge.BridgeError):
        current.attach(attachment["attach_id"], "SUBMIT", FAKE_PDF)
    with pytest.raises(bridge.BridgeError) as mismatch:
        current.attach(attachment["attach_id"], "ATTACH REVIEWED CV", b"%PDF-wrong\n%%EOF")
    assert mismatch.value.status == 422
    assert FakeActor.instances[0].attachments == []
    result = current.attach(attachment["attach_id"], "ATTACH REVIEWED CV", FAKE_PDF)
    assert result == {
        "ok": True, "stage": "attached", "attached_locally": True,
        "employer_upload_confirmed": False,
        "submitted": False, "uploaded": True,
    }
    assert FakeActor.instances[0].attachments == [
        ("resume_file", sha256(FAKE_PDF).hexdigest()),
    ]
    with pytest.raises(bridge.BridgeError) as retry:
        current.attach(attachment["attach_id"], "ATTACH REVIEWED CV", FAKE_PDF)
    assert retry.value.status == 409
    current.stop()


def test_sp112_pdf_attachment_requires_inspection_and_fresh_original_hash():
    current = state()
    current.prepare(PAIR_CODE, reviewed_pdf_packet())
    with pytest.raises(bridge.BridgeError):
        current.attach("no-inspection", "ATTACH REVIEWED CV", FAKE_PDF)
    inspection = current.inspect()
    current.packet["expires_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(bridge.BridgeError) as stale:
        current.attach(inspection["cv_attachment"]["attach_id"], "ATTACH REVIEWED CV", FAKE_PDF)
    assert stale.value.status == 410
    current.stop()


def test_sp112_attachment_one_attempt_burned_after_uncertain_browser_failure():
    class UncertainActor(FakeActor):
        def attach(self, *_args):
            raise RuntimeError("synthetic employer event uncertain")
    current = bridge.BridgeState(pairing_code=PAIR_CODE, actor_factory=UncertainActor)
    current.prepare(PAIR_CODE, reviewed_pdf_packet())
    inspected = current.inspect()
    aid = inspected["cv_attachment"]["attach_id"]
    with pytest.raises(bridge.BridgeError) as uncertain:
        current.attach(aid, "ATTACH REVIEWED CV", FAKE_PDF)
    assert uncertain.value.status == 409
    with pytest.raises(bridge.BridgeError) as retry:
        current.attach(aid, "ATTACH REVIEWED CV", FAKE_PDF)
    assert retry.value.status == 409
    current.stop()


def test_sp112_real_http_binary_pdf_transfer_exact_headers_and_origin():
    current = state()
    with fake_local_http_server(current) as port:
        reply, _, opened = http_request(
            port, "/v1/prepare",
            {"pairing_code": PAIR_CODE, "packet": reviewed_pdf_packet()},
        )
        assert reply == 200
        token = opened["token"]
        status, _, inspected = http_request(
            port, "/v1/inspect", headers={"Authorization": "Bearer " + token},
        )
        assert status == 200
        aid = inspected["cv_attachment"]["attach_id"]

        def send_pdf(pdf, *, origin=SAFE_ORIGIN, change=None):
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            headers = {
                "Origin": origin, "Content-Type": "application/pdf",
                "Authorization": "Bearer " + token,
                "X-Smartploy-Attach-Id": aid,
                "X-Smartploy-Attach-Confirmation": "ATTACH REVIEWED CV",
            }
            if change:
                headers.update(change)
            conn.request("POST", "/v1/attach", body=pdf, headers=headers)
            response = conn.getresponse()
            data = json.loads(response.read())
            code = response.status
            cors = response.getheader("Access-Control-Allow-Origin")
            conn.close()
            return code, cors, data

        bad, cors, _ = send_pdf(FAKE_PDF, origin="https://evil.invalid")
        assert bad == 403 and cors is None
        bad, _, _ = send_pdf(b"%PDF-incorrect\n%%EOF\n")
        assert bad == 422
        assert FakeActor.instances[0].attachments == []
        passed, cors, result = send_pdf(FAKE_PDF)
        assert passed == 200 and cors == SAFE_ORIGIN
        assert result["stage"] == "attached"
        assert result["submitted"] is False
        assert result["employer_upload_confirmed"] is False
        again, _, _ = send_pdf(FAKE_PDF)
        assert again == 409
        assert len(FakeActor.instances[0].attachments) == 1


SP113_PAGE = "https://jobs.lever.co/example/position/thanks"
SP113_REFERENCE = "SYNTHETIC-REF-1234"


def fake_reference_confirmation():
    return {
        "confirmed": True,
        "reference": SP113_REFERENCE,
        "confirmation_page_url": SP113_PAGE,
        "confirmation_page_sha256": "f" * 64,
        "explanation": "Browser-visible reference observed",
    }


def test_sp113_receipt_observation_requires_pairing_explicit_user_approval():
    current = state()
    with pytest.raises(bridge.BridgeError):
        current.observe("OBSERVE EMPLOYER CONFIRMATION")
    current.prepare(PAIR_CODE, packet())
    with pytest.raises(bridge.BridgeError) as unapproved:
        current.observe("SUBMIT")
    assert unapproved.value.status == 403
    uncertain = current.observe("OBSERVE EMPLOYER CONFIRMATION")
    assert uncertain == {
        "ok": True, "stage": "observed", "confirmed": False,
        "receipt": None, "employer_acknowledged": False,
        "submitted": False, "uploaded": False,
    }
    # Observation is read-only and may be explicitly requested again
    # after the applicant navigates to the confirmed job receipt.
    FakeActor.instances[0].receipt_finding = fake_reference_confirmation()
    result = current.observe("OBSERVE EMPLOYER CONFIRMATION")
    assert result["stage"] == "observed"
    assert result["confirmed"] is True
    assert result["receipt"] == {
        "schema": "smartploy.browser_receipt.v1",
        "workspace_id": current.packet["workspace_id"],
        "document_revision": current.packet["revision"],
        "document_sha256": current.packet["document_sha256"],
        "application_url": current.packet["application_url"],
        "confirmation_page_url": SP113_PAGE,
        "reference": SP113_REFERENCE,
        "confirmation_page_sha256": "f" * 64,
        "observed_at": result["receipt"]["observed_at"],
        "confirmed_visible": True,
    }
    assert result["employer_acknowledged"] is False
    assert result["submitted"] is False
    assert result["uploaded"] is False
    assert len(result["receipt"]) == 10
    assert "fields" not in str(result)
    assert "cv_pdf" not in str(result)
    with pytest.raises(bridge.BridgeError) as duplicate:
        current.observe("OBSERVE EMPLOYER CONFIRMATION")
    assert duplicate.value.status == 409
    current.stop()


def test_sp113_expired_review_cannot_create_false_receipt():
    current = state()
    current.prepare(PAIR_CODE, packet())
    FakeActor.instances[0].receipt_finding = fake_reference_confirmation()
    current.packet["expires_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(bridge.BridgeError) as denied:
        current.observe("OBSERVE EMPLOYER CONFIRMATION")
    assert denied.value.status == 410
    current.stop()


def test_sp113_receipt_http_origin_token_and_user_confirmation():
    current = state()
    with fake_local_http_server(current) as port:
        status, _, opened = http_request(
            port, "/v1/prepare",
            {"pairing_code": PAIR_CODE, "packet": packet()},
        )
        assert status == 200
        token = opened["token"]
        FakeActor.instances[0].receipt_finding = fake_reference_confirmation()
        auth = {"Authorization": "Bearer " + token}
        denied, cors, _ = http_request(
            port, "/v1/observe",
            {"confirmation": "OBSERVE EMPLOYER CONFIRMATION"},
            origin="https://evil.invalid", headers=auth,
        )
        assert denied == 403
        assert "Access-Control-Allow-Origin" not in cors
        denied, _, _ = http_request(
            port, "/v1/observe",
            {"confirmation": "OBSERVE EMPLOYER CONFIRMATION"},
        )
        assert denied == 403
        denied, _, _ = http_request(
            port, "/v1/observe", {"confirmation": "SUBMIT"}, headers=auth,
        )
        assert denied == 403
        success, _, observed = http_request(
            port, "/v1/observe",
            {"confirmation": "OBSERVE EMPLOYER CONFIRMATION"}, headers=auth,
        )
        assert success == 200
        assert observed["confirmed"] is True
        assert observed["receipt"]["reference"] == SP113_REFERENCE
        assert observed["employer_acknowledged"] is False
        assert observed["submitted"] is False
        again, _, _ = http_request(
            port, "/v1/observe",
            {"confirmation": "OBSERVE EMPLOYER CONFIRMATION"}, headers=auth,
        )
        assert again == 409
        assert FakeActor.instances[0].attachments == []
        assert FakeActor.instances[0].page.filled == []
        current.stop()



def test_sp114_questions_inspection_and_single_approved_answer_fill():
    current = state()
    current.prepare(PAIR_CODE, packet())
    inspected = current.questions()
    assert inspected["stage"] == "questions_inspected"
    assert len(inspected["questions"]) == 1
    assert inspected["human_only"] == [
        "Visa sponsorship", "Salary expectation", "GDPR consent",
    ]
    assert "value" not in str(inspected)
    with pytest.raises(bridge.BridgeError) as wrong_id:
        current.fill_questions("wrong", "FILL REVIEWED ANSWERS", ["Truthful work"])
    assert wrong_id.value.status == 403
    with pytest.raises(bridge.BridgeError) as wrong_approval:
        current.fill_questions(inspected["plan_id"], "SUBMIT", ["Truthful work"])
    assert wrong_approval.value.status == 403
    with pytest.raises(bridge.BridgeError) as wrong_list:
        current.fill_questions(inspected["plan_id"], "FILL REVIEWED ANSWERS", [])
    assert wrong_list.value.status == 422
    result = current.fill_questions(
        inspected["plan_id"], "FILL REVIEWED ANSWERS",
        ["Led a documented project in Python"],
    )
    assert result == {
        "ok": True, "stage": "answers_filled",
        "status": "filled_for_review", "filled": 1, "planned": 1,
        "submitted": False, "uploaded": False,
    }
    assert FakeActor.instances[0].reviewed_answers == [
        "Led a documented project in Python",
    ]
    assert "Led a documented project" not in str(result)
    with pytest.raises(bridge.BridgeError) as replay:
        current.fill_questions(
            inspected["plan_id"], "FILL REVIEWED ANSWERS",
            ["Do not retry"],
        )
    assert replay.value.status == 409
    with pytest.raises(bridge.BridgeError):
        current.questions()
    current.stop()


def test_sp114_uncertain_answer_fill_cannot_be_replayed():
    class UncertainAnswers(FakeActor):
        def fill_questions(self, *_args):
            raise RuntimeError("Employer might have received one change event")
    current = bridge.BridgeState(
        pairing_code=PAIR_CODE, actor_factory=UncertainAnswers,
    )
    current.prepare(PAIR_CODE, packet())
    reviewed = current.questions()
    with pytest.raises(bridge.BridgeError) as first:
        current.fill_questions(
            reviewed["plan_id"], "FILL REVIEWED ANSWERS", ["Truthful"],
        )
    assert first.value.status == 409
    with pytest.raises(bridge.BridgeError) as retry:
        current.fill_questions(
            reviewed["plan_id"], "FILL REVIEWED ANSWERS", ["Truthful"],
        )
    assert retry.value.status == 409
    current.stop()


def test_sp114_expired_packet_blocks_question_fill_before_employer_input():
    current = state()
    current.prepare(PAIR_CODE, packet())
    reviewed = current.questions()
    current.packet["expires_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(bridge.BridgeError) as stale:
        current.fill_questions(
            reviewed["plan_id"], "FILL REVIEWED ANSWERS", ["Truthful"],
        )
    assert stale.value.status == 410
    assert FakeActor.instances[0].reviewed_answers == []
    current.stop()


def test_sp114_http_question_review_origin_token_and_one_time_answers():
    current = state()
    with fake_local_http_server(current) as port:
        status, _, opening = http_request(
            port, "/v1/prepare",
            {"pairing_code": PAIR_CODE, "packet": packet()},
        )
        assert status == 200
        token = opening["token"]
        auth = {"Authorization": "Bearer " + token}
        bad, hdr, _ = http_request(
            port, "/v1/questions", origin="https://evil.invalid",
            headers=auth,
        )
        assert bad == 403
        assert "Access-Control-Allow-Origin" not in hdr
        denied, _, _ = http_request(port, "/v1/questions")
        assert denied == 403
        status, _, review = http_request(
            port, "/v1/questions", headers=auth,
        )
        assert status == 200
        assert review["stage"] == "questions_inspected"
        assert "Visa sponsorship" in review["human_only"]
        denied, _, _ = http_request(
            port, "/v1/fill-questions",
            {
                "plan_id": review["plan_id"], "confirmation": "SUBMIT",
                "answers": ["Truthful"],
            }, headers=auth,
        )
        assert denied == 403
        successful, _, answer = http_request(
            port, "/v1/fill-questions",
            {
                "plan_id": review["plan_id"],
                "confirmation": "FILL REVIEWED ANSWERS",
                "answers": ["Truthful project work"],
            }, headers=auth,
        )
        assert successful == 200
        assert answer["status"] == "filled_for_review"
        assert answer["submitted"] is False
        assert "Truthful project work" not in str(answer)
        denied, _, _ = http_request(
            port, "/v1/fill-questions",
            {
                "plan_id": review["plan_id"],
                "confirmation": "FILL REVIEWED ANSWERS",
                "answers": ["Truthful project work"],
            }, headers=auth,
        )
        assert denied == 409
        assert FakeActor.instances[0].reviewed_answers == [
            "Truthful project work",
        ]
        assert FakeActor.instances[0].attachments == []
        current.stop()

"""Static deny-first contract for the SmartPloy reviewed PDF attachment.

No real employer calls or applicant files. Node/Chromium tests cover logic.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_no_new_browser_background_or_remote_host_capability():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["version"] == "0.2.0"
    assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
    for key in ("host_permissions", "background", "content_scripts"):
        assert key not in manifest


def test_document_transfer_requires_explicit_owner_selection():
    popup = (ROOT / "popup.mjs").read_text()
    page = (ROOT / "page-attachment.mjs").read_text()
    html = (ROOT / "popup.html").read_text()
    policy = (ROOT / "upload.mjs").read_text()
    assert 'type="file" id="cvFile"' in html
    assert 'id="attach"' in html
    assert 'const file = $("cvFile").files?.[0]' in popup
    assert "validatePacket(currentPacketToJSON(), rechecked.url)" in popup
    assert "chooseResumeField(inspection.result.elements)" in popup
    assert "chrome.storage.local.get(attemptKey)" in popup
    assert '"SEND REVIEWED PDF TO EMPLOYER?' in popup
    assert popup.index('"SEND REVIEWED PDF TO EMPLOYER?') < popup.index("func: attachReviewedPdf")
    assert 'location.href !== payload.inspected_url' in page
    assert 'input.files = transfer.files' in page
    assert 'crypto.subtle.digest("SHA-256", bytes)' in page
    assert "MAX_PDF_BYTES = 2 * 1024 * 1024" in policy
    assert 'status: "attached_locally"' in page
    assert 'status: "ambiguous"' in page
    for prohibited in ("fetch(", "XMLHttpRequest(", "document.cookie", "innerHTML",
                       "chrome.webRequest", "chrome.runtime.onMessage", "eval("):
        assert prohibited not in page + policy


def test_cv_identity_and_existing_one_attempt_submit_still_protected():
    popup = (ROOT / "popup.mjs").read_text()
    assert '![path + "/apply", path + "/apply/"].includes(here.pathname)' in popup
    assert "A CV/résumé must be attached in its own labeled upload field." in popup
    assert "Attach your CV in the labeled résumé field before submitting." in popup
    assert 'chrome.storage.local.set({[key]:' in popup
    assert popup.index('chrome.storage.local.set({[key]:') < popup.index('func: submitOnce')

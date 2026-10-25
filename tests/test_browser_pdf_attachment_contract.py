"""Static deny-first contract for the SmartPloy reviewed PDF attachment.

No real employer calls or applicant files. Node/Chromium tests cover logic.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1] / "browser-companion"


def test_no_new_browser_background_or_remote_host_capability():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["version"] == "0.4.0"
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
    # Ashby is fill-only: do not require a Lever oneAttemptKey for its PDF.
    # Existing Lever jobs still check the irreversible browser attempt record.
    assert "await hasPriorLeverAttempt(currentPacket)" in popup
    assert "if (!isLeverFinalProvider(packet.application_url))" in popup
    assert "const key = await oneAttemptKey(packet)" in popup
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


def test_cv_identity_preserved_but_final_click_fail_closed_without_server_claim():
    popup = (ROOT / "popup.mjs").read_text()
    assert "A CV/résumé must be attached in its own labeled upload field." in popup
    assert 'crypto.subtle.digest("SHA-256", bytes)' in popup
    assert 'attemptReserved' in popup
    assert "await requireOneUseFinalAttempt(chrome.storage.session, packet)" in popup
    assert "await chrome.storage.local.set({[key]: stamp})" in popup
    assert popup.index("await chrome.storage.local.set({[key]: stamp})") < popup.index(
        "func: submitReviewedLeverOnce")
    assert 'func: reserveFinalClickOnSmartPloy' in popup
    assert "func: submitOnce" not in popup
    assert "live[0].click()" not in popup


def test_sp42_ashby_manual_confirmation_never_reuses_lever_submission_authority():
    """Static final-action boundary complements real Node/Chromium receipt tests."""
    popup = (ROOT / "popup.mjs").read_text(encoding="utf-8")
    html = (ROOT / "popup.html").read_text(encoding="utf-8")
    companion = (ROOT / "upload.mjs").read_text(encoding="utf-8")

    observed = popup.split("async function onReceipt() {", 1)[1].split(
        '$("verifyReview").addEventListener', 1
    )[0]
    assert "exactAshbyReceiptPage(tab.url, currentPacket.application_url)" in observed
    assert "await requireVerifiedReview(chrome.storage?.session, currentPacket)" in observed
    assert "window.confirm(" in observed
    assert "You confirm you personally clicked the employer's Submit button" in observed
    assert "args: [original.origin, account, ashbyPosting]" in observed
    assert "if (lever) {" in observed
    assert "await oneAttemptKey(currentPacket)" in observed
    assert "submitReviewedLeverOnce" not in observed
    assert "reserveFinalClickOnSmartPloy" not in observed
    assert "external_actions_performed" not in observed
    assert "exactAshbyReceiptPage" in companion
    assert "previous attempt or manual Ashby confirmation" in html
